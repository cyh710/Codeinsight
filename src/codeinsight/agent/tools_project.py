"""项目结构侧工具：业务流程、变更、设计说明。

三者都来自索引里已经落库的结构化数据——不是现场扫源码。
「流程」是构建索引时从入口跑可达性得出的，所以它和符号、边是**同一个版本**。
"""

from __future__ import annotations

from typing import Any

from codeinsight.agent.tool import ToolContext, ToolResult
from codeinsight.agent.tools import BaseTool
from codeinsight.models import Citation


class GetFlowTool(BaseTool):
    name = "get_flow"
    description = (
        "查看由真实调用边支持的静态候选路径（不代表运行顺序，副作用仅为启发式候选）。"
        "不给名字时列出所有流程；给名字返回沿调用边排列的步骤。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "flow_name": {"type": "string", "description": "流程名（可部分匹配）；缺省列出全部"}
        },
        "required": [],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        from codeinsight.cognitive.indexing.flow_read import verified_flows

        items = verified_flows(self.services.conn, self.services.project_id)
        name = str(arguments.get("flow_name") or "").strip()
        if name:
            items = [f for f in items if name in f["name"]][:1]
        if not items:
            return self.result(
                "没有可核对的静态候选链路；可以直接读取入口源码继续分析。",
                data={"items": [], "citations": []},
            )
        citations = [
            Citation(s["path"], s["lineno"], s["lineno"], s["qualname"], "")
            for f in items
            for s in f["steps"]
            if s["path"] and s["lineno"]
        ]
        content = "静态候选路径，不代表运行顺序；末端副作用为启发式候选。\n" + "\n".join(
            f"{f['name']}："
            + " → ".join(f"{s['qualname']} ({s['path']}:{s['lineno']})" for s in f["steps"])
            + ("（含不确定调用）" if any(e["uncertain"] for e in f["edges"]) else "")
            for f in items
        )
        return self.result(
            content,
            data={
                **(items[0] if name else {"items": items}),
                "citations": self.citations(citations),
            },
        )


class GetChangesTool(BaseTool):
    name = "get_changes"
    description = (
        "查看最近一次索引更新带来的代码变更：哪些文件/符号变了、谁受影响、"
        "哪些设计说明已经过期。回答「这次改了什么」「会不会影响 X」时用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "since": {"type": "string", "description": "指定某个 commit 的变更记录；缺省取最近一次"}
        },
        "required": [],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        from codeinsight.cognitive.changes.service import build_changes

        payload = build_changes(
            self.services.conn,
            self.services.project_id,
            since=str(arguments.get("since") or "") or None,
        )
        files = payload["files"]
        if not payload["changed_symbols"] and not any(files.values()):
            return self.result(
                "还没有可比对的变更记录。变更说明来自两次索引之间的差异——"
                "先用 git 提交改动、再跑一次增量索引，这里才会有内容。",
                data=payload,
            )

        lines = [payload["summary"] or "本次变更："]
        for key, label in (("added", "新增"), ("modified", "修改"), ("deleted", "删除")):
            entries = files[key]
            if entries:
                lines.append(
                    f"{label}文件（{len(entries)}）：" + "、".join(f["path"] for f in entries[:10])
                )
        if payload["changed_symbols"]:
            lines.append("变更符号：")
            for symbol in payload["changed_symbols"][:15]:
                lines.append(
                    f"- {symbol['path']}:{symbol['lineno']}  {symbol['qualname']}"
                    f"（{symbol['change']}）"
                )
        impacted = payload["impacted"]
        if impacted["symbols"]:
            lines.append(f"受影响符号（{len(impacted['symbols'])}）：")
            for symbol in impacted["symbols"][:10]:
                lines.append(f"- {symbol['path']}:{symbol['lineno']}  {symbol['qualname']}")
        if impacted["modules"]:
            lines.append("受影响模块：" + "、".join(impacted["modules"][:10]))
        if payload["stale_design_decisions"]:
            lines.append("可能已过期的设计说明：")
            for item in payload["stale_design_decisions"]:
                lines.append(f"- {item['doc_id']} {item['title']}：{item['reason']}")

        citations = [
            Citation(
                symbol["path"], int(symbol["lineno"]), int(symbol["lineno"]), symbol["qualname"], ""
            )
            for symbol in payload["changed_symbols"]
            if symbol.get("path") and symbol.get("lineno")
        ]
        return self._with_citations("\n".join(lines), payload, citations)

    def _with_citations(
        self, text: str, data: dict[str, Any], citations: list[Citation]
    ) -> ToolResult:
        base = self.result(text, data=data)
        return ToolResult(
            base.content,
            {**base.data, "citations": self.citations(citations)},
            base.truncated,
            base.error,
        )


class GetDesignDecisionsTool(BaseTool):
    name = "get_design_decisions"
    description = (
        "查看项目的设计说明（ADR）及其对应的代码证据。"
        "回答「为什么这么设计」时用；注意设计说明可能已经过期。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "可选关键词（标题 / 正文）"},
            "limit": {"type": "integer", "description": "最多返回多少条，默认 10"},
        },
        "required": [],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(arguments.get("query") or "").strip()
        limit = max(1, min(int(arguments.get("limit") or 10), 50))
        params: list[Any] = [self.services.project_id]
        where = ""
        if query:
            where = " AND (title LIKE ? OR body LIKE ? OR doc_id LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like, like])
        params.append(limit)
        rows = self.services.conn.execute(
            "SELECT id, doc_id, title, status, path, body FROM design_decision"
            f" WHERE project_id = ?{where} ORDER BY doc_id LIMIT ?",
            tuple(params),
        ).fetchall()
        if not rows:
            return self.result(
                "没有找到设计说明。索引时如果仓库里没有 docs/decisions 一类目录，这里会是空的。",
                data={"items": [], "citations": []},
            )

        lines = [f"共 {len(rows)} 条设计说明："]
        items: list[dict[str, Any]] = []
        citations: list[Citation] = []
        for row in rows:
            evidence = self.services.conn.execute(
                "SELECT path, lineno, symbol_id, note FROM design_decision_evidence"
                " WHERE decision_id = ? ORDER BY id LIMIT 6",
                (row["id"],),
            ).fetchall()
            lines.append(f"- {row['doc_id']}  {row['title']}  [{row['status'] or 'unknown'}]")
            if row["path"]:
                lines.append(f"  文档：{row['path']}")
            for item in evidence:
                lines.append(f"  证据：{item['path']}:{item['lineno']}  {item['note'] or ''}")
                if item["path"] and item["lineno"]:
                    citations.append(
                        Citation(item["path"], int(item["lineno"]), int(item["lineno"]), None, "")
                    )
            items.append(
                {
                    "doc_id": row["doc_id"],
                    "title": row["title"],
                    "status": row["status"],
                    "path": row["path"],
                    "evidence": [
                        {
                            "path": item["path"],
                            "lineno": int(item["lineno"] or 0),
                            "note": item["note"],
                        }
                        for item in evidence
                    ],
                }
            )
        return self.result(
            "\n".join(lines),
            data={"items": items, "citations": self.citations(citations)},
        )
