"""在隔离库构建索引，只在最终发布时占用主库写事务。"""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from codeinsight.cognitive.indexing.source_store import cache_path, store_bytes
from codeinsight.storage.sqlite import open_sqlite

_TABLES = (
    "file",
    "module",
    "symbol",
    "dependency",
    "entry_point",
    "edge",
    "flow",
    "flow_step",
    "design_decision",
    "design_decision_evidence",
    "concept_instance",
    "chunk",
)


def _rows(conn: sqlite3.Connection, table: str, pid: int) -> list[dict]:
    if table == "flow_step":
        where = "flow_id IN (SELECT id FROM flow WHERE project_id=?)"
    elif table == "design_decision_evidence":
        where = "decision_id IN (SELECT id FROM design_decision WHERE project_id=?)"
    elif table == "embedding":
        where = "chunk_id IN (SELECT id FROM chunk WHERE project_id=?)"
    else:
        where = "project_id=?"
    cursor = conn.execute(f"SELECT * FROM {table} WHERE {where}", (pid,))
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor]


def _identity(conn: sqlite3.Connection, pid: int) -> tuple:
    row = conn.execute(
        "SELECT p.root_path,r.head_commit,r.index_epoch,r.parser_version,r.concept_version "
        "FROM project p LEFT JOIN repo_state r ON r.project_id=p.id WHERE p.id=?",
        (pid,),
    ).fetchone()
    return tuple(row) if row else ()


def _insert(conn: sqlite3.Connection, table: str, row: dict, *, upsert: bool = False) -> None:
    columns = list(row)
    suffix = (
        " ON CONFLICT DO UPDATE SET " + ",".join(f"{c}=excluded.{c}" for c in columns)
        if upsert
        else ""
    )
    conn.execute(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}){suffix}",
        tuple(row.values()),
    )


def build_and_publish_index(
    conn: sqlite3.Connection,
    project_id: int,
    root_path: str | Path,
    ref: str | None = None,
    **options: Any,
) -> dict:
    """构建失败或源索引变化时不发布；会话、任务和工作区快照绝不被副本覆盖。

    调用者必须先提交项目/运行预留记录。索引来源字节先保存，元数据随后原子发布。
    """
    from codeinsight.cognitive.indexing.indexer import run_index

    if conn.in_transaction:
        raise ValueError("构建索引前必须提交预留事务")
    database = next(row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main")
    if not database:
        raise ValueError("隔离索引需要持久化数据库")
    with tempfile.TemporaryDirectory(prefix="index-stage-", dir=Path(database).parent) as directory:
        with closing(open_sqlite(Path(directory) / "index.db")) as stage:
            conn.backup(stage)
            identity = _identity(stage, project_id)
            baseline = {t: {r["id"] for r in _rows(stage, t, project_id)} for t in _TABLES}
            append_tables = ("change_record", "staleness_report")
            old_ids = {t: {r["id"] for r in _rows(stage, t, project_id)} for t in append_tables}
            stats = run_index(stage, project_id, root_path, ref, **options)
            stage.commit()
            data = {
                t: _rows(stage, t, project_id)
                for t in (*_TABLES, "embedding", "repo_state", "file_snapshot", "test_record")
            }
            for row in data["file"]:
                source = cache_path(stage, row["content_sha256"])
                if source and source.exists():
                    store_bytes(conn, source.read_bytes())
            conn.execute("BEGIN IMMEDIATE")
            try:
                if _identity(conn, project_id) != identity:
                    raise RuntimeError("项目索引或源码目录已变化，本次构建未覆盖新状态，请重试。")
                conn.execute("PRAGMA defer_foreign_keys=ON")
                mappings = {}
                for table in _TABLES:
                    occupied = {r[0] for r in conn.execute(f"SELECT id FROM {table}")}
                    next_id = max(occupied | {r["id"] for r in data[table]}, default=0)
                    mapping = {}
                    for row in data[table]:
                        current = row["id"]
                        if current in occupied and current not in baseline[table]:
                            next_id += 1
                            mapping[current] = next_id
                        else:
                            mapping[current] = current
                    mappings[table] = mapping
                from codeinsight.cognitive.indexing.indexer import _clear_project_data

                _clear_project_data(conn, project_id, commit=False)
                conn.execute("DELETE FROM concept_instance WHERE project_id=?", (project_id,))
                for table in ("concept", "embedding_model"):
                    cursor = stage.execute(f"SELECT * FROM {table}")
                    columns = [c[0] for c in cursor.description]
                    for values in cursor:
                        _insert(conn, table, dict(zip(columns, values, strict=True)), upsert=True)
                for table in (*_TABLES, "embedding"):
                    foreign = {
                        r[3]: r[2] for r in stage.execute(f"PRAGMA foreign_key_list({table})")
                    }
                    for row in data[table]:
                        row = dict(row)
                        if table in mappings:
                            row["id"] = mappings[table][row["id"]]
                        for column, parent in foreign.items():
                            if parent in mappings and row.get(column) is not None:
                                row[column] = mappings[parent][row[column]]
                        _insert(conn, table, row)
                for row in data["repo_state"]:
                    if row["concept_version"]:
                        fingerprint = stage.execute(
                            "SELECT fingerprint FROM concept_rule_version WHERE id=?",
                            (row["concept_version"],),
                        ).fetchone()[0]
                        conn.execute(
                            "INSERT OR IGNORE INTO concept_rule_version(fingerprint) VALUES(?)",
                            (fingerprint,),
                        )
                        row["concept_version"] = conn.execute(
                            "SELECT id FROM concept_rule_version WHERE fingerprint=?",
                            (fingerprint,),
                        ).fetchone()[0]
                    _insert(conn, "repo_state", row, upsert=True)
                for row in data["file_snapshot"]:
                    _insert(conn, "file_snapshot", row, upsert=True)
                for table in append_tables:
                    for row in _rows(stage, table, project_id):
                        if row["id"] not in old_ids[table]:
                            row.pop("id")
                            _insert(conn, table, row)
                # 删除再发布会触发SET NULL；仅恢复副本中仍有效的既有测试关联。
                for row in data["test_record"]:
                    if row["symbol_id"] in mappings["symbol"]:
                        conn.execute(
                            "UPDATE test_record SET symbol_id=? WHERE id=? AND project_id=? AND symbol_id IS NULL",
                            (mappings["symbol"][row["symbol_id"]], row["id"], project_id),
                        )
                conn.execute(
                    "UPDATE project SET root_path=? WHERE id=?", (str(root_path), project_id)
                )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            return stats
