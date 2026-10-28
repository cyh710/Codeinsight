"""旧流程也重新核对相邻调用边；失效候选不冒充真实路径。"""

from __future__ import annotations

import sqlite3

from codeinsight.cognitive.source_targets import attach_targets, begin_read


def verified_flows(conn: sqlite3.Connection, project_id: int) -> list[dict]:
    """同一读取快照内取得步骤、调用边与来源身份；不改写历史。"""
    begin_read(conn)
    items = []
    for row in conn.execute("SELECT * FROM flow WHERE project_id=? ORDER BY id", (project_id,)):
        steps = [
            dict(s)
            for s in conn.execute(
                "SELECT ordinal,symbol_id,qualname,path,lineno,note FROM flow_step WHERE flow_id=? ORDER BY ordinal",
                (row["id"],),
            )
        ]
        if not steps or steps[0]["symbol_id"] != row["entry_symbol_id"]:
            continue
        edges = []
        for left, right in zip(steps, steps[1:], strict=False):
            edge = conn.execute(
                "SELECT confidence FROM edge WHERE project_id=? AND src_symbol_id=? AND dst_symbol_id=? AND kind='call' ORDER BY confidence DESC LIMIT 1",
                (project_id, left["symbol_id"], right["symbol_id"]),
            ).fetchone()
            if edge is None:
                break
            edges.append(
                {
                    "source": left["ordinal"],
                    "target": right["ordinal"],
                    "kind": "call",
                    "uncertain": edge[0] < 1,
                    "confidence": edge[0],
                }
            )
        if len(edges) != len(steps) - 1:
            continue
        effects = [
            dict(e)
            for e in conn.execute(
                "SELECT dst_name,confidence FROM edge WHERE project_id=? AND src_symbol_id=? AND kind='call'",
                (project_id, steps[-1]["symbol_id"]),
            )
        ]
        from codeinsight.cognitive.indexing.flows import _is_side_effect_call

        effects = [e for e in effects if _is_side_effect_call(e["dst_name"])]
        items.append(
            attach_targets(
                conn,
                project_id,
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": "静态候选路径，不代表运行顺序；末端副作用仅为启发式候选。",
                    "entry_qualname": steps[0]["qualname"] or "",
                    "steps": steps,
                    "basis": "static_candidate",
                    "edges": edges,
                    "effect_candidates": effects,
                },
            )
        )
    return items
