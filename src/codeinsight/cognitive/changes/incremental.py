"""增量索引：只重算变了的文件与符号（源文档 §2.4 / §2.5）。

**为什么不是「重新全量跑一遍」**：全量会把每个块的 `source_sha256`
都重写一遍，于是「哪些知识过期了」这个问题永远得不到答案——
所有东西看起来都是新的。增量让**没变的行一行都不动**，
过期判断、变更说明、影响范围才有对象。

几个必须做对的地方：

1. **符号 id 要尽量保留**。改一个函数体不等于「删掉一个符号再加一个」：
   id 一变，别的文件指向它的边全断（CASCADE），调用图和影响范围当场失真。
   所以按 `(file_id, qualname)` 原地 UPDATE，只对真的消失的符号做删除。
2. **块的哈希才是精确层**。符号没变 → 块不动（连 id 都不变，向量还能复用）；
   只挪了行号 → 平移块的 `lineno`，不重写内容。
3. **删掉的符号先记下调用者**。它的入边会随 CASCADE 一起消失，
   事后再查就查不到「谁曾经在用它」——而这正是删除时最该告诉用户的事。
4. **全局派生表照常重建**（入口、流程、依赖、设计说明）。
   它们体量小、依赖全局视图，逐文件增量维护的复杂度不值得。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

from codeinsight.cognitive.changes.git_source import GitDiffSource
from codeinsight.cognitive.changes.impact import callers_of_qualnames, reverse_impact
from codeinsight.cognitive.changes.staleness import (
    decisions_losing_evidence,
    evidence_counts,
    latest_stale_decisions,
    record_report,
)
from codeinsight.cognitive.indexing.design_docs import parse_design_docs
from codeinsight.cognitive.indexing.edges import (
    EdgeResolver,
    FileSymbolScope,
    build_bindings,
    write_edges,
)
from codeinsight.cognitive.indexing.entries import DependencySpec  # noqa: F401 —— 类型注记
from codeinsight.cognitive.indexing.indexer import (
    _INDEXED_FILE_ROLES,
    PARSER_VERSION,
    _embed_chunks,
    _resolve_commit,
    _write_chunks,
    _write_dependencies,
    _write_design_decisions,
    _write_entry_points,
    _write_file,
    _write_flows,
)
from codeinsight.cognitive.indexing.scanner import list_repo_files, module_qualname, read_blobs
from codeinsight.cognitive.indexing.symbols import (
    SymbolIndex,
    sha256_text,
    symbol_source,
    write_module,
)
from codeinsight.cognitive.parsing.base import ParseContext
from codeinsight.cognitive.parsing.python_parser import PythonParser

_CHANGE_ORDER = (
    "signature_changed",
    "body_changed",
    "docstring_changed",
    "moved",
)
"""一个符号只报**最强**的那种变化。签名变了又挪了行，就是签名变了。"""


@dataclass
class SymbolChange:
    qualname: str
    path: str
    lineno: int
    change: str
    symbol_id: int | None = None


@dataclass
class IncrementalPlan:
    old_commit: str
    new_commit: str
    branch: str
    added: list[str]
    modified: list[str]
    deleted: list[str]


def plan_incremental(
    conn: sqlite3.Connection, project_id: int, root: Path, ref: str | None
) -> IncrementalPlan | None:
    """能不能增量。不能就返回 None，由调用方退回全量。

    三种情况必须全量：没有上一位点、历史被改写、解析器换了版本。
    最后一条容易被忽略——解析器升级后旧符号的形状就是错的，
    继续拿它做增量等于把新解析器的结果和老结果混在一起。
    """
    source = GitDiffSource(root)
    try:
        new_commit, branch = _resolve_commit(root, ref)
    except Exception:  # noqa: BLE001 —— 非 git 目录等：交给全量路径报错
        return None
    row = conn.execute(
        "SELECT head_commit, parser_version FROM repo_state WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if row is None or not row[0] or row[1] != PARSER_VERSION:
        return None
    old_commit = str(row[0])
    if old_commit == new_commit:
        return IncrementalPlan(old_commit, new_commit, branch, [], [], [])
    if not source.is_ancestor(old_commit, new_commit):
        return None
    changes = source.changed_files(old_commit, new_commit)
    return IncrementalPlan(
        old_commit=old_commit,
        new_commit=new_commit,
        branch=branch,
        added=[c.path for c in changes if c.status == "added"],
        modified=[c.path for c in changes if c.status == "modified"],
        deleted=[c.path for c in changes if c.status == "deleted"],
    )


def run_incremental(
    conn: sqlite3.Connection,
    project_id: int,
    root_path: str | Path,
    ref: str | None = None,
    *,
    max_chunk_lines: int,
    embed: bool = False,
    concepts_dir: str | Path | None = None,
) -> dict | None:
    """执行增量索引。返回与 `run_index` 同形状的统计；不能增量时返回 None。"""
    root = Path(root_path)
    plan = plan_incremental(conn, project_id, root, ref)
    if plan is None:
        return None
    if not (plan.added or plan.modified or plan.deleted):
        return _stats(conn, project_id, plan, changes=[])

    files_now = {f.path: f for f in list_repo_files(root, ref=ref)}
    touched = [p for p in (*plan.added, *plan.modified) if p in files_now]

    # **必须最先取**：删符号会 CASCADE 掉 design_decision_evidence，
    # 等重建证据时再数「原来有几条」，答案永远是 0。
    prior_evidence = evidence_counts(conn, project_id=project_id)
    snapshots = _snapshot_symbols(conn, project_id, [*plan.modified, *plan.deleted])
    old_qualnames = [row["qualname"] for rows in snapshots.values() for row in rows.values()]
    callers_before = callers_of_qualnames(conn, project_id=project_id, qualnames=old_qualnames)

    for path in plan.deleted:
        conn.execute("DELETE FROM file WHERE project_id = ? AND path = ?", (project_id, path))

    blobs = read_blobs(root, ref=ref, paths=touched)
    parser = PythonParser()
    entries = []
    symbol_changes: list[SymbolChange] = []
    kept_chunks = 0
    skipped = 0

    for path in touched:
        repo_file = files_now[path]
        if repo_file.role not in _INDEXED_FILE_ROLES:
            conn.execute("DELETE FROM file WHERE project_id = ? AND path = ?", (project_id, path))
            continue
        raw = blobs.get(path)
        if raw is None:
            skipped += 1
            continue
        digest = hashlib.sha256(raw).hexdigest()
        line_count = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
        file_id = _upsert_file(conn, project_id, repo_file, digest, line_count)

        if not parser.supports(path):
            continue
        source_text = raw.decode("utf-8", "replace")
        source_lines = source_text.splitlines()
        parsed = parser.parse(
            path, source_text, ParseContext(project_id=project_id, repo_root=str(root))
        )
        if not parsed.symbols and source_text.strip():
            # 语法错误：旧符号必须清掉，否则索引里留着已经不存在的东西。
            conn.execute("DELETE FROM symbol WHERE file_id = ?", (file_id,))
            skipped += 1
            continue

        module = module_qualname(path)
        module_id = write_module(
            conn,
            project_id=project_id,
            file_id=file_id,
            qualname=module,
            docstring=getattr(parsed, "module_docstring", None),
        )
        before = snapshots.get(path, {})
        ids, changes, kept = _upsert_symbols(
            conn,
            project_id=project_id,
            file_id=file_id,
            module_id=module_id,
            module=module,
            path=path,
            parsed=parsed,
            source_lines=source_lines,
            before=before,
            file_digest=digest,
            max_chunk_lines=max_chunk_lines,
        )
        kept_chunks += kept
        symbol_changes.extend(changes)
        # 粗筛层跟着文件走：块内容没变（source_sha256 不动），
        # 但「这个块属于哪一版文件」变了——不更新会让过期检测误报。
        conn.execute(
            "UPDATE chunk SET file_content_sha256 = ? WHERE file_id = ?", (digest, file_id)
        )
        entries.append((path, module, parsed, source_lines, ids))

    _rewrite_edges(conn, project_id, entries)

    # ── 全局派生表 ──────────────────────────────────────────────
    all_files = list_repo_files(root, ref=ref)
    indexed_files = [f for f in all_files if f.role in _INDEXED_FILE_ROLES]
    all_blobs = read_blobs(root, ref=ref, paths=[f.path for f in indexed_files])
    all_sources = {
        path: blob.decode("utf-8", "replace") for path, blob in all_blobs.items()
    }
    # 全局派生表是「重算」而不是「叠加」：先清空，再写。
    # 全量路径靠 `_clear_project_data` 做这件事；增量必须自己补上，
    # 否则 entry_point / flow 会撞 UNIQUE，design_decision_evidence 会越写越多。
    conn.execute("DELETE FROM entry_point WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM flow WHERE project_id = ?", (project_id,))
    conn.execute(
        "DELETE FROM design_decision_evidence WHERE decision_id IN"
        " (SELECT id FROM design_decision WHERE project_id = ?)",
        (project_id,),
    )
    entry_specs = _write_entry_points(
        conn,
        project_id=project_id,
        root=root,
        files=[f.path for f in indexed_files],
        sources=all_sources,
    )
    _write_flows(conn, project_id=project_id, entry_specs=entry_specs)
    _write_design_decisions(
        conn,
        project_id=project_id,
        docs=parse_design_docs(
            [f.path for f in indexed_files],
            {p: s for p, s in all_sources.items() if p.endswith(".md")},
        ),
    )
    stale_decisions = decisions_losing_evidence(
        conn, project_id=project_id, prior=prior_evidence
    )
    total_chunks = int(
        conn.execute(
            "SELECT COUNT(*) FROM chunk WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
    )
    record_report(
        conn,
        project_id=project_id,
        commit_sha=plan.new_commit,
        total_chunks=total_chunks,
        design_decisions=stale_decisions,
    )
    imported = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT dst_name FROM edge WHERE project_id = ? AND kind = 'imports'",
            (project_id,),
        ).fetchall()
    ]
    _write_dependencies(
        conn,
        project_id=project_id,
        root=root,
        indexed=indexed_files,
        imported_modules=imported,
        local_packages={module_qualname(f.path).split(".")[0] for f in indexed_files},
    )

    concepts = instances = 0
    if concepts_dir:
        from codeinsight.cognitive.indexing.concepts_sync import sync_concepts

        sync = sync_concepts(
            conn, project_id=project_id, knowledge_dir=concepts_dir, sources=all_sources
        )
        concepts, instances = sync.concepts, sync.instances

    if embed:
        _embed_chunks(conn, project_id=project_id)

    # ── 变更记录 ────────────────────────────────────────────────
    changed_ids = [c.symbol_id for c in symbol_changes if c.symbol_id is not None]
    extra_seeds = [c.qualname for c in symbol_changes if c.change == "removed"]
    impact = reverse_impact(
        conn,
        project_id=project_id,
        seed_symbol_ids=changed_ids,
        seed_qualnames=[*callers_before, *extra_seeds],
    )
    record_change(
        conn,
        project_id=project_id,
        plan=plan,
        symbol_changes=symbol_changes,
        impact=impact.as_dict(),
    )

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
        (project_id, plan.new_commit, plan.branch, PARSER_VERSION, next_epoch),
    )
    conn.commit()

    stats = _stats(conn, project_id, plan, changes=symbol_changes)
    stats.update(
        {
            "kept_chunks_reused": kept_chunks,
            "skipped": skipped,
            "concepts": concepts,
            "concept_instances": instances,
        }
    )
    return stats


# ── 文件与符号 ────────────────────────────────────────────────


def _upsert_file(
    conn: sqlite3.Connection, project_id: int, repo_file, digest: str, line_count: int
) -> int:
    row = conn.execute(
        "SELECT id FROM file WHERE project_id = ? AND path = ?", (project_id, repo_file.path)
    ).fetchone()
    if row is None:
        return _write_file(
            conn,
            project_id=project_id,
            repo_file=repo_file,
            content_sha256=digest,
            line_count=line_count,
        )
    file_id = int(row[0])
    conn.execute(
        """
        UPDATE file SET blob_sha = ?, content_sha256 = ?, size_bytes = ?, line_count = ?,
                        role = ?, in_index = ?
        WHERE id = ?
        """,
        (
            repo_file.blob_sha,
            digest,
            repo_file.size_bytes,
            line_count,
            repo_file.role,
            int(repo_file.in_index),
            file_id,
        ),
    )
    return file_id


def _snapshot_symbols(
    conn: sqlite3.Connection, project_id: int, paths: list[str]
) -> dict[str, dict[str, dict]]:
    """改动前的符号快照。用位置取值——引擎里的连接不保证 row_factory。"""
    snapshots: dict[str, dict[str, dict]] = {}
    for path in paths:
        rows = conn.execute(
            """
            SELECT s.id, s.qualname, s.lineno, s.end_lineno, s.header,
                   COALESCE(s.docstring, ''), s.source_sha256
            FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE f.project_id = ? AND f.path = ?
            """,
            (project_id, path),
        ).fetchall()
        snapshots[path] = {
            row[1]: {
                "id": int(row[0]),
                "qualname": row[1],
                "lineno": int(row[2]),
                "end_lineno": int(row[3]),
                "header": row[4] or "",
                "docstring": row[5] or "",
                "source_sha256": row[6],
            }
            for row in rows
        }
    return snapshots


def _upsert_symbols(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    file_id: int,
    module_id: int | None,
    module: str,
    path: str,
    parsed,
    source_lines: list[str],
    before: dict[str, sqlite3.Row],
    file_digest: str,
    max_chunk_lines: int,
) -> tuple[list[int], list[SymbolChange], int]:
    ids: list[int] = []
    changes: list[SymbolChange] = []
    kept = 0

    for symbol in parsed.symbols:
        text = symbol_source(source_lines, symbol.lineno, symbol.end_lineno)
        digest = sha256_text(text)
        row = before.get(symbol.qualname)
        if row is None:
            symbol_id = _insert_symbol(
                conn, project_id, file_id, module_id, symbol, digest
            )
            _write_symbol_chunks(
                conn, project_id, file_id, file_digest, parsed, symbol, symbol_id,
                source_lines, max_chunk_lines,
            )
            changes.append(SymbolChange(symbol.qualname, path, symbol.lineno, "added", symbol_id))
            ids.append(symbol_id)
            continue

        symbol_id = int(row["id"])
        ids.append(symbol_id)
        content_changed = row["source_sha256"] != digest
        header_changed = (row["header"] or "") != (symbol.header or "")
        doc_changed = (row["docstring"] or "") != (symbol.docstring or "")
        moved = (int(row["lineno"]), int(row["end_lineno"])) != (symbol.lineno, symbol.end_lineno)

        if not (content_changed or moved):
            kept += 1
            continue

        conn.execute(
            """
            UPDATE symbol SET lineno = ?, end_lineno = ?, header = ?, docstring = ?,
                              kind = ?, is_async = ?, is_private = ?, is_dunder = ?,
                              n_lines = ?, source_sha256 = ?
            WHERE id = ?
            """,
            (
                symbol.lineno,
                symbol.end_lineno,
                symbol.header,
                symbol.docstring,
                str(symbol.kind),
                int(symbol.is_async),
                int(symbol.is_private),
                int(symbol.is_dunder),
                symbol.n_lines,
                digest,
                symbol_id,
            ),
        )
        if content_changed:
            conn.execute("DELETE FROM chunk WHERE symbol_id = ?", (symbol_id,))
            _write_symbol_chunks(
                conn, project_id, file_id, file_digest, parsed, symbol, symbol_id,
                source_lines, max_chunk_lines,
            )
        elif moved:
            delta = symbol.lineno - int(row["lineno"])
            conn.execute(
                "UPDATE chunk SET lineno = lineno + ?, end_lineno = end_lineno + ?"
                " WHERE symbol_id = ?",
                (delta, delta, symbol_id),
            )

        if header_changed:
            kind = "signature_changed"
        elif content_changed:
            kind = "body_changed"
        elif doc_changed:
            kind = "docstring_changed"
        else:
            kind = "moved"
        changes.append(SymbolChange(symbol.qualname, path, symbol.lineno, kind, symbol_id))

    # 消失的符号
    present = {symbol.qualname for symbol in parsed.symbols}
    for qualname, row in before.items():
        if qualname in present:
            continue
        conn.execute("DELETE FROM symbol WHERE id = ?", (int(row["id"]),))
        changes.append(SymbolChange(qualname, path, int(row["lineno"]), "removed", None))

    _backfill_parents(conn, project_id=project_id, file_id=file_id, parsed=parsed)
    return ids, changes, kept


def _insert_symbol(
    conn: sqlite3.Connection, project_id: int, file_id: int, module_id: int | None, symbol, digest: str
) -> int:
    cur = conn.execute(
        """
        INSERT INTO symbol (
            project_id, file_id, module_id, qualname, name, kind, lineno, end_lineno,
            header, docstring, is_async, is_private, is_dunder, n_lines, source_sha256
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            file_id,
            module_id,
            symbol.qualname,
            symbol.name,
            str(symbol.kind),
            symbol.lineno,
            symbol.end_lineno,
            symbol.header,
            symbol.docstring,
            int(symbol.is_async),
            int(symbol.is_private),
            int(symbol.is_dunder),
            symbol.n_lines,
            digest,
        ),
    )
    return int(cur.lastrowid or 0)


