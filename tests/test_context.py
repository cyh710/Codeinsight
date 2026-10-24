"""有界上下文（源文档 §3.2「上下文管理」）。

两个验收点：

1. 截断**不切碎多字节字符**，并且明确标出省略了多少。
2. 丢历史只能**整组丢**——assistant.tool_calls 与它的 tool 结果是一体的，
   拆开会让 OpenAI 兼容端点直接 400。
"""

from __future__ import annotations

from codeinsight.agent.context import (
    ContextBudget,
    assemble,
    byte_len,
    group_messages,
    message_bytes,
    truncate_bytes,
)


def test_truncate_keeps_utf8_intact() -> None:
    text = "中文内容" * 100
    cut, truncated = truncate_bytes(text, 120)
    assert truncated
    assert cut.encode("utf-8").decode("utf-8") == cut
    assert "已截断" in cut


def test_truncate_noop_when_within_budget() -> None:
    cut, truncated = truncate_bytes("短", 100)
    assert (cut, truncated) == ("短", False)


def test_group_messages_keeps_tool_calls_with_results() -> None:
    messages = [
        {"role": "user", "content": "问"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "结果"},
        {"role": "assistant", "content": "答"},
    ]
    groups = group_messages(messages)
    assert [len(group) for group in groups] == [1, 2, 1]


def test_assemble_pins_goal_and_drops_oldest_whole_groups() -> None:
    big = "x" * 500
    prior = [
        {"role": "user", "content": big},
        {"role": "assistant", "content": big},
        {"role": "user", "content": "较新的问题"},
        {"role": "assistant", "content": "较新的回答"},
    ]
    goal = {"role": "user", "content": "当前问题"}
    budget = ContextBudget(max_turn_bytes=800, max_message_bytes=800, max_tool_result_bytes=100)
    messages, dropped = assemble(prior, [], goal, budget)

    assert messages[-1]["content"] == "当前问题"
    assert dropped >= 1
    assert sum(message_bytes(message) for message in messages) <= budget.max_turn_bytes


def test_assemble_keeps_current_turn_tool_groups() -> None:
    current = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "y" * 100},
    ]
    goal = {"role": "user", "content": "问题"}
    budget = ContextBudget(max_turn_bytes=10_000, max_message_bytes=1_000, max_tool_result_bytes=100)
    messages, dropped = assemble([], current, goal, budget)
    assert dropped == 0
    assert messages[0]["content"] == "问题"
    assert messages[-1]["role"] == "tool"


def test_message_bytes_counts_tool_arguments() -> None:
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "search_code", "arguments": '{"query":"abc"}'}}],
    }
    assert message_bytes(message) >= byte_len('{"query":"abc"}')
