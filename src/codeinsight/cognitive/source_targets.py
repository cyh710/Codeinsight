"""代码位置的版本身份由服务端一次生成，调用方不重新拼接。"""

from __future__ import annotations

import sqlite3
from typing import Any


def begin_read(conn: sqlite3.Connection) -> None:
    """固定对象和来源元数据的读取快照；不提交调用者已有事务。"""
    if not conn.in_transaction:
        conn.execute("BEGIN")


def indexed_target(
    conn: sqlite3.Connection, pid: int, path: str, line: int, end: int | None = None
) -> dict | None:
    """同一次查询取得文件和索引身份；缺少记录不补造版本。"""
    row = conn.execute(
        "SELECT f.content_sha256,f.line_count,r.head_commit,r.index_epoch FROM file f "
        "JOIN repo_state r ON r.project_id=f.project_id WHERE f.project_id=? AND f.path=?",
        (pid, path),
    ).fetchone()
    if not row or not row[0] or type(line) is not int or line < 1 or line > max(1, row[1] or 0):
        return None
    return {
        "kind": "code",
        "project_id": pid,
        "path": path,
        "lineno": line,
        "end_lineno": min(end or line, line + 199, max(1, row[1] or 0)),
        "source_kind": "index",
        "content_sha256": row[0],
        "head_commit": row[2],
        "index_epoch": row[3],
    }


def citation_target(pid: int, raw: dict) -> dict | None:
    """只投影已有身份，不从全局最新索引为旧记录补版本。"""
    if not raw.get("path") or type(raw.get("lineno")) is not int:
        return None
    if raw.get("source_kind") == "workspace":
        if not raw.get("content_sha256"):
            return None
    elif not raw.get("index_epoch") and not raw.get("head_commit"):
        return None
    return {
        "kind": "code",
        "project_id": pid,
        **{
            k: raw[k]
            for k in (
                "path",
                "lineno",
                "end_lineno",
                "source_kind",
                "content_sha256",
                "index_epoch",
                "head_commit",
                "qualname",
            )
            if raw.get(k) is not None
        },
    }


def attach_targets(conn: sqlite3.Connection, pid: int, value: Any) -> Any:
    """仅用于当前索引的API投影；历史答案必须使用自身已保存的身份。"""
    if isinstance(value, list):
        return [attach_targets(conn, pid, item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {k: attach_targets(conn, pid, v) if k != "target" else v for k, v in value.items()}
    if (
        isinstance(result.get("path"), str)
        and type(result.get("lineno")) is int
        and "target" not in result
    ):
        result["target"] = indexed_target(
            conn, pid, result["path"], result["lineno"], result.get("end_lineno")
        )
        if result["target"] and result.get("qualname"):
            result["target"]["qualname"] = result["qualname"]
    return result
