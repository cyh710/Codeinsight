"""会话管理与运行任务注册；切换界面不会改变后台请求的归属。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from codeinsight.api.errors import ApiFailure, bad_request
from codeinsight.api.projects import connect_db, require_project
from codeinsight.storage.conversations import ConversationRepository

router = APIRouter(tags=["conversations"])
RUNNING: dict[str, tuple[int, asyncio.Task]] = {}


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None
    archived: bool | None = None
    mark_read: bool = False


def missing_conversation() -> ApiFailure:
    return ApiFailure(
        status_code=404, code="not_found", title="对话不存在", hint="请从对话列表重新选择。"
    )


@router.get("/conversations")
def list_conversations(
    project_id: int | None = None,
    q: str = "",
    archived: bool = False,
    cursor: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    """返回本地会话分页；跨项目搜索仍保留每项的实际项目。"""
    conn = connect_db(project_id or 0)
    try:
        if project_id is not None:
            require_project(conn, project_id)
        return ConversationRepository(conn).list(
            project_id=project_id, query=q, archived=archived, cursor=cursor, limit=limit
        )
    finally:
        conn.close()


@router.post("/projects/{project_id}/conversations", status_code=201)
def create_conversation(project_id: int) -> dict[str, Any]:
    """只建立会话元数据，不触发模型或索引。"""
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        return ConversationRepository(conn).create(project_id)
    finally:
        conn.close()


@router.get("/projects/{project_id}/conversations/{conversation_id}")
def get_conversation(project_id: int, conversation_id: str) -> dict[str, Any]:
    """会话不存在和项目不匹配统一返回未找到。"""
    conn = connect_db(project_id)
    try:
        return ConversationRepository(conn).get(project_id, conversation_id)
    except LookupError:
        raise missing_conversation() from None
    finally:
        conn.close()


@router.patch("/projects/{project_id}/conversations/{conversation_id}")
def patch_conversation(
    project_id: int, conversation_id: str, body: ConversationPatch
) -> dict[str, Any]:
    """只修改会话组织字段，不删除历史或改写回答。"""
    conn = connect_db(project_id)
    try:
        return ConversationRepository(conn).patch(
            project_id, conversation_id, body.model_dump(exclude_none=True)
        )
    except LookupError:
        raise missing_conversation() from None
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    finally:
        conn.close()


@router.get("/projects/{project_id}/conversations/{conversation_id}/turns")
def conversation_turns(
    project_id: int,
    conversation_id: str,
    cursor: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    """来源和阅读目标随回合返回，不从模型文本补造元数据。"""
    conn = connect_db(project_id)
    try:
        return ConversationRepository(conn).turns(project_id, conversation_id, cursor, limit)
    except LookupError:
        raise missing_conversation() from None
    finally:
        conn.close()


@router.post("/projects/{project_id}/tasks/{task_id}/cancel")
async def cancel_task(project_id: int, task_id: str) -> dict[str, Any]:
    """仅取消该项目实际运行的任务；任务自行提交中断结果。"""
    conn = connect_db(project_id)
    try:
        row = conn.execute(
            "SELECT project_id,status FROM agent_task WHERE id=?", (task_id,)
        ).fetchone()
        if row is None or row["project_id"] != project_id:
            raise missing_conversation()
        running = RUNNING.get(task_id)
        if running and running[0] == project_id:
            running[1].cancel()
        return {"task_id": task_id, "cancelled": bool(running), "status": row["status"]}
    finally:
        conn.close()
