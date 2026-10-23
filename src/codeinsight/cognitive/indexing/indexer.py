"""索引主流程（规格 §1.2 M1）。

一次索引 = **扫描 → 解析 → 落库**三段，中间用 `ParsedFile` 串起来。

一个刻意的安排：**符号全部落库之后才写边**。
因为边要解析到具体符号 id，而「这个 qualname 对应哪个符号」只有全局才知道
（同名多义时甚至无法唯一确定）。两趟写换来的是「不猜」——
边要么指向唯一确定的符号，要么 `dst_symbol_id` 留 NULL。

索引绑定 commit，不扫工作区（`scanner.py` 的说明有理由）：
认知必须和确定的代码版本关联，否则「过期信息比例」这个指标没法算。
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from codeinsight.cognitive.indexing.edges import (
    EdgeResolver,
    FileSymbolScope,
    ImportBindings,
    build_bindings,
    write_edges,
)
from codeinsight.cognitive.indexing.entries import (
    DependencySpec,
    collect_import_dependencies,
    detect_entry_points,
    normalize_distribution,
    parse_pyproject_dependencies,
    parse_requirements_text,
)
from codeinsight.cognitive.indexing.scanner import (
    RepoFile,
    list_repo_files,
    module_qualname,
    read_blobs,
)
from codeinsight.cognitive.indexing.symbols import (
    SymbolIndex,
    write_module,
    write_symbols,
)
from codeinsight.cognitive.parsing.base import ParseContext
from codeinsight.cognitive.parsing.python_parser import PythonParser
from codeinsight.storage.sqlite import ensure_schema, open_sqlite

PARSER_VERSION = "python-ast-1"
"""解析器版本。变了就要重建索引（`repo_state.parser_version` 不匹配时强制全量）。"""

_INDEXED_FILE_ROLES = frozenset({"source", "test", "generated", "config", "doc", "vendored"})
"""会进 `file` 表的角色。`vendored` 也进——它只是不进 chunk 索引。"""


@dataclass
class IndexResult:
    """一次索引的结果摘要。"""

    project_id: int
    project_name: str
    head_commit: str
    files: int = 0
    modules: int = 0
    symbols: int = 0
    edges: int = 0
    resolved_edges: int = 0
    entry_points: int = 0
    dependencies: int = 0
    skipped: int = 0
    elapsed_s: float = 0.0
    stats: dict = field(default_factory=dict)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", "replace").strip()


def _resolve_commit(root: Path, ref: str | None) -> tuple[str, str]:
    """返回 (commit_sha, branch)。非 git 目录返回 ("", "")。"""
    if not (root / ".git").exists():
        return "", ""
    commit = _git(root, "rev-parse", ref or "HEAD")
    branch = _git(root, "rev-parse", "--abbrev-ref", ref or "HEAD")
    return commit, branch


def _origin_url(root: Path) -> str:
    """项目根路径：优先用 git origin URL。

    用 URL 而不是本地绝对路径，索引库才能跟着仓库走——本地路径进了库，
    别人就复现不了，公开仓库里还等于泄露本机目录结构。
    """
    url = _git(root, "config", "--get", "remote.origin.url")
    if url:
        return url
    return str(root.resolve())


def _stdlib_names() -> frozenset[str]:
    """标准库顶层模块名。用来把 `import os` 从「未声明依赖」里排除。"""
    import sys

    names = set(getattr(sys, "stdlib_module_names", ()))
    return frozenset(names)


@dataclass
class _ParsedEntry:
    path: str
    module_qualname: str
    parsed: object
    source_lines: list[str]


def index_project(
    db_path: str | Path,
    *,
    root: str | Path,
    name: str,
    ref: str | None = None,
) -> IndexResult:
    """对一个仓库做一次**全量**索引。

    参数
    ----
    db_path
        索引库路径。
    root
        仓库根目录。
    name
        项目显示名（同名项目会被复用）。
    ref
        git ref（缺省 HEAD）。

    全量重建的理由：先让「索引是对某个 commit 的完整快照」这件事成立，
    增量（M6）才有明确的对比基准。增量版会在同一套写入逻辑上加一层 diff。
    """
    started = time.monotonic()
    root = Path(root)
    ensure_schema(db_path)

    head_commit, head_branch = _resolve_commit(root, ref)
    parser = PythonParser()

    files = list_repo_files(root, ref=ref)
    indexed = [f for f in files if f.role in _INDEXED_FILE_ROLES]

    # 一次 `git cat-file --batch` 管道读全部内容：算 sha256（过期判定用）、
    # 算行数、给解析器喂源码。分多次读就是分多次进程创建，慢一个量级。
    blobs = read_blobs(root, ref, [f.path for f in indexed])
    to_parse = [f for f in indexed if parser.supports(f.path)]

    with open_sqlite(db_path) as conn:
        project_id = _ensure_project(conn, name=name, root_path=_origin_url(root))
        _clear_project_data(conn, project_id)

        file_ids: dict[str, int] = {}
        for f in indexed:
            raw = blobs.get(f.path, b"")
            file_ids[f.path] = _write_file(
                conn,
                project_id=project_id,
                repo_file=f,
                content_sha256=hashlib.sha256(raw).hexdigest(),
                line_count=raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0),
            )

        # ── 解析 ────────────────────────────────────────────────
        parsed_entries: list[_ParsedEntry] = []
        skipped = 0
        for f in to_parse:
            raw = blobs.get(f.path)
            if raw is None:
                skipped += 1
                continue
            source = raw.decode("utf-8", "replace")
            source_lines = source.splitlines()
            parsed = parser.parse(
                f.path, source, ParseContext(project_id=project_id, repo_root=str(root))
            )
            if not parsed.symbols and source.strip():
                # 语法错误或空文件——记为跳过，不让整次索引失败（ADR 0012）。
                skipped += 1
                continue
            parsed_entries.append(
                _ParsedEntry(
                    path=f.path,
                    module_qualname=module_qualname(f.path),
                    parsed=parsed,
                    source_lines=source_lines,
                )
            )

        # ── 模块与符号 ─────────────────────────────────────────
        symbol_index = SymbolIndex()
        scopes: dict[str, FileSymbolScope] = {}
        bindings: dict[str, ImportBindings] = {}
        src_modules: dict[str, str] = {}
        module_ids: dict[str, int] = {}
        symbol_count = 0

        for entry in parsed_entries:
            module_id = write_module(
                conn,
                project_id=project_id,
                file_id=file_ids[entry.path],
                qualname=entry.module_qualname,
                docstring=getattr(entry.parsed, "module_docstring", None),
            )
            module_ids[entry.module_qualname] = module_id
            ids = write_symbols(
                conn,
                project_id=project_id,
                file_id=file_ids[entry.path],
                module_id=module_id,
                module_qualname=entry.module_qualname,
                parsed=entry.parsed,
                source_lines=entry.source_lines,
                index=symbol_index,
            )
            scope = FileSymbolScope()
            for symbol, symbol_id in zip(entry.parsed.symbols, ids, strict=True):
                scope.entries.append((symbol.qualname, symbol.lineno, symbol.end_lineno, symbol_id))
                src_modules[symbol.qualname] = entry.module_qualname
            symbol_count += len(ids)
            scopes[entry.path] = scope
            bindings[entry.module_qualname] = build_bindings(entry.parsed.imports)

        # ── 边（全局符号表齐了才写）──────────────────────────────
        resolver = EdgeResolver(symbol_index, bindings)
        edge_count = 0
        for entry in parsed_entries:
            edge_count += write_edges(
                conn,
                project_id=project_id,
                scope=scopes[entry.path],
                edges=list(entry.parsed.edges),
                resolver=resolver,
                src_modules=src_modules,
            )
        resolved_count = conn.execute(
            "SELECT COUNT(*) FROM edge WHERE project_id = ? AND dst_symbol_id IS NOT NULL",
            (project_id,),
        ).fetchone()[0]

        # ── 入口与依赖 ─────────────────────────────────────────
        entry_points = _write_entry_points(
            conn,
            project_id=project_id,
            root=root,
            files=[f.path for f in indexed],
            sources={e.path: "\n".join(e.source_lines) for e in parsed_entries},
        )
        dependencies = _write_dependencies(
            conn,
            project_id=project_id,
            root=root,
            indexed=indexed,
            imported_modules=sorted(
                {
                    imp.module
                    for entry in parsed_entries
                    for imp in entry.parsed.imports
                    if imp.module
                }
            ),
            local_packages={qual.split(".")[0] for qual in module_ids},
        )

        # ── 状态 ───────────────────────────────────────────────
        epoch = conn.execute(
            "SELECT index_epoch FROM repo_state WHERE project_id = ?", (project_id,)
        ).fetchone()
        next_epoch = (epoch[0] if epoch else 0) + 1
        conn.execute(
            """
            INSERT INTO repo_state (project_id, head_commit, head_branch, indexed_at,
                                    parser_version, index_epoch)
            VALUES (?, ?, ?, datetime('now'), ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                head_commit = excluded.head_commit,
                head_branch = excluded.head_branch,
                indexed_at = excluded.indexed_at,
                parser_version = excluded.parser_version,
                index_epoch = excluded.index_epoch
            """,
            (project_id, head_commit, head_branch, PARSER_VERSION, next_epoch),
        )

        conn.execute(
            """
            INSERT INTO index_run (project_id, base_commit, head_commit, mode,
                                   started_at, finished_at, ok,
                                   files_total, symbols_added, stats_json)
            VALUES (?, ?, ?, 'full', ?, datetime('now'), 1, ?, ?, ?)
            """,
            (
                project_id,
                head_commit,
                head_commit,
                started,
                len(indexed),
                symbol_count,
                None,
            ),
        )
        conn.commit()

    return IndexResult(
        project_id=project_id,
        project_name=name,
        head_commit=head_commit,
        files=len(indexed),
        modules=len(module_ids),
        symbols=symbol_count,
        edges=edge_count,
        resolved_edges=resolved_count,
        entry_points=entry_points,
        dependencies=dependencies,
        skipped=skipped,
        elapsed_s=time.monotonic() - started,
        stats={"index_epoch": next_epoch, "parser_version": PARSER_VERSION},
    )


def _ensure_project(conn: sqlite3.Connection, *, name: str, root_path: str) -> int:
    row = conn.execute("SELECT id FROM project WHERE name = ?", (name,)).fetchone()
    if row:
        conn.execute("UPDATE project SET root_path = ? WHERE id = ?", (root_path, row[0]))
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO project (name, root_path) VALUES (?, ?)",
        (name, root_path),
    )
    return int(cur.lastrowid or 0)


def _clear_project_data(conn: sqlite3.Connection, project_id: int) -> None:
    """清掉这个项目的旧索引数据（保留 project 行与 id）。

    删除顺序照顾外键：`file` 的 CASCADE 会带走 module/symbol/edge/chunk/flow。
    不在级联范围内的表显式删。
    """
    conn.execute("DELETE FROM dependency WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM entry_point WHERE project_id = ?", (project_id,))
    conn.execute(
        "DELETE FROM design_decision_evidence WHERE decision_id IN "
        "(SELECT id FROM design_decision WHERE project_id = ?)",
        (project_id,),
    )
    conn.execute("DELETE FROM design_decision WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM flow WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM file WHERE project_id = ?", (project_id,))
    conn.commit()


def _write_file(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    repo_file: RepoFile,
    content_sha256: str,
    line_count: int,
) -> int:
    """写一行 `file` 表。

    `content_sha256` 是**文件内容的 sha256**——过期判定的粗筛层靠它
    （`file_snapshot` 与 `v_stale_candidate` 用同一个算法，两边必须一致）。
    """
    cur = conn.execute(
        """
        INSERT INTO file (project_id, path, language, blob_sha, content_sha256,
                          size_bytes, line_count, role, in_index)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            repo_file.path,
            repo_file.language,
            repo_file.blob_sha,
            content_sha256,
            repo_file.size_bytes,
            line_count,
            repo_file.role,
            int(repo_file.in_index),
        ),
    )
    return int(cur.lastrowid or 0)


