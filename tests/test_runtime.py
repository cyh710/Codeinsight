"""Agent 主循环（M3 验收）。

用**脚本化的假模型**跑，不打网络：
模型的行为是可枚举的，运行时的行为才可断言。

验收口径：
- `meta` 第一条；`answer` 与 `done` 各恰好一次，`done` 最后。
- 工具结果真的回到 messages 里，模型能看到。
- 没有 grounded 证据时**弃答**，不把模型的话当项目事实。
- 走满轮次 → `incomplete`，不硬编答案。
"""

from __future__ import annotations

from typing import Any

import pytest

from codeinsight.agent.runtime import AgentRuntime, RuntimeConfig
from codeinsight.agent.tool import ToolContext, ToolRegistry, ToolResult
from codeinsight.llm.provider import StreamChunk, ToolCall


class FakeProvider:
    model_id = "fake-model@1"

    def __init__(self, turns: list[list[StreamChunk]]) -> None:
        self.turns = turns
        self.calls: list[list[dict[str, Any]]] = []
        self.tools_seen: list[list[dict[str, Any]]] = []

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        self.calls.append(list(messages))
        self.tools_seen.append(list(tools))
        turn = self.turns.pop(0) if self.turns else [StreamChunk(finish_reason="stop")]
        for chunk in turn:
            yield chunk

    async def complete(self, *args, **kwargs):  # pragma: no cover —— 主循环不用
        return ""

    async def complete_with_tools(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("主循环应走流式接口")


class FakeSearchTool:
    name = "search_code"
    description = "假的检索工具"
    parameters = {"type": "object", "properties": {}, "required": []}
    mutating = False

    def __init__(self, hits: list[dict[str, Any]] | None = None) -> None:
        self.hits = hits or []
        self.calls: list[dict[str, Any]] = []

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        self.calls.append(arguments)
        if not self.hits:
            return ToolResult("没有命中。", data={"items": [], "citations": []})
        return ToolResult(
            "命中 1 条",
            data={
                "items": [
                    {
                        "path": "a.py",
                        "lineno": 3,
                        "end_lineno": 9,
                        "qualname": "a.f",
                        "snippet": "def f():",
                        "lanes": ["bm25"],
                        "concepts": [],
                    }
                ],
                "citations": [
                    {"path": "a.py", "lineno": 3, "end_lineno": 9, "qualname": "a.f"}
                ],
            },
        )


def _tool_call(query: str = "入口") -> StreamChunk:
    return StreamChunk(
        tool_calls=[ToolCall(id="c1", name="search_code", arguments={"query": query})],
        finish_reason="tool_calls",
    )


async def _run(runtime: AgentRuntime, question: str = "入口在哪") -> tuple[Any, list]:
    events: list = []

    async def emit(event) -> None:
        events.append(event)

    answer = await runtime.run(
        project_id=1, question=question, conversation_id="conv-1", emit=emit
    )
    return answer, events


@pytest.mark.asyncio
async def test_tool_round_trip_and_fact_extraction() -> None:
    provider = FakeProvider(
        [
            [StreamChunk(text="我查一下。"), _tool_call()],
            [StreamChunk(text="入口是 a.f [a.py:3]。"), StreamChunk(finish_reason="stop")],
        ]
    )
    registry = ToolRegistry([FakeSearchTool(hits=[{"x": 1}])])
    runtime = AgentRuntime(provider=provider, registry=registry)

    answer, events = await _run(runtime)

    assert events[0].type == "meta"
    assert events[0].data["tools"] == ["search_code"]
    # 工具目录是独立参数，不进 messages——省上下文，也避免模型把 schema 当对话内容。
    assert provider.tools_seen[0][0]["name"] == "search_code"
    assert [event.type for event in events].count("answer") == 1
    assert [event.type for event in events].count("done") == 1
    assert events[-1].type == "done"
    assert "search_code" in [event.data.get("name") for event in events if event.type == "tool"]
    assert answer.tools_used == ["search_code"]
    assert answer.facts and answer.facts[0]["citation"]["path"] == "a.py"
    assert answer.abstained is False

    # 工具结果真的回传给了模型：第二轮的 messages 里有 tool 消息。
    second_turn = provider.calls[1]
    assert any(message["role"] == "tool" for message in second_turn)
    assert any(message["role"] == "assistant" and message.get("tool_calls") for message in second_turn)


@pytest.mark.asyncio
async def test_abstains_when_no_grounding() -> None:
    provider = FakeProvider(
        [
            [_tool_call()],
            [StreamChunk(text="我猜入口在 main.py。"), StreamChunk(finish_reason="stop")],
        ]
    )
    runtime = AgentRuntime(provider=provider, registry=ToolRegistry([FakeSearchTool()]))

    answer, events = await _run(runtime, "不存在的东西")

    assert answer.abstained is True
    assert answer.abstention_reason
    assert answer.facts == []
    assert answer.inferences == []
    assert "没有找到" in answer.text
    assert events[-1].data["abstained"] is True


@pytest.mark.asyncio
async def test_fabricated_citation_cannot_become_a_fact() -> None:
    provider = FakeProvider(
        [
            [_tool_call()],
            [StreamChunk(text="入口在 [b.py:777]。"), StreamChunk(finish_reason="stop")],
        ]
    )
    runtime = AgentRuntime(provider=provider, registry=ToolRegistry([FakeSearchTool(hits=[{}])]))

    answer, _ = await _run(runtime)

    assert answer.facts == []
    assert "777" not in answer.text


@pytest.mark.asyncio
async def test_turn_limit_marks_incomplete() -> None:
    provider = FakeProvider([[_tool_call()] for _ in range(5)])
    runtime = AgentRuntime(
        provider=provider,
        registry=ToolRegistry([FakeSearchTool(hits=[{}])]),
        config=RuntimeConfig(max_model_turns=2),
    )

    answer, events = await _run(runtime)

    assert answer.incomplete is True
    assert answer.facts == []
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_unknown_tool_does_not_crash_the_turn() -> None:
    provider = FakeProvider(
        [
            [
                StreamChunk(
                    tool_calls=[ToolCall(id="c9", name="nope", arguments={})],
                    finish_reason="tool_calls",
                )
            ],
            [StreamChunk(text="换个方式回答。"), StreamChunk(finish_reason="stop")],
        ]
    )
    runtime = AgentRuntime(provider=provider, registry=ToolRegistry([]))

    answer, events = await _run(runtime)

    assert answer.error is None
    assert any(
        event.type == "tool" and event.data["status"] == "error" for event in events
    )
    tool_messages = [m for m in provider.calls[1] if m["role"] == "tool"]
    assert tool_messages and "没有名为" in tool_messages[0]["content"]


@pytest.mark.asyncio
async def test_upstream_error_still_emits_done() -> None:
    class BoomProvider(FakeProvider):
        async def stream_with_tools(self, *args, **kwargs):
            raise RuntimeError("upstream down")
            yield  # pragma: no cover

    runtime = AgentRuntime(provider=BoomProvider([]), registry=ToolRegistry([]))
    answer, events = await _run(runtime)

    assert answer.error is not None
    assert [event.type for event in events][-1] == "done"
    assert any(event.type == "error" for event in events)


@pytest.mark.asyncio
async def test_follow_up_turn_sees_history() -> None:
    provider = FakeProvider(
        [
            [StreamChunk(text="回答一 [a.py:3]。"), StreamChunk(finish_reason="stop")],
            [StreamChunk(text="继续说明 [a.py:3]。"), StreamChunk(finish_reason="stop")],
        ]
    )
    runtime = AgentRuntime(provider=provider, registry=ToolRegistry([]))

    # 第一轮没有 grounded 位置——但这里只关心历史是否带进第二轮。
    await runtime.run(project_id=1, question="第一问", conversation_id="c")
    await runtime.run(project_id=1, question="第二问", conversation_id="c")

    second = provider.calls[1]
    assert second[0]["content"] == "第一问"
    assert second[-1]["content"] == "第二问"
