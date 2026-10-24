"""知识侧工具：概念列表、三级解释、概念实例（源文档 §2.6）。

概念本体与检测规则是 B 线的资产（`cognitive/concepts/`），
实例数据是 A 线在索引时同步进来的（`indexing/concepts_sync.py`）。
这里只做「查」——不重新检测、不生成新的项目事实。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from codeinsight.agent.tool import ToolContext, ToolResult
from codeinsight.agent.tools import BaseTool
from codeinsight.cognitive.concepts.explain import explain
from codeinsight.cognitive.concepts.learning_models import Relation
from codeinsight.cognitive.indexing.concepts_sync import load_project_concepts
from codeinsight.models import Citation, ConceptDepth, ConceptInstance

MAX_INSTANCES = 20


def _instance_rows(conn, project_id: int, concept_id: str, *, limit: int) -> list[Any]:
    return conn.execute(
        """
        SELECT id, concept_id, symbol_id, path, lineno, qualname, evidence, confidence
        FROM concept_instance
        WHERE project_id = ? AND concept_id = ?
        ORDER BY path, lineno LIMIT ?
        """,
        (project_id, concept_id, limit),
    ).fetchall()


def _to_instance(row: Any) -> ConceptInstance:
    return ConceptInstance(
        concept_id=row["concept_id"],
        path=row["path"],
        lineno=int(row["lineno"]),
        qualname=row["qualname"],
        symbol_id=int(row["symbol_id"]) if row["symbol_id"] is not None else None,
        evidence=row["evidence"] or "",
        confidence=float(row["confidence"]),
    )


class ListConceptsTool(BaseTool):
    name = "list_concepts"
    description = (
        "列出本项目识别到的技术概念，可按关键词过滤。"
        "回答「这个项目用了哪些技术/设计」或想看概念清单时用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "可选关键词（概念名 / 类别 / 摘要）"},
            "limit": {"type": "integer", "description": "最多返回多少个，默认 30"},
        },
        "required": [],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(arguments.get("query") or "").strip()
        limit = max(1, min(int(arguments.get("limit") or 30), 100))
        params: list[Any] = [self.services.project_id]
        where = ""
        if query:
            where = " AND (c.name LIKE ? OR c.id LIKE ? OR c.category LIKE ? OR c.summary LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like, like, like])
        params.append(limit)
        rows = self.services.conn.execute(
            f"""
            SELECT c.id, c.name, c.category, c.summary,
                   (SELECT COUNT(*) FROM concept_instance ci
                    WHERE ci.project_id = ? AND ci.concept_id = c.id) AS instances
            FROM concept c
            WHERE 1 = 1{where}
            ORDER BY instances DESC, c.id LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        if not rows:
            return self.result(
                "这个项目里没有识别到概念。可能是没同步本体（`ci index --concepts`），"
                "也可能是关键词太窄。",
                data={"items": [], "citations": []},
            )

        lines = [f"识别到 {len(rows)} 个概念："]
        for row in rows:
            lines.append(
                f"- {row['id']}  {row['name']}（{row['category']}，{row['instances']} 处实例）"
                f"：{row['summary']}"
            )
        return self.result(
            "\n".join(lines),
            data={
                "items": [
                    {
                        "concept_id": row["id"],
                        "name": row["name"],
                        "category": row["category"],
                        "summary": row["summary"],
                        "instance_count": row["instances"],
                    }
                    for row in rows
                ],
                "citations": [],
            },
        )