def _write_entry_points(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    root: Path,
    files: list[str],
    sources: dict[str, str],
) -> int:
    pyproject = _load_pyproject(root)
    specs = detect_entry_points(files=files, sources=sources, pyproject=pyproject)
    count = 0
    for spec in specs:
        module_id = None
        if spec.module_qualname:
            row = conn.execute(
                "SELECT id FROM module WHERE project_id = ? AND qualname = ?",
                (project_id, spec.module_qualname),
            ).fetchone()
            if row:
                module_id = int(row[0])
        conn.execute(
            """
            INSERT INTO entry_point (project_id, module_id, kind, target, source_path, doc)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                module_id,
                spec.kind,
                spec.target,
                spec.source_path,
                spec.doc,
            ),
        )
        count += 1
    return count


def _load_pyproject(root: Path) -> dict | None:
    import tomllib

    path = root / "pyproject.toml"
    if not path.exists():
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None


def _write_dependencies(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    root: Path,
    indexed: list[RepoFile],
    imported_modules: list[str],
    local_packages: set[str],
) -> int:
    """写依赖表：先声明的（pyproject / requirements），后 import 到的。

    `local_packages` 是本仓库自己的顶层包（`backend` / `scripts` / `tests` …）——
    它们不是依赖，是项目自己的代码。混进依赖表会让「这个项目用了什么」
    这个问题的答案失真。
    """
    specs: list[DependencySpec] = []

    pyproject = _load_pyproject(root)
    if pyproject:
        specs.extend(parse_pyproject_dependencies(pyproject))

    for repo_file in indexed:
        name = repo_file.path.rsplit("/", 1)[-1]
        if not name.startswith("requirements") or not name.endswith(".txt"):
            continue
        path = root / repo_file.path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        specs.extend(parse_requirements_text(text))

    # 只在源码里 import 到、但没声明的 → source='import'。
    specs.extend(
        collect_import_dependencies(
            imported_modules,
            stdlib_names=_stdlib_names(),
            local_packages=local_packages,
        )
    )

    count = 0
    seen: set[str] = set()
    for spec in specs:
        key = normalize_distribution(spec.name)
        if key in seen:
            # 同一个包既被声明又被 import 到：保留声明那条（信息更全）。
            continue
        seen.add(key)
        conn.execute(
            """
            INSERT INTO dependency (project_id, name, version, source, declared, is_dev)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, name) DO UPDATE SET
                version = excluded.version,
                source = excluded.source,
                declared = excluded.declared,
                is_dev = excluded.is_dev
            """,
            (
                project_id,
                spec.name,
                spec.version,
                spec.source,
                int(spec.declared),
                int(spec.is_dev),
            ),
        )
        count += 1
    return count


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