def _write_symbol_chunks(
    conn: sqlite3.Connection,
    project_id: int,
    file_id: int,
    file_digest: str,
    parsed,
    symbol,
    symbol_id: int,
    source_lines: list[str],
    max_chunk_lines: int,
) -> None:
    single = replace(parsed, symbols=(symbol,))
    _write_chunks(
        conn,
        project_id=project_id,
        file_id=file_id,
        file_content_sha256=file_digest,
        parsed=single,
        source_lines=source_lines,
        symbol_ids=[symbol_id],
        max_lines=max_chunk_lines,
    )


def _backfill_parents(
    conn: sqlite3.Connection, *, project_id: int, file_id: int, parsed
) -> None:
    ids = {
        row[0]: int(row[1])
        for row in conn.execute(
            "SELECT qualname, id FROM symbol WHERE project_id = ? AND file_id = ?",
            (project_id, file_id),
        ).fetchall()
    }
    for symbol in parsed.symbols:
        parent = symbol.parent_qualname
        child_id = ids.get(symbol.qualname)
        if not parent or child_id is None or parent not in ids:
            continue
        conn.execute(
            "UPDATE symbol SET parent_symbol_id = ? WHERE id = ?", (ids[parent], child_id)
        )


# ── 边 ────────────────────────────────────────────────────────