class ExplainConceptTool(BaseTool):
    name = "explain_concept"
    description = (
        "三级深度解释一个技术概念：quick=一句话（不调模型）、"
        "project=结合本项目的实例与调用关系、deep=原理与设计取舍。"
        "用户问「X 是什么 / 为什么这么设计」时用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "concept_id": {"type": "string", "description": "概念 id（如 jwt、async）"},
            "depth": {
                "type": "string",
                "enum": ["quick", "project", "deep"],
                "description": "解释深度，默认 project",
            },
        },
        "required": ["concept_id"],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        concept_id = str(arguments.get("concept_id") or "").strip()
        if not concept_id:
            return self.result("缺少 concept_id 参数。", error="bad_request")
        depth_raw = str(arguments.get("depth") or "project")
        try:
            depth = ConceptDepth(depth_raw)
        except ValueError:
            return self.result(
                f"未知深度「{depth_raw}」，只能是 quick / project / deep。", error="bad_request"
            )
        if self.services.concepts_dir is None:
            return self.result("没有配置概念本体目录。", error="not_indexed")
        concepts = load_project_concepts(self.services.concepts_dir)
        concept = concepts.get(concept_id)
        if concept is None:
            return self.result(
                f"没有 id 为「{concept_id}」的概念。先用 list_concepts 看可用清单。",
                data={"items": [], "citations": []},
                error="concept_not_found",
            )

        rows = _instance_rows(
            self.services.conn, self.services.project_id, concept_id, limit=MAX_INSTANCES
        )
        instances = [_to_instance(row) for row in rows]
        relations = self._relations({item.qualname for item in instances if item.qualname})

        explanation = await explain(
            concept,
            instances=instances,
            relations=relations,
            depth=depth,
            provider=self.services.provider,
        )

        lines = [f"## {concept.name}（{concept.category}）", explanation.summary]
        if explanation.facts:
            lines.append("\n可验证的项目事实：")
            lines.extend(f"- {item['text']}" for item in explanation.facts)
        if explanation.inferences:
            lines.append("\n模型推断（未验证）：")
            lines.extend(f"- {item['text']}" for item in explanation.inferences)
        if explanation.error:
            lines.append(f"\n（{explanation.error}）")

        citations = [
            Citation(
                item["citation"]["path"],
                int(item["citation"]["lineno"]),
                int(item["citation"].get("end_lineno") or item["citation"]["lineno"]),
                item["citation"].get("qualname"),
                "",
            )
            for item in explanation.facts
            if item.get("citation")
        ]
        return self.result(
            "\n".join(lines),
            data={
                **asdict(explanation),
                "items": [asdict(item) for item in instances],
                "citations": self.citations(citations),
            },
        )

    def _relations(self, qualnames: set[str]) -> list[Relation]:
        """取与本概念实例直接相连的边，供 `explain` 讲调用关系。"""
        if not qualnames:
            return []
        placeholders = ",".join("?" for _ in qualnames)
        rows = self.services.conn.execute(
            f"""
            SELECT src.qualname AS src_qualname,
                   COALESCE(dst.qualname, e.dst_name) AS dst_qualname,
                   sf.path, e.lineno, e.confidence
            FROM edge e
            JOIN symbol src ON src.id = e.src_symbol_id
            JOIN file sf ON sf.id = src.file_id
            LEFT JOIN symbol dst ON dst.id = e.dst_symbol_id
            WHERE e.project_id = ?
              AND (src.qualname IN ({placeholders}) OR dst.qualname IN ({placeholders}))
            LIMIT 60
            """,
            (self.services.project_id, *qualnames, *qualnames),
        ).fetchall()
        return [
            Relation(
                src_qualname=row["src_qualname"],
                dst_qualname=row["dst_qualname"],
                path=row["path"],
                lineno=int(row["lineno"] or 0),
                confidence=float(row["confidence"]),
            )
            for row in rows
            if row["lineno"]
        ]


class FindConceptInstancesTool(BaseTool):
    name = "find_concept_instances"
    description = (
        "列出某个概念在本项目里的具体落点（file:line 与检测证据）。"
        "用户问「这个项目哪里用了 X」时用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "concept_id": {"type": "string", "description": "概念 id"},
            "limit": {"type": "integer", "description": "最多返回多少处，默认 20"},
        },
        "required": ["concept_id"],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        concept_id = str(arguments.get("concept_id") or "").strip()
        if not concept_id:
            return self.result("缺少 concept_id 参数。", error="bad_request")
        limit = max(1, min(int(arguments.get("limit") or MAX_INSTANCES), 100))
        rows = _instance_rows(
            self.services.conn, self.services.project_id, concept_id, limit=limit
        )
        if not rows:
            return self.result(
                f"概念「{concept_id}」在本项目里没有检测到实例。"
                "这不等于项目没用它——也可能是检测规则没覆盖到。",
                data={"items": [], "citations": []},
            )

        lines = [f"概念「{concept_id}」在项目中有 {len(rows)} 处实例："]
        instances = [_to_instance(row) for row in rows]
        for item in instances:
            lines.append(f"- {item.path}:{item.lineno}  {item.qualname or ''}  ← {item.evidence}")
        return self.result(
            "\n".join(lines),
            data={
                "items": [
                    {
                        "concept_id": item.concept_id,
                        "path": item.path,
                        "lineno": item.lineno,
                        "qualname": item.qualname,
                        "evidence": item.evidence,
                        "confidence": item.confidence,
                    }
                    for item in instances
                ],
                "citations": self.citations(
                    [
                        Citation(item.path, item.lineno, item.lineno, item.qualname, item.evidence)
                        for item in instances
                    ]
                ),
            },
        )
