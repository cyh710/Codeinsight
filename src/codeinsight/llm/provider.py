"""LLM Provider 接口。

源文档 §3.2「模型接口：可配置 LLM API」。

接口形态沿用织忆 `ai-companion-agent` 的 `BaseLLMClient`（Apache-2.0，已移植，见
`docs/ported-from-tapestry.md`），但**只留需要的四个方法**，
丢掉织忆那层产品化的 provider 绑定（primary_chat / provider_registry / api_key_store）——
CodeInsight 是单用户本地工具，不需要账号与路由那套。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolCall:
    """模型请求的一次工具调用。"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolCallResponse:
    """模型的完整回复：文本 + 工具调用。"""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@runtime_checkable
class LLMProvider(Protocol):
    """一个模型服务。"""

    model_id: str
    """完整模型标识，含版本（如 `deepseek-chat`），评测报告要记录它。"""

    async def complete(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 0,
        temperature: float = 0.0,
    ) -> str:
        """纯文本补全。"""
        ...

    async def complete_with_tools(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 0,
        temperature: float = 0.0,
        tool_choice: str | Mapping[str, Any] = "auto",
    ) -> ToolCallResponse:
        """带工具的补全。Agent 主循环用这个。"""
        ...
