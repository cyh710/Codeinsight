"""问答端点（契约 §8）：非流式 `POST /query` 与 SSE `POST /query/stream`。

这一层只做三件事：**翻译请求、维护事件顺序、归一错误**。
Agent 怎么检索、怎么校验引用，全在 `agent/runtime.py` 里——接口层不参与。

事件词汇表是冻结的（契约 §8.3），`RuntimeEvent.type` 与事件名一一对应；
这里**不补事件、不合并事件**。`done` 由运行时在 `finally` 里发，
接口层绝不能自己再发一个——重复的 `done` 会让前端提前收尾。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from codeinsight.agent.runtime import RuntimeEvent
from codeinsight.agent.service import AgentSession, ProjectNotFound, open_agent
from codeinsight.api.errors import ApiFailure, bad_request, not_found_project
from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path

router = APIRouter(tags=["query"])

_PROVIDER_FACTORY: Callable[[], Any] | None = None
"""测试注入点：默认按 `.env` 建 provider；测试里换成脚本化的假模型。

与 `api/indexing.py::_ENGINE_CALLABLE` 同一套做法——**接缝只有一个**，
测试与实际走同一条装配路径。
"""


def set_provider_factory(factory: Callable[[], Any] | None) -> None:
    global _PROVIDER_FACTORY
    _PROVIDER_FACTORY = factory


class QueryBody(BaseModel):
    project_id: int
    question: str
    conversation_id: str | None = None


def _open_session(project_id: int) -> AgentSession:
    if not db_path(settings.data_dir).exists():
        raise not_found_project(project_id)
    try:
        return open_agent(
            db_path(settings.data_dir),
            project_id,
            provider=_PROVIDER_FACTORY() if _PROVIDER_FACTORY else None,
        )
    except ProjectNotFound:
        raise not_found_project(project_id) from None


def _sse(event: RuntimeEvent) -> str:
    """一帧 SSE。`data` 必须是**单行** JSON——`json.dumps` 会把换行转义掉。"""
    payload = json.dumps(event.data, ensure_ascii=False, default=str)
    return f"event: {event.type}\ndata: {payload}\n\n"


def _http_status(code: str) -> int:
    return {"upstream_error": 502, "timeout": 504}.get(code, 500)


@router.post("/query")
async def query(body: QueryBody) -> dict[str, Any]:
    """非流式问答。形状见契约 §8.1。"""
    if not body.question.strip():
        raise bad_request("question 不能为空", hint="问点什么，例如「对话流在哪实现」")
    session = _open_session(body.project_id)
    try:
        answer = await session.runtime.run(
            project_id=session.project_id,
            question=body.question,
            conversation_id=body.conversation_id or "",
        )
    finally:
        session.close()

    if answer.error:
        raise ApiFailure(
            status_code=_http_status(str(answer.error.get("code", ""))),
            code=str(answer.error.get("code") or "internal_error"),
            title=str(answer.error.get("title") or "问答失败"),
            hint=str(answer.error.get("hint") or ""),
            detail="",
        )

    return {
        "text": answer.text,
        "facts": answer.facts,
        "inferences": answer.inferences,
        "citations": [
            {
                "path": item.path,
                "lineno": item.lineno,
                "end_lineno": item.end_lineno or item.lineno,
                "qualname": item.qualname,
                "snippet": item.snippet,
            }
            for item in answer.citations
        ],
        "tools_used": answer.tools_used,
        "abstained": answer.abstained,
        "abstention_reason": answer.abstention_reason,
        "incomplete": answer.incomplete,
        "evidence": answer.evidence,
    }


@router.post("/query/stream")
async def query_stream(body: QueryBody) -> StreamingResponse:
    """SSE 流式问答。事件序列见契约 §8.3。

    运行时装进一个后台任务，事件经队列交给生成器——这样**客户端断开时**
    我们能取消任务并关连接，而不是让它在后台悄悄跑完。
    """
    if not body.question.strip():
        raise bad_request("question 不能为空", hint="问点什么，例如「对话流在哪实现」")
    session = _open_session(body.project_id)
    queue: asyncio.Queue[RuntimeEvent | None] = asyncio.Queue()

    async def emit(event: RuntimeEvent) -> None:
        await queue.put(event)

    async def run() -> None:
        try:
            await session.runtime.run(
                project_id=session.project_id,
                question=body.question,
                conversation_id=body.conversation_id or "",
                emit=emit,
            )
        finally:
            # 哨兵：即使运行时在发 meta 之前就崩了，生成器也不会永远等下去。
            await queue.put(None)

    task = asyncio.create_task(run())

    async def frames():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield _sse(event)
                if event.type == "done":
                    break
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
            session.close()

    return StreamingResponse(
        frames(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            # 代理层必须知道这是流：否则 nginx 一类会把它缓冲住，前端收不到增量。
            "X-Accel-Buffering": "no",
        },
    )
