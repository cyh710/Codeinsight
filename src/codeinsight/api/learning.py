"""内置知识 API：全局教材不依赖项目库或模型服务。"""

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import Response

from codeinsight.api.errors import ApiFailure
from codeinsight.api.knowledge import _prepare_project
from codeinsight.api.projects import connect_db
from codeinsight.cognitive.concepts.integration import LearningBridge
from codeinsight.cognitive.concepts.learning_models import KnowledgeError
from codeinsight.cognitive.concepts.library_loader import get_learning_library
from codeinsight.cognitive.concepts.service import KnowledgeService
from codeinsight.cognitive.source_targets import attach_targets

router = APIRouter(tags=["learning"])


@router.get("/knowledge/assets/{asset_id}/{sha256}")
def knowledge_asset(asset_id: str, sha256: str) -> Response:
    """版本化图片不依赖项目索引；损坏或旧版本不影响正文读取。"""
    try:
        asset, content = get_learning_library().visuals.read(asset_id, sha256)
    except KnowledgeError as exc:
        raise ApiFailure(
            status_code=404,
            code="not_found",
            title="教学图暂不可用",
            hint="章节文字仍可阅读；可重试或打开当前版本。",
            detail=str(exc),
        ) from exc
    return Response(
        content,
        media_type=asset.media_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{asset.sha256}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        },
    )


def _bridge() -> LearningBridge:
    try:
        return LearningBridge(KnowledgeService(get_learning_library()))
    except KnowledgeError as exc:
        raise ApiFailure(
            status_code=503,
            code="internal_error",
            title="知识库暂不可用",
            hint="请检查知识资产安装。",
            detail=str(exc),
        ) from exc


@router.get("/knowledge/tree")
def knowledge_tree() -> dict[str, Any]:
    return _bridge().tree().data


@router.get("/knowledge/topics/{topic_id}")
def knowledge_topic(topic_id: str) -> dict[str, Any]:
    result = _bridge().topic(topic_id)
    if result.error:
        raise ApiFailure(
            status_code=404, code="not_found", title="知识主题不存在", hint="请从知识目录重新选择。"
        )
    return result.data


@router.get("/knowledge/search")
def knowledge_search(q: str = "", limit: int = Query(default=8, ge=1, le=50)) -> dict[str, Any]:
    """教材检索。

    `limit` 是**章节**数（契约 §11）——同一篇文章的多个章节都会命中，
    界面按文章合并展示。取章节而不是文章，是因为章节才是检索的粒度。
    """
    return _bridge().search(q, limit).data


@router.get("/projects/{project_id}/knowledge/topics/{topic_id}/instances")
def topic_instances(project_id: int, topic_id: str) -> dict[str, Any]:
    """只展示索引派生的概念实例；教学示例不能充当项目命中。"""
    bridge = _bridge()
    topic = bridge.library.get(topic_id)
    if topic is None:
        raise ApiFailure(status_code=404, code="not_found", title="知识主题不存在")
    conn = connect_db(project_id)
    try:
        _prepare_project(conn, project_id)
        state = conn.execute(
            "SELECT head_commit, index_epoch FROM repo_state WHERE project_id = ?", (project_id,)
        ).fetchone()
        items = []
        total = 0
        if topic.concept_ids:
            marks = ",".join("?" for _ in topic.concept_ids)
            rows = conn.execute(
                "SELECT id, concept_id, path, lineno, qualname, symbol_id, evidence, confidence "
                f"FROM concept_instance WHERE project_id = ? AND concept_id IN ({marks}) "
                "ORDER BY confidence DESC, path, lineno LIMIT 50",
                (project_id, *topic.concept_ids),
            ).fetchall()
            items = [{**dict(row), "snippet": ""} for row in rows]
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM concept_instance WHERE project_id = ? AND concept_id IN ({marks})",
                    (project_id, *topic.concept_ids),
                ).fetchone()[0]
            )
        return {
            "items": attach_targets(conn, project_id, items),
            "total": total,
            "limit": 50,
            "status": "ok" if state and state["index_epoch"] > 0 else "not_indexed",
            "head_commit": state["head_commit"] if state else None,
            "index_epoch": state["index_epoch"] if state else None,
        }
    finally:
        conn.close()
