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
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from codeinsight.agent.discovery import discover
from codeinsight.agent.exploration import target, version
from codeinsight.agent.runtime import RuntimeEvent
from codeinsight.agent.service import AgentSession, ProjectNotFound, open_agent
from codeinsight.api.conversations import RUNNING
from codeinsight.api.errors import ApiFailure, bad_request, not_found_project
from codeinsight.config import settings
from codeinsight.storage.conversations import ConversationRepository, PersistentConversationStore
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
    reading_context: dict[str, Any] | None = None
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    action_origin: dict[str, Any] | None = None


def _open_session(project_id: int) -> AgentSession:
    if not db_path(settings.data_dir).exists():
        raise not_found_project(project_id)
    try:
        session = open_agent(
            db_path(settings.data_dir),
            project_id,
            provider=_PROVIDER_FACTORY() if _PROVIDER_FACTORY else None,
        )
        session.runtime.store = PersistentConversationStore(session.conn)
        return session
    except ProjectNotFound:
        raise not_found_project(project_id) from None


def _sse(event: RuntimeEvent) -> str:
    """一帧 SSE。`data` 必须是**单行** JSON——`json.dumps` 会把换行转义掉。"""
    payload = json.dumps(event.data, ensure_ascii=False, default=str)
    return f"event: {event.type}\ndata: {payload}\n\n"


def _http_status(code: str) -> int:
    return {"upstream_error": 502, "timeout": 504, "reading_invalid": 400, "aborted": 409}.get(
        code, 500
    )


def _reserve(body: QueryBody):
    if not body.question.strip():
        raise bad_request("question 不能为空", hint="问点什么，例如「对话流在哪实现」")
    session = _open_session(body.project_id)
    cid = body.conversation_id or f"conv-{uuid.uuid4().hex}"
    rid = body.request_id or uuid.uuid4().hex
    try:
        previous = ConversationRepository(session.conn).turn(body.project_id, cid, rid)
        replaying = bool(
            previous
            and body.action_origin
            and (previous["answer"].get("exploration") or {}).get("origin") == body.action_origin
        )
        if replaying:
            body.question = previous["question"]
            body.reading_context = previous["reading_context"]
        if body.action_origin and not replaying:
            origin = body.action_origin
            if origin.get("kind") == "overview":
                source = discover(session.conn, body.project_id)
                actions = source["exploration_entries"]
            elif origin.get("kind") == "answer":
                saved = ConversationRepository(session.conn).turn(
                    body.project_id, cid, str(origin.get("request_id", ""))
                )
                source = (saved or {}).get("answer", {}).get("exploration") or {}
                actions = source.get("actions", [])
            else:
                source, actions = {}, []
            if not source:
                raise bad_request("探索动作来源不存在或不属于当前会话")
            now = version(session.conn, body.project_id)
            if (
                any(source.get(k) != now[k] for k in ("project_id", "index_epoch", "head_commit"))
                or origin.get("index_epoch") != now["index_epoch"]
            ):
                raise ApiFailure(
                    status_code=409,
                    code="reading_invalid",
                    title="探索入口已过期",
                    hint="请刷新项目导览或重新核对当前版本。",
                )
            action = next(
                (
                    a
                    for a in actions
                    if a["id"] == origin.get("action_id") and a["kind"] == "follow_up"
                ),
                None,
            )
            if action is None:
                raise bad_request("探索动作不存在或不属于当前会话")
            body.question = action["question"]
            original = action.get("target")
            body.reading_context = (
                target(session.conn, body.project_id, original, session.runtime.learning)
                if original
                else None
            )
            if original and not body.reading_context:
                raise bad_request("探索材料已失效，请重新打开来源")
        turn, created = ConversationRepository(session.conn).reserve(
            body.project_id, cid, rid, body.question, body.reading_context
        )
        if not created and turn["status"] == "running":
            raise sqlite3.IntegrityError("这次请求仍在生成")
        return session, cid, rid, turn, created
    except sqlite3.IntegrityError as exc:
        session.close()
        raise ApiFailure(
            status_code=409,
            code="conversation_busy",
            title="这个对话正在生成回答",
            hint="等待当前回答结束，或先停止它。",
        ) from exc
    except ValueError as exc:
        session.close()
        raise bad_request(str(exc)) from exc
    except BaseException:
        session.close()
        raise


