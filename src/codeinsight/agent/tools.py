"""工具集装配（源文档 §2.7-3「调用项目理解工具辅助开发」）。

12 个工具全部**只读**（ADR 0008）。写入与执行交给外部 agent 经 MCP 承担，
CodeInsight 占住理解、变更验证、认知更新三段。

三条实现约束，每个工具都要守：

1. **`run()` 不抛异常**。失败返回 `ToolResult(error=...)`，`content` 写
   可读的中文——模型要能据此自我修正（「没有找到 X，可以试试 Y」），
   而不是看到一个栈回溯。
2. **`data` 里带结构化引用**。运行时靠它校验模型答案里
   声称的 `file:line` 是不是真的（见 `answer.py`）。
3. **截断只作用于 `content`**。`data` 里的引用不受 12 KB 预算影响。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codeinsight.agent.context import ContextBudget
from codeinsight.agent.tool import Tool, ToolContext, ToolRegistry, ToolResult
from codeinsight.models import Citation


@dataclass
class ToolServices:
    """工具共用的依赖。一次问答创建一个，工具之间不共享可变状态。"""

    conn: Any
    project_id: int
    repo_root: str
    ref: str | None = None
    retriever: Any = None
    budget: ContextBudget = ContextBudget()
    concepts_dir: Path | None = None
    provider: Any = None
    """`explain_concept(deep)` 才用到；没有就退回 textbook 讲解。"""

    learning: Any = None
    """B 线的教材桥（`LearningBridge`）。有它就多注册两个知识工具。"""

    @property
    def root(self) -> Path:
        return Path(self.repo_root)


class BaseTool:
    """工具基类：管好截断与错误归一，子类只管查询与排版。"""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}
    mutating: bool = False

    def __init__(self, services: ToolServices) -> None:
        self.services = services

    def result(
        self,
        content: str,
        *,
        data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolResult:
        text, truncated = self.services.budget.clamp_tool_result(content)
        return ToolResult(text, data or {}, truncated, error)

    @staticmethod
    def citations(rows: list[Citation]) -> list[dict[str, Any]]:
        return [
            {
                "path": item.path,
                "lineno": item.lineno,
                "end_lineno": item.end_lineno or item.lineno,
                "qualname": item.qualname,
            }
            for item in rows
        ]

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        raise NotImplementedError


def build_tools(services: ToolServices) -> ToolRegistry:
    """装配 12 个工具。顺序即 `meta` 事件里的展示顺序。"""
    from codeinsight.agent.tools_code import (
        FindSymbolTool,
        GetCalleesTool,
        GetCallersTool,
        GetModuleOverviewTool,
        ReadFileTool,
        SearchCodeTool,
    )
    from codeinsight.agent.tools_knowledge import (
        ExplainConceptTool,
        FindConceptInstancesTool,
        ListConceptsTool,
    )
    from codeinsight.agent.tools_project import (
        GetChangesTool,
        GetDesignDecisionsTool,
        GetFlowTool,
    )

    tools: list[Tool] = [
        SearchCodeTool(services),
        FindSymbolTool(services),
        ReadFileTool(services),
        GetCallersTool(services),
        GetCalleesTool(services),
        ListConceptsTool(services),
        ExplainConceptTool(services),
        FindConceptInstancesTool(services),
        GetFlowTool(services),
        GetChangesTool(services),
        GetDesignDecisionsTool(services),
        GetModuleOverviewTool(services),
    ]
    if services.learning is not None:
        # 教材工具与项目工具分开：它们返回的是教学资料，`data` 里**没有**
        # citations——教材命中不能变成项目事实（见 answer_policy）。
        from codeinsight.cognitive.concepts.tools import build_learning_tools

        tools.extend(
            build_learning_tools(
                services.learning, max_bytes=services.budget.max_tool_result_bytes
            )
        )
    return ToolRegistry(tools)
