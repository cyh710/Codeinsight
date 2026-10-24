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
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path

from codeinsight.cognitive.indexing.chunker import DEFAULT_MAX_CHUNK_LINES, chunk_symbol
from codeinsight.cognitive.indexing.design_docs import DesignDoc, parse_design_docs
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
from codeinsight.cognitive.indexing.flows import (
    FlowEdge,
    FlowEntry,
    FlowSymbol,
    detect_flows,
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
    flows: int = 0
    design_decisions: int = 0
    dependencies: int = 0
    skipped: int = 0
    chunks: int = 0
    embedded: int = 0
    concepts: int = 0
    concept_instances: int = 0
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


def _root_label(root: Path) -> str:
    """项目根路径：本地绝对路径。

    `project.root_path` 的语义是「这个项目指向哪个仓库」——
    API 层用它做「同名同路径 = 重建索引」的判定，
    所以这里必须写**调用方给的路径**，不能替它改。

    「公开仓库里不能留本机绝对路径」这个顾虑落在**发布出去的东西**上，
    不在本地索引库里：索引库在 `.ci/` 里、是被 gitignore 的；
    真正会被公开的是 `fixtures/sample-index.json`，
    它的 `root_path` 由 `snapshot.py` 单独写成 git origin URL。
    """
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


def run_index(
    conn: sqlite3.Connection,
    project_id: int,
    root_path: str | Path,
    ref: str | None = None,
    *,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
    embed: bool = False,
    concepts_dir: str | Path | None = None,
    incremental: bool = False,
) -> dict:
    """扫描 → 解析 → 落库 → `repo_state` 收尾（**不含** `index_run` 记账）。

    这是 C 线 `api/indexing.py::_ENGINE_CALLABLE` 要接的入口
    （见 `docs/requests/0002-index-engine-entry.md`）：

    - `conn` 由调用方传入——事务与 `index_run` 记账归 API 层，引擎只管数据；
    - 只返回原始计数，概览由调用方自己 `COUNT(*)` 生成，避免两处口径漂移；
    - 失败抛异常，调用方的 try/except 会把它记进 `index_run.stats_json`。

    `embed=True` 时额外算向量——**默认关**：嵌入是唯一重的一步（要调外部 API），
    而且没有 key 时本来就跑不了。

    `concepts_dir` 指向概念本体目录（B 线的 `knowledge/concepts`）。
    给了就跑一次概念检测，把本体与实例写进 `concept` / `concept_instance`
    两张表——概念检索通道就靠这两张表供数。

    语义是**全量重建**：先清掉这个项目的数据再重建。
    先让「索引是对某个 commit 的完整快照」这件事成立，
    增量（M6）才有明确的对比基准。

    `incremental=True` 时先试增量：只重算变了的文件与符号，其余行一行不动。
    不能增量（没有上一位点 / 历史被改写 / 解析器版本变了）时自动退回全量——
    **退路由引擎自己判断**，调用方不需要知道哪条路走成了。
    """
    started = time.monotonic()
    root = Path(root_path)

    if incremental:
        from codeinsight.cognitive.changes.incremental import run_incremental

        stats = run_incremental(
            conn,
            project_id,
            root,
            ref,
            max_chunk_lines=max_chunk_lines,
            embed=embed,
            concepts_dir=concepts_dir,
        )
        if stats is not None:
            stats.setdefault("elapsed_s", time.monotonic() - started)
            return stats

    head_commit, head_branch = _resolve_commit(root, ref)
    parser = PythonParser()

    files = list_repo_files(root, ref=ref)
    indexed = [f for f in files if f.role in _INDEXED_FILE_ROLES]

    # 一次 `git cat-file --batch` 管道读全部内容：算 sha256（过期判定用）、
    # 算行数、给解析器喂源码。分多次读就是分多次进程创建，慢一个量级。
    blobs = read_blobs(root, ref, [f.path for f in indexed])
    to_parse = [f for f in indexed if parser.supports(f.path)]

    with nullcontext(conn) as conn:
        _clear_project_data(conn, project_id)

        file_ids: dict[str, int] = {}
        file_sha: dict[str, str] = {}
        role_by_path: dict[str, str] = {}
        for f in indexed:
            raw = blobs.get(f.path, b"")
            digest = hashlib.sha256(raw).hexdigest()
            file_sha[f.path] = digest
            role_by_path[f.path] = f.role
            file_ids[f.path] = _write_file(
                conn,
                project_id=project_id,
                repo_file=f,
                content_sha256=digest,
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
        chunk_count = 0

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

            # ── 切块（ADR 0005）────────────────────────────────
            # vendored 文件只进符号索引，不进块索引（ADR 0015 第二档）：
            # 第三方代码不该出现在「这个项目怎么做的」的答案里。
            if role_by_path[entry.path] != "vendored":
                chunk_count += _write_chunks(
                    conn,
                    project_id=project_id,
                    file_id=file_ids[entry.path],
                    file_content_sha256=file_sha[entry.path],
                    parsed=entry.parsed,
                    source_lines=entry.source_lines,
                    symbol_ids=ids,
                    max_lines=max_chunk_lines,
                )

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
        entry_specs = _write_entry_points(
            conn,
            project_id=project_id,
            root=root,
            files=[f.path for f in indexed],
            sources={e.path: "\n".join(e.source_lines) for e in parsed_entries},
        )
        entry_points = len(entry_specs)
        flow_count = _write_flows(conn, project_id=project_id, entry_specs=entry_specs)
        design_count = _write_design_decisions(
            conn,
            project_id=project_id,
            docs=parse_design_docs(
                [f.path for f in indexed],
                {
                    f.path: blobs[f.path].decode("utf-8", "replace")
                    for f in indexed
                    if f.path.endswith(".md") and f.path in blobs
                },
            ),
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

        # ── 概念同步（可选）─────────────────────────────────────
        concept_count = 0
        concept_instances = 0
        if concepts_dir:
            from codeinsight.cognitive.indexing.concepts_sync import sync_concepts

            sync = sync_concepts(
                conn,
                project_id=project_id,
                knowledge_dir=concepts_dir,
                sources={e.path: "\n".join(e.source_lines) for e in parsed_entries},
            )
            concept_count = sync.concepts
            concept_instances = sync.instances

        # ── 向量（可选）───────────────────────────────────────
        embedded = 0
        if embed:
            embedded = _embed_chunks(conn, project_id=project_id)

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

        conn.commit()

    return {
        "head_commit": head_commit,
        "head_branch": head_branch,
        "files": len(indexed),
        "modules": len(module_ids),
        "symbols": symbol_count,
        "edges": edge_count,
        "resolved_edges": resolved_count,
        "entry_points": entry_points,
        "flows": flow_count,
        "design_decisions": design_count,
        "dependencies": dependencies,
        "skipped": skipped,
        "chunks": chunk_count,
        "embedded": embedded,
        "concepts": concept_count,
        "concept_instances": concept_instances,
        "elapsed_s": time.monotonic() - started,
        "index_epoch": next_epoch,
        "parser_version": PARSER_VERSION,
    }


def index_project(
    db_path: str | Path,
    *,
    root: str | Path,
    name: str,
    ref: str | None = None,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
    embed: bool = False,
    concepts_dir: str | Path | None = None,
    incremental: bool = False,
) -> IndexResult:
    """对一个仓库建索引并记账（CLI 与测试用）。

    这是 `run_index` 的薄包装：自己开库、自己建项目行、自己写 `index_run`。
    API 层要用的是 `run_index`——那里连接与记账都归调用方。
    """
    started = time.monotonic()
    ensure_schema(db_path)

    with open_sqlite(db_path) as conn:
        project_id = _ensure_project(conn, name=name, root_path=_root_label(Path(root)))
        stats = run_index(
            conn,
            project_id,
            root,
            ref,
            max_chunk_lines=max_chunk_lines,
            embed=embed,
            concepts_dir=concepts_dir,
            incremental=incremental,
        )
        # `base_commit` 记的是上一次索引停在哪——它是这次增量的参照点，
        # 也是「这份认知有多新」的唯一依据。
        base_row = conn.execute(
            "SELECT base_commit FROM index_run WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        mode = "incremental" if stats.get("changed_symbols") is not None else "full"
        conn.execute(
            """
            INSERT INTO index_run (project_id, base_commit, head_commit, mode,
                                   started_at, finished_at, ok,
                                   files_total, symbols_added, stats_json)
            VALUES (?, ?, ?, ?, ?, datetime('now'), 1, ?, ?, ?)
            """,
            (
                project_id,
                base_row[0] if base_row else stats["head_commit"],
                stats["head_commit"],
                mode,
                started,
                stats["files"],
                stats.get("changed_symbols", stats["symbols"]),
                None,
            ),
        )
        conn.commit()

    return IndexResult(
        project_id=project_id,
        project_name=name,
        head_commit=stats["head_commit"],
        files=stats["files"],
        modules=stats["modules"],
        symbols=stats["symbols"],
        edges=stats["edges"],
        resolved_edges=stats["resolved_edges"],
        entry_points=stats["entry_points"],
        flows=stats["flows"],
        design_decisions=stats["design_decisions"],
        dependencies=stats["dependencies"],
        skipped=stats["skipped"],
        chunks=stats["chunks"],
        embedded=stats["embedded"],
        concepts=stats["concepts"],
        concept_instances=stats["concept_instances"],
        elapsed_s=time.monotonic() - started,
        stats={
            "index_epoch": stats["index_epoch"],
            "parser_version": stats["parser_version"],
            # 增量模式的附加信息（全量时不存在）。
            **{
                key: stats[key]
                for key in ("changed_symbols", "stale_design_decisions")
                if key in stats
            },
        },
    )


def _ensure_project(conn: sqlite3.Connection, *, name: str, root_path: str) -> int:
    """按名字取项目行；没有就建一个。

    **不覆盖已有行的 `root_path`**：调用方（API 层）拿它做
    「同名同路径 = 重建索引」的判定，引擎擅自改成 origin URL 之后，
    第二次导入同一个仓库会被误判成「同名不同路径」而拒掉。
    """
    row = conn.execute("SELECT id FROM project WHERE name = ?", (name,)).fetchone()
    if row:
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


def _write_chunks(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    file_id: int,
    file_content_sha256: str,
    parsed: object,
    source_lines: list[str],
    symbol_ids: list[int],
    max_lines: int,
) -> int:
    """切块并写进 `chunk` 表（ADR 0005）。

    `file_content_sha256` 是**文件级**哈希——过期判定的粗筛层；
    `chunk.source_sha256` 是**块级**哈希——精确层。
    文件变了但符号没变时，粗筛会误报，精确层不会。
    """
    import_lines = [imp.lineno for imp in parsed.imports if imp.lineno]
    # 只保留**模块头部**的 import：函数体里的 import 是实现细节，
    # 混进模块块会让它的行号范围一路延伸到文件末尾。
    first_symbol_line = min(
        (s.lineno for s in parsed.symbols if str(s.kind) != "module"),
        default=0,
    )
    if first_symbol_line:
        import_lines = [lineno for lineno in import_lines if lineno < first_symbol_line]

    written = 0
    for symbol, symbol_id in zip(parsed.symbols, symbol_ids, strict=True):
        for spec in chunk_symbol(
            symbol,
            source_lines,
            max_lines=max_lines,
            import_lines=import_lines,
        ):
            conn.execute(
                """
                INSERT INTO chunk (
                    project_id, symbol_id, file_id, ordinal, part_count,
                    qualname, name, kind, lineno, end_lineno, header, body,
                    token_text, source_sha256, file_content_sha256, content_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    symbol_id,
                    file_id,
                    spec.ordinal,
                    spec.part_count,
                    spec.qualname,
                    spec.name,
                    spec.kind,
                    spec.lineno,
                    spec.end_lineno,
                    spec.header,
                    spec.body,
                    spec.token_text,
                    spec.source_sha256,
                    file_content_sha256,
                    spec.content_kind,
                ),
            )
            written += 1
    return written


def _embed_chunks(conn: sqlite3.Connection, *, project_id: int) -> int:
    """给所有块算向量（可选步骤）。

    内容没变的块**复用旧向量**——`embedding.text_sha256` 存的就是
    `chunk.source_sha256`（块正文的哈希），对上了就不用重算。

    没有 embedder / 没有 key 时返回 0：稠密通道自动少一路，
    其余两路照常工作（评测时这正是「hybrid 臂退化成 bm25 臂」的情况，
    得如实记下来而不是假装跑过了）。
    """
    from codeinsight.cognitive.embedding.siliconflow import SiliconFlowEmbedder
    from codeinsight.cognitive.retrieval.dense import (
        SqliteVectorStore,
        register_model,
        reusable_vector_ids,
    )

    embedder = SiliconFlowEmbedder()
    if not embedder.enabled:
        return 0

    rows = conn.execute(
        "SELECT id, body, source_sha256 FROM chunk WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    if not rows:
        return 0

    digest_of = {int(r[0]): r[2] for r in rows}
    reusable = reusable_vector_ids(conn, model_id=embedder.model_id, text_sha256s=digest_of)
    todo = [r for r in rows if int(r[0]) not in reusable]
    if not todo:
        return 0

    register_model(
        conn,
        model_id=embedder.model_id,
        dim=embedder.dim,
        provider=embedder._base_url,  # noqa: SLF001 —— 只为排查用
    )

    store = SqliteVectorStore(conn, model_id=embedder.model_id)
    written = 0
    batch_size = 32
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        vectors = embedder.encode([r[1] for r in batch])
        if len(vectors) != len(batch):
            continue
        store.upsert(
            [int(r[0]) for r in batch],
            vectors,
            text_sha256s=[r[2] for r in batch],
        )
        written += len(batch)
    return written


def _write_entry_points(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    root: Path,
    files: list[str],
    sources: dict[str, str],
) -> list:
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
    return specs


def _write_flows(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    entry_specs: list,
) -> int:
    """检测关键业务流程并写进 `flow` / `flow_step`（规格 §1.2 A5）。"""
    symbol_rows = conn.execute(
        """
        SELECT s.id, s.qualname, s.name, s.kind, f.path, s.lineno, COALESCE(m.qualname, '')
        FROM symbol s
        JOIN file f ON f.id = s.file_id
        LEFT JOIN module m ON m.id = s.module_id
        WHERE s.project_id = ?
        """,
        (project_id,),
    ).fetchall()
    symbols = [FlowSymbol(*row) for row in symbol_rows]

    edge_rows = conn.execute(
        """
        SELECT src_symbol_id, dst_symbol_id, kind, dst_name, confidence
        FROM edge WHERE project_id = ? AND kind = 'call'
        """,
        (project_id,),
    ).fetchall()
    edges = [FlowEdge(*row) for row in edge_rows]

    entries = [_flow_entry(spec) for spec in entry_specs]
    flows = detect_flows(symbols, edges, entries)

    for flow in flows:
        cur = conn.execute(
            """
            INSERT INTO flow (project_id, name, entry_symbol_id, description)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, flow.name, flow.entry_symbol_id, flow.description),
        )
        flow_id = int(cur.lastrowid or 0)
        for ordinal, step in enumerate(flow.steps):
            conn.execute(
                """
                INSERT INTO flow_step (flow_id, ordinal, symbol_id, qualname, path, lineno, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    flow_id,
                    ordinal,
                    step.symbol_id,
                    step.qualname,
                    step.path,
                    step.lineno,
                    step.note,
                ),
            )
    return len(flows)


def _flow_entry(spec) -> FlowEntry:
    """把入口规格转成流程检测用的起点。"""
    target = spec.target
    if spec.kind == "console_script" and "=" in target:
        target = target.split("=", 1)[1].strip()

    module_qualname = spec.module_qualname
    symbol_qualname = None
    if ":" in target:
        module_part, _, attr = target.partition(":")
        module_qualname = module_qualname or module_part
        if spec.kind == "console_script" and attr:
            # `pkg.main:main` → 符号 qualname `pkg.main.main`
            symbol_qualname = f"{module_part}.{attr}"
    return FlowEntry(
        kind=spec.kind,
        target=target,
        module_qualname=module_qualname,
        symbol_qualname=symbol_qualname,
    )


def _write_design_decisions(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    docs: list[DesignDoc],
) -> int:
    """写设计说明及其证据（规格 §1.2 A6）。

    证据 = 「这条设计说明提到的文件/符号，在代码里确实在这儿」。
    M6 的过期检测就靠它：符号没了、文件没了 → 这条设计说明不再适用。
    """
    import json

    count = 0
    for doc in docs:
        cur = conn.execute(
            """
            INSERT INTO design_decision (project_id, doc_id, title, status, body, path, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, doc_id) DO UPDATE SET
                title = excluded.title,
                status = excluded.status,
                body = excluded.body,
                path = excluded.path,
                decided_at = excluded.decided_at,
                claims_json = excluded.claims_json
            """,
            (
                project_id,
                doc.doc_id,
                doc.title,
                doc.status,
                doc.body,
                doc.path,
                doc.decided_at,
            ),
        )
        del cur
        conn.execute(
            "UPDATE design_decision SET claims_json = ? WHERE project_id = ? AND doc_id = ?",
            (json.dumps(doc.claims, ensure_ascii=False), project_id, doc.doc_id),
        )
        decision_id = conn.execute(
            "SELECT id FROM design_decision WHERE project_id = ? AND doc_id = ?",
            (project_id, doc.doc_id),
        ).fetchone()[0]

        for claim in doc.claims:
            for evidence in _claim_evidence(conn, project_id, claim):
                conn.execute(
                    """
                    INSERT INTO design_decision_evidence (decision_id, symbol_id, path, lineno, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        decision_id,
                        evidence[0],
                        evidence[1],
                        evidence[2],
                        evidence[3],
                    ),
                )
        count += 1
    return count


def _claim_evidence(
    conn: sqlite3.Connection,
    project_id: int,
    claim: dict,
) -> list[tuple[int | None, str | None, int | None, str]]:
    """把一条 claim 落到具体代码位置上。

    路径 claim → 那个文件（及其模块符号）。
    符号 claim → 名字或点号后缀匹配的符号。
    """
    value = claim.get("value") or ""
    if claim.get("kind") == "path":
        row = conn.execute(
            "SELECT id FROM file WHERE project_id = ? AND path = ?",
            (project_id, value),
        ).fetchone()
        if not row:
            return []
        file_id = int(row[0])
        module_row = conn.execute(
            "SELECT id FROM module WHERE project_id = ? AND file_id = ?",
            (project_id, file_id),
        ).fetchone()
        note = "设计说明提到该文件"
        if module_row:
            return [(int(module_row[0]), value, None, note)]
        return [(None, value, None, note)]

    if claim.get("kind") == "symbol":
        rows = conn.execute(
            """
            SELECT s.id, f.path, s.lineno FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE s.project_id = ?
              AND (s.qualname = ? OR s.qualname LIKE ? OR s.name = ?)
            LIMIT 5
            """,
            (project_id, value, f"%.{value}", value),
        ).fetchall()
        return [(int(r[0]), r[1], int(r[2]), "设计说明提到该符号") for r in rows]

    return []


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
