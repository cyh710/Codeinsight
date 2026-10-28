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
        from codeinsight.cognitive.indexing.flow_read import verified_flows

        items = verified_flows(conn, project_id)
        return {"items": items, "total": len(items)}
    finally:
        conn.close()


@router.get("/projects/{project_id}/changes")
def get_changes(project_id: int, since: str | None = None) -> dict[str, Any]:
    """最近一次变更说明（契约 §7.1）。

    没有变更记录时返回**同形状的空壳**——前端不需要为此写分支。
    """
    from codeinsight.cognitive.changes.service import build_changes

    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        return build_changes(conn, project_id, since=since)
    finally:
        conn.close()
