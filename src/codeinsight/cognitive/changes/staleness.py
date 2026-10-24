"""设计说明过期检测（源文档 §2.4 第 5 问）。

「哪些历史设计说明已不再适用」——代码会过期，**设计声明也会过期**。

判定只认一条**有前后对比**的证据：

    这条设计说明**上次**在代码里找得到落点，**这次**一个都找不到了。

为什么不直接拿 claim 去查当前索引：design 文档里反引号包着的东西
不全是符号——`assistant.tool_calls`、`tool.finished` 是事件名，
它们从来就不是 `symbol` 表里的一行。用「claim 查不到」当过期信号，
会让一批根本没变的 ADR 天天报「已过期」，用户很快就不再信任这个提示。

所以判据换成「**证据消失**」：

- 索引时 `design_decision_evidence` 记录了 claim 落到代码上的位置；
- 重新索引后，如果一条以前有证据的说明现在一条证据都没有了，
  说明它声称的机制从代码里消失了——这才是可报告的过期。

宁可漏报（机制换了个名字但还在），不可误报（文档没变却说它过期）。
"""

from __future__ import annotations

import json
import sqlite3

MAX_REPORTED = 10


def evidence_counts(conn: sqlite3.Connection, *, project_id: int) -> dict[int, int]:
    """每条设计说明当前有多少条证据。重写证据**之前**调用。"""
    rows = conn.execute(
        """
        SELECT d.id, COUNT(e.id)
        FROM design_decision d
        LEFT JOIN design_decision_evidence e ON e.decision_id = d.id
        WHERE d.project_id = ?
        GROUP BY d.id
        """,
        (project_id,),
    ).fetchall()
    return {int(row[0]): int(row[1]) for row in rows}


def decisions_losing_evidence(
    conn: sqlite3.Connection, *, project_id: int, prior: dict[int, int]
) -> list[dict]:
    """以前有证据、现在一条都没有的设计说明。"""
    stale: list[dict] = []
    if not prior:
        return stale
    for decision_id, before in prior.items():
        if before <= 0:
            continue
        row = conn.execute(
            "SELECT doc_id, title, claims_json FROM design_decision WHERE id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            continue  # 文档本身被删了，不算「过期」
        current = conn.execute(
            "SELECT COUNT(*) FROM design_decision_evidence WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()[0]
        if current:
            continue
        claims = _claims(row[2])
        listed = "、".join(
            f"{claim.get('kind')}={claim.get('value')}" for claim in claims[:3]
        )
        stale.append(
            {
                "doc_id": row[0],
                "title": row[1],
                "reason": (
                    f"上次索引时还能定位到 {before} 处证据，现在一处都没有了：{listed}"
                    if listed
                    else f"上次索引时还能定位到 {before} 处证据，现在一处都没有了"
                ),
            }
        )
        if len(stale) >= MAX_REPORTED:
            break
    return stale


def record_report(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    commit_sha: str,
    total_chunks: int,
    design_decisions: list[dict],
) -> None:
    """把本次的过期判定落 `staleness_report`（读侧直接取，不重算）。"""
    conn.execute(
        """
        INSERT INTO staleness_report (project_id, commit_sha, total_chunks,
                                      stale_chunks, stale_rate, by_reason)
        VALUES (?, ?, ?, 0, 0.0, ?)
        """,
        (
            project_id,
            commit_sha,
            total_chunks,
            json.dumps({"design_decisions": design_decisions}, ensure_ascii=False),
        ),
    )


def latest_stale_decisions(conn: sqlite3.Connection, *, project_id: int) -> list[dict]:
    """最近一次索引报告的过期设计说明。没有报告就是空——不猜。"""
    row = conn.execute(
        "SELECT by_reason FROM staleness_report WHERE project_id = ?"
        " ORDER BY id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row is None or not row[0]:
        return []
    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError:
        return []
    items = payload.get("design_decisions") if isinstance(payload, dict) else None
    return items if isinstance(items, list) else []


def _claims(raw: str | None) -> list[dict]:
    try:
        claims = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []
    return [claim for claim in claims if isinstance(claim, dict)]
