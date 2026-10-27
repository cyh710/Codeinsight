"""工具集装配（源文档 §2.7-3「调用项目理解工具辅助开发」）。

基础工具全部**只读**（ADR 0008）。写入与执行交给外部 agent 经 MCP 承担，
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

from dataclasses import dataclass, field
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

    workspace_versions: dict[str, str] = field(default_factory=dict)
    """每个请求首次读到的文件版本；不同会话不共享。"""

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
        if data and data.get("citations") and self.name not in {"read_file", "search_files"}:
            state = self.services.conn.execute(
                "SELECT index_epoch,head_commit FROM repo_state WHERE project_id=?",
                (self.services.project_id,),
            ).fetchone()
            for citation in data["citations"]:
                citation.setdefault("source_kind", "index")
                citation.setdefault("index_epoch", state[0] if state else 0)
                citation.setdefault("head_commit", state[1] if state else None)
            content = (
                "以下来自索引快照，仅供定位；解释当前实现前请用read_file核对工作区。\n" + content
            )
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
                **{
                    k: v
                    for k in ("source_kind", "content_sha256", "index_epoch", "head_commit")
                    if (v := getattr(item, k, None)) is not None
                },
            }
            for item in rows
        ]

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        raise NotImplementedError


def build_tools(services: ToolServices) -> ToolRegistry:
    """装配15个基础工具。工作区工具不依赖索引，知识桥可追加教材工具。"""
    from codeinsight.agent.tools_code import (
        FindSymbolTool,
        GetCalleesTool,
        GetCallersTool,
        GetModuleOverviewTool,
        ReadFileTool,
        SearchCodeTool,
    )
    from codeinsight.agent.tools_exploration import ProposeExplorationTool
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
    from codeinsight.agent.tools_workspace import ListFilesTool, SearchFilesTool

    tools: list[Tool] = [
        ListFilesTool(services),
        SearchFilesTool(services),
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
        ProposeExplorationTool(services),
    ]
    if services.learning is not None:
        # 教材工具与项目工具分开：它们返回的是教学资料，`data` 里**没有**
        # citations——教材命中不能变成项目事实（见 answer_policy）。
        from codeinsight.cognitive.concepts.tools import build_learning_tools

        tools.extend(
            build_learning_tools(services.learning, max_bytes=services.budget.max_tool_result_bytes)
        )
    return ToolRegistry(tools)
