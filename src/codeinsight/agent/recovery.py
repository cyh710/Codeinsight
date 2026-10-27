"""工具失败按回合记忆；无进展时收束，有新材料时不限制分析轮次。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from codeinsight.agent.tool import ToolResult


@dataclass
class ToolRecovery:
    blocked_files: dict[str, str] = field(default_factory=dict)
    materials: set[str] = field(default_factory=set)
    idle_turns: int = 0
    version: dict | None = None

    def blocked(self, name: str, arguments: dict) -> ToolResult | None:
        """文件版本失败与窗口无关，换行号不能再次触发实际读取。"""
        path = str(arguments.get("path") or "")
        if name == "read_file" and path in self.blocked_files:
            return ToolResult(
                self.blocked_files[path] + " 本回合已确认，不再重复读取；请整理已有材料。",
                error="stale_source",
            )
        return None

    def observe(self, name: str, arguments: dict, result: ToolResult) -> None:
        """只把新增成功材料计入进展；失败消息不能通过换参数变成进展。"""
        if result.error:
            if name == "read_file" and result.error == "stale_source":
                self.blocked_files[str(arguments.get("path") or "")] = result.content
            return
        data = result.data or {}
        locations = data.get("citations") or []
        if locations:
            self.materials.update(
                json.dumps(c, sort_keys=True, ensure_ascii=False) for c in locations
            )
        elif data.get("items") == []:
            return
        elif data or result.content.strip():
            self.materials.add(
                json.dumps(
                    {"tool": name, "data": data, "content": result.content},
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )

    def end_turn(self, before: int) -> bool:
        """连续三轮没有新增材料才进入整理阶段，不限制正常推进的总轮次。"""
        self.idle_turns = self.idle_turns + 1 if len(self.materials) == before else 0
        return self.idle_turns >= 3
