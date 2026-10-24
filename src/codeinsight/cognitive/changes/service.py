"""变更说明的读取侧（契约 §7.1）。

增量索引写 `change_record`，这里把它读成契约形状。**不重新分析**：
写的时候是什么，读出来就是什么。两处各算一遍必然漂移，
而漂移过的「变更说明」比没有更糟——用户没法知道该信哪个。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from codeinsight.cognitive.changes.staleness import latest_stale_decisions

MAX_TESTS = 50


def _load(raw: str | None) -> dict:
    if not raw:
        return {"files": [], "symbols": []}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"files": [], "symbols": []}
    if isinstance(value, list):  # 兼容早期只存路径列表的写法
        return {"files": value, "symbols": []}
    return {"files": value.get("files", []), "symbols": value.get("symbols", [])}


def build_changes(
    conn: sqlite3.Connection, project_id: int, *, since: str | None = None
) -> dict[str, Any]:
    """最近一次变更的完整说明；没有任何变更记录时返回空壳（形状不变）。"""
    params: list[Any] = [project_id]
    where = "WHERE project_id = ?"
    if since:
        where += " AND commit_sha = ?"
        params.append(since)
    row = conn.execute(
        f"SELECT id, commit_sha, summary, added_json, removed_json, modified_json, impact_json"
        f" FROM change_record {where} ORDER BY id DESC LIMIT 1",
        tuple(params),
    ).fetchone()
    if row is None:
        return _empty(conn, project_id, since)

    record_id, head, summary, added_raw, removed_raw, modified_raw, impact_raw = row
    # `since` 优先取这次索引的**基准 commit**（index_run.base_commit）；
    # 没有记录时才退回「上一条变更记录的 commit」。两者在正常情况下相同，
    # 但倒退重跑索引时只有前者是对的。
    base = conn.execute(
        "SELECT base_commit FROM index_run WHERE project_id = ? AND head_commit = ?"
        " AND base_commit IS NOT NULL ORDER BY id DESC LIMIT 1",
        (project_id, head),
    ).fetchone()
    if base is None or not base[0]:
        base = conn.execute(
            "SELECT commit_sha FROM change_record WHERE project_id = ? AND id < ?"
            " ORDER BY id DESC LIMIT 1",
            (project_id, record_id),
        ).fetchone()
    base_commit = str(base[0]) if base and base[0] else ""

    added = _load(added_raw)
    removed = _load(removed_raw)
    modified = _load(modified_raw)
    try:
        impact = json.loads(impact_raw) if impact_raw else {}
    except json.JSONDecodeError:
        impact = {}

    modified_count: dict[str, int] = {}
    for symbol in modified["symbols"]:
        path = symbol.get("path")
        if path:
            modified_count[path] = modified_count.get(path, 0) + 1

    tests = [
        {"nodeid": row[0], "outcome": row[1], "duration_s": float(row[2] or 0.0)}
        for row in conn.execute(
            "SELECT nodeid, outcome, duration_s FROM test_record"
            " WHERE project_id = ? ORDER BY id DESC LIMIT ?",
            (project_id, MAX_TESTS),
        ).fetchall()
    ]

    return {
        "since": base_commit,
        "head": str(head or ""),
        "summary": summary or "",
        "files": {
            "added": [{"path": p, "status": "A"} for p in added["files"]],
            "modified": [
                {"path": p, "status": "M", "changed_symbols": modified_count.get(p, 0)}
                for p in modified["files"]
            ],
            "deleted": [{"path": p, "status": "D"} for p in removed["files"]],
        },
        "changed_symbols": [
            {
                "qualname": symbol["qualname"],
                "path": symbol["path"],
                "lineno": int(symbol.get("lineno") or 0),
                "change": symbol["change"],
            }
            for group in (added, removed, modified)
            for symbol in group["symbols"]
        ],
        "impacted": {
            "modules": impact.get("modules", []),
            "symbols": impact.get("symbols", []),
            "concept_ids": impact.get("concept_ids", []),
        },
        "tests": tests,
        # 读**索引时写下的报告**，不在读路径重算——两处各算一遍必然漂移。
        "stale_design_decisions": latest_stale_decisions(conn, project_id=project_id),
    }


def _empty(conn: sqlite3.Connection, project_id: int, since: str | None) -> dict[str, Any]:
    state = conn.execute(
        "SELECT head_commit FROM repo_state WHERE project_id = ?", (project_id,)
    ).fetchone()
    return {
        "since": since or "",
        "head": str(state[0]) if state and state[0] else "",
        "summary": "",
        "files": {"added": [], "modified": [], "deleted": []},
        "changed_symbols": [],
        "impacted": {"modules": [], "symbols": [], "concept_ids": []},
        "tests": [],
        "stale_design_decisions": [],
    }


def record_test_results(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    nodeid: str,
    outcome: str,
    duration_s: float = 0.0,
    message: str = "",
    commit_sha: str | None = None,
    symbol_id: int | None = None,
) -> None:
    """把一条测试结果落库（§2.5-6「关联相关测试结果」）。

    测试**由外部 agent 跑**，CodeInsight 只记录结果——
    执行侧不在这里（ADR 0008）。
    """
    conn.execute(
        """
        INSERT INTO test_record (project_id, commit_sha, nodeid, outcome, duration_s,
                                 message, symbol_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, commit_sha, nodeid, outcome, float(duration_s), message or None, symbol_id),
    )
