"""编排执行端点（契约 §16.3，请求 0015）。

HTTP 层只做迁移与读取；状态机与后台执行都在
`execution/orchestrator.py`。错误统一走 §0.3 形状。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from codeinsight.api.errors import ApiFailure
from codeinsight.api.projects import connect_db, require_project
from codeinsight.execution import orchestrator

router = APIRouter(tags=["executions"])


def _failure(exc: orchestrator.TransitionError) -> ApiFailure:
    # 状态机错误全部用 bad_request 码（契约 §16.3：非法迁移 409、任务不存在 404，
    # 均属请求侧问题；HTTP 状态码本身已区分场景）。
    code = "bad_request" if exc.status_code in (400, 404, 409) else "internal_error"
    return ApiFailure(
        status_code=exc.status_code,
        code=code,
        title=str(exc),
        hint="",
        detail=str(exc),
    )


@router.get("/projects/{project_id}/executions/{task_id}")
def get_execution(project_id: int, task_id: str) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
    finally:
        conn.close()
    try:
        row = orchestrator.get_execution(project_id, task_id)
    except orchestrator.TransitionError as exc:
        raise _failure(exc) from exc
    return orchestrator.execution_public(row)


def _transition_endpoint(action: str):
    def _endpoint(project_id: int, task_id: str) -> dict[str, Any]:
        conn = connect_db(project_id)
        try:
            require_project(conn, project_id)
        finally:
            conn.close()
        try:
            row = orchestrator.transition(project_id, task_id, action)
        except orchestrator.TransitionError as exc:
            raise _failure(exc) from exc
        return orchestrator.execution_public(row)

    return _endpoint


# 四个动作共用一个实现，只差动作名；路径分开是为了契约可读。
router.add_api_route(
    "/projects/{project_id}/executions/{task_id}/approve",
    _transition_endpoint("approve"),
    methods=["POST"],
)
router.add_api_route(
    "/projects/{project_id}/executions/{task_id}/reject",
    _transition_endpoint("reject"),
    methods=["POST"],
)
router.add_api_route(
    "/projects/{project_id}/executions/{task_id}/abort",
    _transition_endpoint("abort"),
    methods=["POST"],
)
router.add_api_route(
    "/projects/{project_id}/executions/{task_id}/merge",
    _transition_endpoint("merge"),
    methods=["POST"],
)
