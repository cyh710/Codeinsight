"""知识层端点（契约 §6）。

quick / project 两级解释**不调 LLM**（源文档 §2.6）：quick 读本体 summary，
project 从 concept_instance 派生位置事实——这正合 ADR 0007 的"事实带出处"。
deep 依赖 LLM Provider（A 线 M3），未接入前返回 upstream_error 并说明原因，
不假装生成过深度解释。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from codeinsight.agent.service import build_provider
from codeinsight.api.errors import ApiFailure, not_found_concept
from codeinsight.api.projects import connect_db, require_project
from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.concepts.builtin import concept_context
from codeinsight.cognitive.concepts.explain import explain
from codeinsight.cognitive.concepts.learning_models import KnowledgeError, Relation
from codeinsight.cognitive.concepts.library import LearningLibrary
from codeinsight.cognitive.concepts.ontology import Concept, DetectionRules
from codeinsight.cognitive.indexing.concepts_sync import refresh_project_concepts
from codeinsight.config import settings
from codeinsight.models import ConceptDepth, ConceptInstance

router = APIRouter(tags=["concepts"])
_PROVIDER_FACTORY: Callable[[], Any] | None = None


def _prepare_project(conn: Any, project_id: int) -> None:
    require_project(conn, project_id)
    refresh_project_concepts(
        conn, project_id=project_id, knowledge_dir=knowledge_directory("concepts")
    )


def _learning_targets(concept_id: str) -> list[dict]:
    try:
        library = LearningLibrary(knowledge_directory("learning"))
    except KnowledgeError:
        # 教材安装错误不阻断已有项目证据；知识端点会给出独立错误。
        return []
    return [
        {**asdict(library.target(t.id)), "href": library.target(t.id).href}
        for t in library.topics_for_concept(concept_id)
    ]


def _concept_row(conn: Any, concept_id: str) -> dict[str, Any]:
    import json

    row = conn.execute(
        "SELECT id, name, category, summary, principles, tradeoffs, alternatives, references_json "
        "FROM concept WHERE id = ?",
        (concept_id,),
    ).fetchone()
    if row is None:
        raise not_found_concept(concept_id)
    d = dict(row)
    d["references"] = json.loads(d.pop("references_json") or "[]")
    return d


def _instances(conn: Any, project_id: int, concept_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ci.id, ci.concept_id, ci.path, ci.lineno, ci.qualname, ci.symbol_id,
               ci.evidence, ci.confidence
        FROM concept_instance ci
        WHERE ci.project_id = ? AND ci.concept_id = ?
        ORDER BY ci.path, ci.lineno
        """,
        (project_id, concept_id),
    ).fetchall()
    return [
        {
            **dict(r),
            "snippet": "",  # 契约要求 snippet；正文由前端按需读取（避免列表膨胀）
        }
        for r in rows
    ]


def _instance_count(conn: Any, project_id: int, concept_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM concept_instance WHERE project_id = ? AND concept_id = ?",
            (project_id, concept_id),
        ).fetchone()[0]
    )


