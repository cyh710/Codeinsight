"""整理探索方向的内部只读工具，不能授予正文代码事实资格。"""

import sqlite3
from typing import Any

from codeinsight.agent.exploration import normalize
from codeinsight.agent.tool import ToolContext, ToolResult
from codeinsight.agent.tools import BaseTool


class ProposeExplorationTool(BaseTool):
    name = "propose_exploration"
    description = (
        "在查证后整理可选局部关系、已展示要点与最多三个后续探索动作。不执行动作，不代替查代码。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "takeaways": {
                "type": "array",
                "items": {"type": "string"},
                "description": "将会在最终正文原样展示的简短要点，不表示用户已理解",
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["follow_up", "code", "knowledge", "graph", "timeline"],
                        },
                        "label": {"type": "string"},
                        "reason": {"type": "string"},
                        "question": {"type": "string"},
                        "target": {
                            "type": "object",
                            "description": "code: kind/path/lineno/qualname；knowledge: kind/topic_id/section_id/version",
                        },
                    },
                },
            },
            "flow": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "role": {"type": "string"},
                                "target": {"type": "object"},
                            },
                        },
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "target": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """非法建议只降级，不使整个问答失败。"""
        try:
            proposal = normalize(
                self.services.conn, ctx.project_id, arguments, self.services.learning
            )
            return self.result(
                "探索建议已核对；请继续正常回答当前问题，不输出 JSON。",
                data={"exploration": proposal},
            )
        except (TypeError, ValueError, KeyError, sqlite3.Error) as exc:
            return self.result("探索建议格式不完整，可直接继续正文回答。", error=str(exc))
