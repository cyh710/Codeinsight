"""Agent 工具接口。

源文档 §3.1 第二层「代码检索与分析工具调用」+「项目上下文选择」。

工具是**只读**的（v1）。写入与执行交给外部 agent 经 MCP Server 承担
（源文档 §2.7 的"实际操作"一段），CodeInsight 占住理解、变更验证、认知更新三段。
`Tool` 接口本身预留了 `mutating` 标记，将来要加写工具时可在此基础上扩展审批。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolResult:
    """一次工具调用的结果。

    `content` 是给模型看的文本（可能被截断）；`data` 是结构化数据（不进模型上下文，
    但会被引用与前端使用）。两者分离保证：**截断 `content` 不会破坏 `data` 里的
    `file:line` 引用**。
    """

    content: str
    data: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    error: str | None = None


@dataclass(frozen=True)
class ToolContext:
    """工具执行上下文。"""

    project_id: int
    repo_root: str
    conversation_id: str = ""
    depth: int = 0
    """当前工具调用深度，用于限制递归（例如 get_callers 触发更多检索）。"""


@runtime_checkable
class Tool(Protocol):
    """一个可被模型调用的工具。"""

    name: str
    description: str
    parameters: Mapping[str, Any]
    """JSON Schema（OpenAI function schema 形态）。"""

    mutating: bool
    """是否改变仓库状态。v1 全部为 False。"""

    async def run(self, arguments: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        """执行工具。

        约定：**不抛异常**。失败时返回 `ToolResult(error=...)`，
        让 Agent 有机会看到错误并换个策略，而不是整个回合崩掉。

        为什么是 `async`：一部分工具要等模型（`explain_concept(deep)`），
        一部分要等 I/O（读源码）。同步签名会逼调用方在事件循环里
        `asyncio.run`，那在 FastAPI 的线程里直接炸。统一异步，
        实现方需要同步执行时也不必假装异步——它可以直接是 async 函数。
        """
        ...


class ToolRegistry:
    """名字 → 工具。注册表是 Agent 唯一能看到工具的入口。"""

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具重名：{tool.name}")
        self._tools[tool.name] = tool

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def names(self) -> list[str]:
        """按注册顺序，稳定——`meta` 事件里会原样给前端。"""
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        """给模型的工具目录（作为独立参数，不进 messages）。"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": dict(tool.parameters),
            }
            for tool in self._tools.values()
        ]
