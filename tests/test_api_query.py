"""问答端点（契约 §8）。

这一层只验证**接口行为**：事件顺序、错误归一、会话生命周期。
检索与引用校验在 `test_runtime.py` / `test_answer.py` 里验证——
这里用脚本化的假运行时，不打网络、不依赖索引。

验收口径（契约 §8.3 的三条硬约束）：
- `meta` 第一条、`answer` 与 `done` 各恰好一次、`done` 最后；
- 流式响应带 `X-Accel-Buffering: no`（否则代理会缓冲）；
- 每个请求一个 session，结束时关掉。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.runtime import RuntimeEvent
from codeinsight.agent.service import ProjectNotFound
from codeinsight.api import query as query_module
from codeinsight.api.app import create_app
from codeinsight.models import Answer, Citation


class FakeRuntime:
    def __init__(self, events: list[RuntimeEvent], answer: Answer) -> None:
        self.events = events
        self.answer = answer
        self.calls: list[dict] = []

    async def run(self, *, project_id, question, conversation_id, emit=None):
        self.calls.append(
            {"project_id": project_id, "question": question, "conversation_id": conversation_id}
        )
        if emit is not None:
            for event in self.events:
                await emit(event)
        return self.answer


class FakeSession:
    def __init__(self, runtime: FakeRuntime, project_id: int = 1) -> None:
        self.runtime = runtime
        self.project_id = project_id
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _answer(**overrides) -> Answer:
    base = Answer(
        text="入口是 chat_stream [backend/api/chat.py:42]。",
        facts=[
            {
                "text": "入口是 chat_stream。",
                "citation": {
                    "path": "backend/api/chat.py",
                    "lineno": 42,
                    "end_lineno": 42,
                    "qualname": "backend.api.chat.chat_stream",
                    "snippet": "async def chat_stream",
                },
            }
        ],
        inferences=[{"text": "可能用了队列解耦。", "confidence": 0.5}],
        citations=[Citation("backend/api/chat.py", 42, 42, "backend.api.chat.chat_stream", "")],
        tools_used=["search_code"],
        evidence=[
            {
                "chunk_id": 7,
                "path": "backend/api/chat.py",
                "lineno": 42,
                "end_lineno": 60,
                "qualname": "backend.api.chat.chat_stream",
                "snippet": "async def chat_stream",
                "score": 0.87,
                "lanes": ["bm25", "dense"],
                "concept_ids": ["async"],
            }
        ],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _events() -> list[RuntimeEvent]:
    return [
        RuntimeEvent(
            "meta", {"task_id": "t1", "conversation_id": "", "model": "fake", "tools": []}
        ),
        RuntimeEvent("tool", {"name": "search_code", "status": "running", "summary": "搜索"}),
        RuntimeEvent(
            "evidence",
            {
                "path": "backend/api/chat.py",
                "lineno": 42,
                "end_lineno": 60,
                "qualname": "backend.api.chat.chat_stream",
                "snippet": "x",
                "lanes": ["bm25"],
                "concepts": [],
            },
        ),
        RuntimeEvent("delta", {"text": "入口是"}),
        RuntimeEvent(
            "answer",
            {
                "facts": [],
                "inferences": [],
                "citations": [],
                "abstained": False,
                "reason": "",
                "incomplete": False,
            },
        ),
        RuntimeEvent("done", {"abstained": False, "reason": ""}),
    ]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, data_dir) -> FakeSession:
    session = FakeSession(FakeRuntime(_events(), _answer()))
    monkeypatch.setattr(query_module, "open_agent", lambda *args, **kwargs: session)
    return session


def test_query_returns_contract_shape(client, fake) -> None:
    response = client.post(
        "/query",
        json={"project_id": 1, "question": "对话流在哪", "conversation_id": "c1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"].startswith("入口是")
    assert body["facts"][0]["citation"]["lineno"] == 42
    assert body["inferences"][0]["confidence"] < 1
    assert body["tools_used"] == ["search_code"]
    assert body["evidence"][0]["chunk_id"] == 7
    assert body["evidence"][0]["lanes"] == ["bm25", "dense"]
    assert body["incomplete"] is False
    assert fake.runtime.calls[0]["conversation_id"] == "c1"
    assert fake.closed is True


def test_query_rejects_empty_question(client, fake) -> None:
    response = client.post("/query", json={"project_id": 1, "question": "   "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_query_maps_upstream_error_to_502(client, fake) -> None:
    fake.runtime.answer = _answer(
        error={"code": "upstream_error", "title": "模型服务暂时不可用", "hint": "稍后重试"}
    )
    response = client.post("/query", json={"project_id": 1, "question": "x"})
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "upstream_error"
    assert error["hint"]


def test_query_unknown_project_is_404(client, monkeypatch, data_dir) -> None:
    def boom(*args, **kwargs):
        raise ProjectNotFound("nope")

    monkeypatch.setattr(query_module, "open_agent", boom)
    response = client.post("/query", json={"project_id": 99, "question": "x"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    frames = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[len("event: ") :] for line in lines if line.startswith("event: "))
        data = next(line[len("data: ") :] for line in lines if line.startswith("data: "))
        frames.append((event, json.loads(data)))
    return frames


def test_stream_event_order_and_headers(client, fake) -> None:
    with client.stream(
        "POST", "/query/stream", json={"project_id": 1, "question": "对话流在哪"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        text = "".join(response.iter_text())

    frames = _parse_sse(text)
    names = [name for name, _ in frames]
    assert names[0] == "meta"
    assert names[-1] == "done"
    assert names.count("answer") == 1
    assert names.count("done") == 1
    assert fake.closed is True


def test_stream_data_is_single_line_json(client, fake) -> None:
    with client.stream(
        "POST", "/query/stream", json={"project_id": 1, "question": "多行\n文本"}
    ) as response:
        text = "".join(response.iter_text())
    for block in text.strip().split("\n\n"):
        data_lines = [line for line in block.splitlines() if line.startswith("data: ")]
        assert len(data_lines) == 1