def _rewrite_edges(conn: sqlite3.Connection, project_id: int, entries) -> None:
    """重写**改动文件**的边；未改文件指向保留 id 的边原样保留。"""
    if not entries:
        return
    index = _rebuild_symbol_index(conn, project_id)
    bindings = {
        module: build_bindings(parsed.imports) for _, module, parsed, _, _ in entries
    }
    resolver = EdgeResolver(index, bindings)
    for path, module, parsed, _, _ in entries:
        rows = conn.execute(
            """
            SELECT s.id, s.qualname, s.lineno, s.end_lineno
            FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE f.project_id = ? AND f.path = ?
            """,
            (project_id, path),
        ).fetchall()
        if not rows:
            continue
        scope = FileSymbolScope()
        scope.entries = [
            (row[1], int(row[2]), int(row[3]), int(row[0])) for row in rows
        ]
        ids = [int(row[0]) for row in rows]
        marks = ",".join("?" for _ in ids)
        conn.execute(
            f"DELETE FROM edge WHERE project_id = ? AND src_symbol_id IN ({marks})",
            (project_id, *ids),
        )
        write_edges(
            conn,
            project_id=project_id,
            scope=scope,
            edges=list(parsed.edges),
            resolver=resolver,
            src_modules={symbol.qualname: module for symbol in parsed.symbols},
        )
    del index


