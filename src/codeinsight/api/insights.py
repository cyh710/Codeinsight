"""流程与变更端点（契约 §5 / §7）。

flows 是 A 线 A5（关键业务流程检测）的数据出口——检测器未落地前
如实返回空列表。changes 在 M1–M5 期间按契约 §7.1 返回空壳，
**字段不删不改**，前端现在就按完整形状写。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from codeinsight.api.projects import connect_db, require_project

router = APIRouter(tags=["insights"])


@router.get("/projects/{project_id}/flows")
def list_flows(project_id: int) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        rows = conn.execute(
            "SELECT id, name, description FROM flow WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
        items = []
        for r in rows:
            steps = [
                {
                    "ordinal": s["ordinal"],
                    "qualname": s["qualname"],
                    "path": s["path"],
                    "lineno": s["lineno"],
                    "note": s["note"],
                }
                for s in conn.execute(
                    "SELECT ordinal, qualname, path, lineno, note FROM flow_step "
                    "WHERE flow_id = ? ORDER BY ordinal",
                    (r["id"],),
                ).fetchall()
            ]
            items.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"] or "",
                    # 入口符号缺关联时退而取第一步的 qualname，两处都空则为空串。
                    "entry_qualname": (
                        conn.execute(
                            "SELECT s.qualname FROM flow fl JOIN symbol s ON s.id = fl.entry_symbol_id "
                            "WHERE fl.id = ?",
                            (r["id"],),
                        ).fetchone()
                        or {"qualname": steps[0]["qualname"] if steps else None}
                    )["qualname"]
                    or "",
                    "steps": steps,
                }
            )
        return {"items": items, "total": len(items)}
    finally:
        conn.close()


@router.get("/projects/{project_id}/changes")
def get_changes(project_id: int, since: str | None = None) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        # M6 前的空壳（契约 §7.1）：形状冻结，值为空。
        return {
            "since": since or "",
            "head": "",
            "summary": "",
            "files": {"added": [], "modified": [], "deleted": []},
            "changed_symbols": [],
            "impacted": {"modules": [], "symbols": [], "concept_ids": []},
            "tests": [],
            "stale_design_decisions": [],
        }
    finally:
        conn.close()
