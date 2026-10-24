"""上下文有界（源文档 §3.2「上下文管理」核心技术）。

两层预算，两个不同的目的：

- **持久化层**（80 KB/单个工具结果）：写进事件账本时的上限。账本是审计
  与复现用的，不需要为模型压缩，但也不能无限膨胀。
- **模型层**（单轮 64 KB / 单消息 24 KB / 单结果 12 KB）：喂给模型的上限。
  这是真正决定每次请求花多少钱、会不会撑爆窗口的数字。

**代码场景的特殊要求**：截断不得破坏 `file:line` 引用。
所以 `ToolResult.content`（给模型看的）与 `ToolResult.data`（引用、证据、
结构化结果）从一开始就是两个对象——截断只作用于前者，后者原样保留。
如果引用只存在于正文里，任何一次截断都会让「答案可追溯」变成碰运气。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

TRUNCATION_MARK = "\n…（内容已截断，{omitted} 字节未显示）"


def byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def truncate_bytes(text: str, limit: int) -> tuple[str, bool]:
    """按 UTF-8 字节截断，不切碎多字节字符，并标明省略了多少。

    返回 `(截断后的文本, 是否截断)`。
    """
    if limit <= 0:
        return "", bool(text)
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False
    # 标记自身占字节，预留出来，保证结果不超过 limit。
    marker = TRUNCATION_MARK.format(omitted=len(data))
    reserve = byte_len(marker)
    if reserve >= limit:
        return "", True
    head = data[: limit - reserve].decode("utf-8", errors="ignore")
    omitted = len(data) - byte_len(head)
    return head + TRUNCATION_MARK.format(omitted=omitted), True


def message_bytes(message: dict[str, Any]) -> int:
    """一条消息在请求里的近似字节数。

    只算内容与参数。近似即可——预算的目的是**限制规模**，
    不是精确计费；用 `json.dumps` 会低估工具调用结构、高估中文
    （`ensure_ascii=False` 时正好），差别在几十字节量级。
    """
    total = 0
    content = message.get("content")
    if isinstance(content, str):
        total += byte_len(content)
    for call in message.get("tool_calls") or []:
        total += byte_len(json.dumps(call, ensure_ascii=False))
    return total


def group_messages(messages: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """把消息切成**不可拆分**的交互组。

    一个 assistant 的 `tool_calls` 和随后的 `tool` 结果是一组：
    拆开会出现「工具结果没有对应调用」或反之——OpenAI 兼容端点会直接 400。
    所以丢弃历史时只能整组丢。
    """
    groups: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        group = [message]
        index += 1
        if message.get("role") == "assistant" and message.get("tool_calls"):
            while index < len(messages) and messages[index].get("role") == "tool":
                group.append(messages[index])
                index += 1
        groups.append(group)
    return groups


@dataclass(frozen=True)
class ContextBudget:
    """模型层预算（字节）。默认值对齐 `config.Settings`。"""

    max_turn_bytes: int = 64_000
    max_message_bytes: int = 24_000
    max_tool_result_bytes: int = 12_000

    def clamp_tool_result(self, text: str) -> tuple[str, bool]:
        return truncate_bytes(text, self.max_tool_result_bytes)


def assemble(
    prior: Sequence[dict[str, Any]],
    current: Sequence[dict[str, Any]],
    goal: dict[str, Any],
    budget: ContextBudget,
) -> tuple[list[dict[str, Any]], int]:
    """装配一轮的 messages：**目标钉住 + 最近的完整交互组**。

    三段的顺序不能变：

        [更早的对话] [当前问题] [本轮的工具交互]

    当前问题要在中间——本轮的 assistant/tool 消息是它的后续，
    把问题挪到最后会让工具结果看起来是「凭空出现的」。

    `prior` 是**以前各轮**的完整消息；`current` 是**本轮**已经发生的
    工具交互（assistant.tool_calls + tool 结果）。取舍从最新的组往前收，
    放不下就整组丢——绝不留半组（OpenAI 兼容端点会直接拒绝）。

    返回 `(messages, 丢掉了多少组)`。
    """
    goal_text, goal_truncated = truncate_bytes(str(goal.get("content") or ""), budget.max_message_bytes)
    if goal_truncated:
        goal_text += "\n\n（用户问题过长，已按单消息预算截断）"
    pinned = {**goal, "content": goal_text}

    prior_groups = group_messages(list(prior))
    current_groups = group_messages(list(current))

    used = message_bytes(pinned)
    dropped = 0
    kept_current: list[list[dict[str, Any]]] = []
    kept_prior: list[list[dict[str, Any]]] = []

    # 本轮的工具交互优先级最高：它们是回答当前问题的直接依据。
    for group in reversed(current_groups):
        size = sum(message_bytes(message) for message in group)
        if used + size > budget.max_turn_bytes:
            dropped += 1
            continue
        kept_current.append(group)
        used += size

    for group in reversed(prior_groups):
        size = sum(message_bytes(message) for message in group)
        if used + size > budget.max_turn_bytes:
            dropped += 1
            continue
        kept_prior.append(group)
        used += size

    kept_current.reverse()
    kept_prior.reverse()
    messages = [message for group in kept_prior for message in group]
    messages.append(pinned)
    messages.extend(message for group in kept_current for message in group)
    return messages, dropped
