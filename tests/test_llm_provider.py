"""模型协议层：JSON 抠取与流式工具调用拼接。

这两块都是「上游怎么坏，我们怎么接」——不测到就等于没写。
"""

from __future__ import annotations

import json

import pytest

from codeinsight.llm.openai_compat import (
    LLMNotConfigured,
    OpenAICompatProvider,
    StreamChunk,
    _accumulate_tool_call,
    _finalize_tool_calls,
    _parse_arguments,
)
from codeinsight.llm.response_parser import extract_json


def test_extract_plain_json() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_from_fence() -> None:
    raw = '好的，结果如下：\n```json\n{"summary": "x"}\n```\n希望有帮助'
    assert extract_json(raw) == {"summary": "x"}


def test_extract_json_with_thinking_tag() -> None:
    raw = '<think>先想想…</think>{"a": 2}'
    assert extract_json(raw) == {"a": 2}


def test_extract_json_with_unescaped_inner_quotes() -> None:
    raw = '{"text": "他说"你好"就走了"}'
    assert extract_json(raw)["text"] == '他说"你好"就走了'


def test_extract_json_double_wrapped() -> None:
    assert extract_json('{{"a": 3}}') == {"a": 3}


def test_extract_json_raises_when_absent() -> None:
    with pytest.raises(json.JSONDecodeError):
        extract_json("完全没有 JSON")


def test_parse_arguments_tolerates_bad_json() -> None:
    assert _parse_arguments('{"q": "x"}') == {"q": "x"}
    assert _parse_arguments("") == {}
    assert _parse_arguments("{not json") == {}


def test_streamed_tool_call_arguments_are_concatenated() -> None:
    pending: dict[int, dict] = {}
    for piece in [
        {"index": 0, "id": "call-1", "function": {"name": "search_code", "arguments": '{"query":'}},
        {"index": 0, "function": {"arguments": '"入口"'}},
        {"index": 0, "function": {"arguments": "}"}},
    ]:
        _accumulate_tool_call(pending, piece)
    calls = _finalize_tool_calls(pending)
    assert len(calls) == 1
    assert calls[0].name == "search_code"
    assert calls[0].arguments == {"query": "入口"}


def test_two_parallel_tool_calls_keep_their_order() -> None:
    pending: dict[int, dict] = {}
    _accumulate_tool_call(
        pending, {"index": 1, "id": "b", "function": {"name": "second", "arguments": "{}"}}
    )
    _accumulate_tool_call(
        pending, {"index": 0, "id": "a", "function": {"name": "first", "arguments": "{}"}}
    )
    assert [call.name for call in _finalize_tool_calls(pending)] == ["first", "second"]


def test_provider_requires_key_before_network() -> None:
    provider = OpenAICompatProvider(base_url="https://example.com/v1", api_key="", model="m")
    assert provider.enabled is False

    async def run() -> None:
        with pytest.raises(LLMNotConfigured):
            async for _ in provider.stream_with_tools("s", [], []):
                pass

    import asyncio

    asyncio.run(run())


def test_model_id_is_recorded_for_reports() -> None:
    provider = OpenAICompatProvider(
        base_url="https://example.com/v1", api_key="k", model="deepseek-chat"
    )
    assert provider.model_id == "deepseek-chat"


def test_stream_chunk_defaults() -> None:
    chunk = StreamChunk(text="x")
    assert chunk.tool_calls == []
    assert chunk.finish_reason is None