def _rebuild_symbol_index(conn: sqlite3.Connection, project_id: int) -> SymbolIndex:
    index = SymbolIndex()
    rows = conn.execute(
        """
        SELECT s.id, s.qualname, s.name, m.qualname
        FROM symbol s LEFT JOIN module m ON m.id = s.module_id
        WHERE s.project_id = ?
        """,
        (project_id,),
    ).fetchall()
    for symbol_id, qualname, name, module in rows:
        if not module:
            continue
        index.add(qualname, name, int(symbol_id), module)
        if qualname.startswith(f"{module}.") and qualname.count(".") == module.count(".") + 1:
            index.module_symbols.setdefault(module, {}).setdefault(name, []).append(int(symbol_id))
    return index


# ── 记录与统计 ────────────────────────────────────────────────


def record_change(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    plan: IncrementalPlan,
    symbol_changes: list[SymbolChange],
    impact: dict,
) -> int:
    # 分门别类存**完整**的符号信息（qualname / path / lineno / change）。
    # 只存名字的话，读的人还得回表猜行号——而那个行号可能已经变了。
    def entry(change: SymbolChange) -> dict:
        return {
            "qualname": change.qualname,
            "path": change.path,
            "lineno": change.lineno,
            "change": change.change,
        }

    added_symbols = [entry(c) for c in symbol_changes if c.change == "added"]
    removed_symbols = [entry(c) for c in symbol_changes if c.change == "removed"]
    modified_symbols = [
        entry(c) for c in symbol_changes if c.change not in {"added", "removed"}
    ]
    summary = (
        f"本次更新新增 {len(plan.added)} 个文件、修改 {len(plan.modified)} 个、"
        f"删除 {len(plan.deleted)} 个；{len(symbol_changes)} 个符号发生变化。"
    )
    cur = conn.execute(
        """
        INSERT INTO change_record (project_id, commit_sha, source, summary, occurred_at,
                                   added_json, removed_json, modified_json, impact_json)
        VALUES (?, ?, 'git', ?, datetime('now'), ?, ?, ?, ?)
        """,
        (
            project_id,
            plan.new_commit,
            summary,
            _json({"files": plan.added, "symbols": added_symbols}),
            _json({"files": plan.deleted, "symbols": removed_symbols}),
            _json({"files": plan.modified, "symbols": modified_symbols}),
            _json(impact),
        ),
    )
    return int(cur.lastrowid or 0)