async def _run_persisted(session, body, cid, rid, emit=None):
    repository = ConversationRepository(session.conn)
    task_ids = []

    async def persist(event: RuntimeEvent) -> None:
        if event.type == "answer":
            event.data["source_head_commit"] = getattr(session, "head_commit", None)
            if body.action_origin and event.data.get("exploration") is not None:
                event.data["exploration"]["origin"] = body.action_origin
        if event.type == "meta":
            event.data["request_id"] = rid
            task_ids.append(event.data["task_id"])
            RUNNING[event.data["task_id"]] = (body.project_id, asyncio.current_task())
        repository.event(body.project_id, cid, rid, event.type, event.data)
        if emit:
            await emit(event)

    try:
        return await session.runtime.run(
            project_id=session.project_id,
            question=body.question,
            conversation_id=cid,
            **(
                {"reading_context": body.reading_context}
                if body.reading_context is not None
                else {}
            ),
            emit=persist,
        )
    finally:
        for task_id in task_ids:
            RUNNING.pop(task_id, None)


@router.post("/query")
async def query(body: QueryBody) -> dict[str, Any]:
    """非流式问答。形状见契约 §8.1。"""
    session, cid, rid, previous, created = _reserve(body)
    try:
        if not created:
            saved = previous["answer"]
            if saved.get("error"):
                error = saved["error"]
                raise ApiFailure(
                    status_code=_http_status(error["code"]),
                    code=error["code"],
                    title=error["title"],
                    hint=error["hint"],
                )
            return {
                **saved,
                "conversation_id": cid,
                "request_id": rid,
                "tools_used": saved.get("tools_used", []),
                "evidence": saved.get("evidence", []),
                "abstention_reason": saved.get("reason", ""),
                "incomplete": saved.get("incomplete", False),
            }
        answer = await _run_persisted(session, body, cid, rid)
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
        "conversation_id": cid,
        "request_id": rid,
        "source_head_commit": getattr(session, "head_commit", None),
        "text": answer.text,
        "raw_text": answer.raw_text,
        "response_kind": answer.response_kind,
        "evidence_review": answer.evidence_review,
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
        "knowledge_sources": answer.knowledge_sources,
        "learning_entries": answer.learning_entries,
        "learning_targets": answer.learning_targets,
        "reading_status": answer.reading_status,
        "knowledge_error": answer.knowledge_error,
        "exploration": answer.exploration,
    }


@router.post("/query/stream")
async def query_stream(body: QueryBody) -> StreamingResponse:
    """SSE 流式问答。事件序列见契约 §8.3。

    运行时装进一个后台任务，事件经队列交给生成器——这样**客户端断开时**
    我们能取消任务并关连接，而不是让它在后台悄悄跑完。
    """
    session, cid, rid, previous, created = _reserve(body)
    if not created:
        session.close()

        async def replay():
            yield _sse(
                RuntimeEvent(
                    "meta",
                    {
                        "task_id": previous["task_id"],
                        "conversation_id": cid,
                        "request_id": rid,
                        "model": "",
                        "tools": [],
                    },
                )
            )
            result = previous["answer"]
            if result.get("error"):
                if result.get("text"):
                    yield _sse(RuntimeEvent("delta", {"text": result["text"]}))
                yield _sse(RuntimeEvent("error", result["error"]))
            else:
                yield _sse(RuntimeEvent("answer", result))
            yield _sse(
                RuntimeEvent(
                    "done",
                    {
                        "abstained": result.get("abstained", False),
                        "reason": result.get("reason", ""),
                    },
                )
            )

        return StreamingResponse(replay(), media_type="text/event-stream; charset=utf-8")
    queue: asyncio.Queue[RuntimeEvent | None] = asyncio.Queue()

    async def emit(event: RuntimeEvent) -> None:
        await queue.put(event)

    async def run() -> None:
        try:
            await _run_persisted(session, body, cid, rid, emit)
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
