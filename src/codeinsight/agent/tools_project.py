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
        "查看项目的关键业务流程（从入口到副作用的调用链）。"
        "不给名字时列出所有流程；给名字返回有序步骤。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "flow_name": {"type": "string", "description": "流程名（可部分匹配）；缺省列出全部"}
        },
        "required": [],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        name = str(arguments.get("flow_name") or "").strip()
        if not name:
            rows = self.services.conn.execute(
                """
                SELECT f.id, f.name, f.description, f.entry_symbol_id,
                       (SELECT COUNT(*) FROM flow_step s WHERE s.flow_id = f.id) AS steps
                FROM flow f WHERE f.project_id = ? ORDER BY f.id
                """,
                (self.services.project_id,),
            ).fetchall()
            if not rows:
                return self.result(
                    "索引里没有识别出业务流程。入口可能没有被识别到（M1 的 entry_point 为空）。",
                    data={"items": [], "citations": []},
                )
            lines = [f"共 {len(rows)} 条关键流程："]
            for row in rows:
                lines.append(
                    f"- [{row['id']}] {row['name']}（{row['steps']} 步）：{row['description'] or ''}"
                )
            return self.result(
                "\n".join(lines),
                data={
                    "items": [
                        {
                            "id": int(row["id"]),
                            "name": row["name"],
                            "description": row["description"],
                            "steps": int(row["steps"]),
                        }
                        for row in rows
                    ],
                    "citations": [],
                },
            )

        flow = self.services.conn.execute(
            "SELECT id, name, description FROM flow WHERE project_id = ? AND (name = ? OR name LIKE ?)"
            " ORDER BY (name = ?) DESC LIMIT 1",
            (self.services.project_id, name, f"%{name}%", name),
        ).fetchone()
        if flow is None:
            return self.result(
                f"没有找到名为「{name}」的流程。不传 flow_name 可以先看全部流程。",
                data={"items": [], "citations": []},
                error="not_found",
            )

        steps = self.services.conn.execute(
            "SELECT ordinal, qualname, path, lineno, note FROM flow_step"
            " WHERE flow_id = ? ORDER BY ordinal",
            (flow["id"],),
        ).fetchall()
        lines = [f"{flow['name']}（{len(steps)} 步）：{flow['description'] or ''}"]
        for step in steps:
            lines.append(
                f"{step['ordinal']}. {step['path']}:{step['lineno']}  {step['qualname'] or ''}"
                f"  {('— ' + step['note']) if step['note'] else ''}"
            )
        citations = [
            Citation(step["path"], int(step["lineno"]), int(step["lineno"]), step["qualname"], "")
            for step in steps
            if step["path"] and step["lineno"]
        ]
        return self.result(
            "\n".join(lines),
            data={
                "id": int(flow["id"]),
                "name": flow["name"],
                "description": flow["description"],
                "steps": [
                    {
                        "ordinal": int(step["ordinal"]),
                        "qualname": step["qualname"],
                        "path": step["path"],
                        "lineno": int(step["lineno"] or 0),
                        "note": step["note"],
                    }
                    for step in steps
                ],
                "citations": self.citations(citations),
            },
        )


class GetChangesTool(BaseTool):
    name = "get_changes"
    description = "查看自某个提交以来的代码变更与影响范围。变更分析在 M6 才可用。"
    parameters = {
        "type": "object",
        "properties": {
            "since": {"type": "string", "description": "起始 commit / 分支名；缺省为上次索引的 commit"}
        },
        "required": [],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        # M6 之前不假装能分析。给它一个**空但形状完整**的结果，
        # 模型就知道这条路走不通，不会再试。
        return self.result(
            "变更分析还没有实现（属于 M6）。当前无法回答「这次改了什么」，"
            "请改用 search_code / find_symbol 查看现状。",
            data={
                "implemented": False,
                "files": {"added": [], "modified": [], "deleted": []},
                "changed_symbols": [],
                "impacted": {"modules": [], "symbols": [], "concept_ids": []},
            },
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