def _json(value) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _stats(
    conn: sqlite3.Connection, project_id: int, plan: IncrementalPlan, *, changes: list[SymbolChange]
) -> dict:
    def count(table: str) -> int:
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE project_id = ?", (project_id,)
            ).fetchone()[0]
        )

    def count_edges(resolved: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM edge WHERE project_id = ?"
        if resolved:
            sql += " AND dst_symbol_id IS NOT NULL"
        return int(conn.execute(sql, (project_id,)).fetchone()[0])

    epoch = conn.execute(
        "SELECT index_epoch FROM repo_state WHERE project_id = ?", (project_id,)
    ).fetchone()
    return {
        "head_commit": plan.new_commit,
        "head_branch": plan.branch,
        "files": count("file"),
        "modules": count("module"),
        "symbols": count("symbol"),
        "edges": count_edges(),
        "resolved_edges": count_edges(resolved=True),
        "entry_points": count("entry_point"),
        "flows": count("flow"),
        "design_decisions": count("design_decision"),
        "dependencies": count("dependency"),
        "skipped": 0,
        "chunks": count("chunk"),
        "embedded": 0,
        # `concept` 是全局本体表（没有 project_id），实例才按项目分。
        "concepts": int(conn.execute("SELECT COUNT(*) FROM concept").fetchone()[0]),
        "concept_instances": count("concept_instance"),
        "changed_symbols": len(changes),
        "index_epoch": int(epoch[0]) if epoch else 0,
        "parser_version": PARSER_VERSION,
        "stale_design_decisions": len(
            latest_stale_decisions(conn, project_id=project_id)
        ),
    }