@router.get("/projects/{project_id}/concepts")
def list_concepts(
    project_id: int,
    q: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        _prepare_project(conn, project_id)
        # 概念列表按"本项目有实例"的 concept 表做 LEFT JOIN——没实例的概念
        # 对这个项目没有意义（实例由检测器派生，ADR 0011）。
        where = ["ci.project_id = ?"]
        params: list[Any] = [project_id]
        if q:
            where.append("(c.name LIKE ? OR c.id LIKE ? OR c.summary LIKE ?)")
            params.extend([f"%{q}%"] * 3)
        if category:
            where.append("c.category = ?")
            params.append(category)
        rows = conn.execute(
            f"""
            SELECT c.id, c.name, c.category, c.summary,
                   COUNT(ci.id) AS instance_count,
                   MIN(ci.path) AS first_instance_path
            FROM concept_instance ci
            JOIN concept c ON c.id = ci.concept_id
            WHERE {" AND ".join(where)}
            GROUP BY c.id
            ORDER BY instance_count DESC, c.id
            """,
            params,
        ).fetchall()
        items = [{**dict(r), "concept_id": r["id"], "id": r["id"]} for r in rows]
        return {"items": items, "total": len(items)}
    finally:
        conn.close()


@router.get("/projects/{project_id}/concepts/{concept_id}")
def get_concept(project_id: int, concept_id: str) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        _prepare_project(conn, project_id)
        c = _concept_row(conn, concept_id)
        return {
            "concept_id": c["id"],
            "learning_targets": _learning_targets(c["id"]),
            "name": c["name"],
            "category": c["category"],
            "summary": c["summary"],
            "principles": c["principles"] or "",
            "tradeoffs": c["tradeoffs"] or "",
            "alternatives": c["alternatives"] or "",
            "references": c["references"],
            "instance_count": _instance_count(conn, project_id, concept_id),
            "instance_paths": sorted(
                {
                    r["path"]
                    for r in conn.execute(
                        "SELECT DISTINCT path FROM concept_instance "
                        "WHERE project_id = ? AND concept_id = ? LIMIT 50",
                        (project_id, concept_id),
                    ).fetchall()
                }
            ),
        }
    finally:
        conn.close()


@router.get("/projects/{project_id}/concepts/{concept_id}/instances")
def list_concept_instances(project_id: int, concept_id: str) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        _prepare_project(conn, project_id)
        if conn.execute("SELECT 1 FROM concept WHERE id = ?", (concept_id,)).fetchone() is None:
            raise not_found_concept(concept_id)
        items = _instances(conn, project_id, concept_id)
        return {"items": items, "total": len(items)}
    finally:
        conn.close()


class ExplainBody(BaseModel):
    depth: str = "quick"


@router.post("/projects/{project_id}/concepts/{concept_id}/explain")
async def explain_concept(project_id: int, concept_id: str, body: ExplainBody) -> dict[str, Any]:
    """复用 B 解释服务；低置信候选不升级为事实，deep 失败保留教材。"""
    try:
        depth = ConceptDepth(body.depth)
    except ValueError as exc:
        raise ApiFailure(
            status_code=400,
            code="bad_request",
            title="参数不合法",
            hint="depth 取 quick | project | deep",
        ) from exc
    conn = connect_db(project_id)
    try:
        _prepare_project(conn, project_id)
        c = _concept_row(conn, concept_id)
        instances = _instances(conn, project_id, concept_id)
        concept = Concept(
            id=c["id"],
            name=c["name"],
            category=c["category"],
            summary=c["summary"],
            principles=c["principles"] or "",
            tradeoffs=c["tradeoffs"] or "",
            alternatives=c["alternatives"] or "",
            references=tuple(c["references"]),
            detection=DetectionRules(),
        )
        views = [
            ConceptInstance(
                **{
                    k: i[k]
                    for k in (
                        "concept_id",
                        "path",
                        "lineno",
                        "qualname",
                        "symbol_id",
                        "evidence",
                        "confidence",
                    )
                }
            )
            for i in instances
        ]
        names = {i.qualname for i in views if i.qualname}
        relations = []
        if names and depth != ConceptDepth.QUICK:
            marks = ",".join("?" for _ in names)
            rows = conn.execute(
                "SELECT src.qualname, COALESCE(dst.qualname, e.dst_name), f.path, e.lineno, e.confidence "
                "FROM edge e JOIN symbol src ON src.id = e.src_symbol_id "
                "JOIN file f ON f.id = src.file_id LEFT JOIN symbol dst ON dst.id = e.dst_symbol_id "
                f"WHERE e.project_id = ? AND (src.qualname IN ({marks}) OR dst.qualname IN ({marks})) LIMIT 60",
                (project_id, *names, *names),
            ).fetchall()
            relations = [Relation(*row) for row in rows if row[3] and row[3] > 0]
        provider = None
        if depth == ConceptDepth.DEEP:
            provider = (
                _PROVIDER_FACTORY()
                if _PROVIDER_FACTORY is not None
                else (build_provider() if settings.llm_api_key else None)
            )
        textbook = concept_context(concept_id) if depth == ConceptDepth.DEEP else None
        result = await explain(
            concept,
            instances=views,
            relations=relations,
            depth=depth,
            provider=provider,
            knowledge_content=textbook.content if textbook else "",
            knowledge_sources=[hit.target.href for hit in textbook.references] if textbook else (),
        )
        return {
            **asdict(result),
            "instances": instances,
            "learning_targets": _learning_targets(concept_id)
            + (
                [{**asdict(hit.target), "href": hit.target.href} for hit in textbook.references]
                if textbook
                else []
            ),
        }
    finally:
        conn.close()
