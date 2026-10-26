"""FastAPI 应用：路由接线与错误归一。

各路由模块只做查询与组装；一切失败经 `errors.install_error_handlers`
归一成契约 §0.3 的唯一错误形状。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from codeinsight import __version__
from codeinsight.api.code import router as code_router
from codeinsight.api.conversations import router as conversations_router
from codeinsight.api.errors import install_error_handlers
from codeinsight.api.health import router as health_router
from codeinsight.api.insights import router as insights_router
from codeinsight.api.knowledge import router as knowledge_router
from codeinsight.api.learning import router as learning_router
from codeinsight.api.local import router as local_router
from codeinsight.api.overview import router as overview_router
from codeinsight.api.projects import router as projects_router
from codeinsight.api.query import router as query_router
from codeinsight.api.relocation import recover_relocations
from codeinsight.api.structure import router as structure_router
from codeinsight.config import settings
from codeinsight.storage.conversations import ConversationRepository
from codeinsight.storage.sqlite import db_path, ensure_schema, open_sqlite


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = db_path(settings.data_dir)
    if path.exists():
        ensure_schema(path)
        with open_sqlite(path, row_factory=True) as conn:
            recover_relocations(conn)
            repository = ConversationRepository(conn)
            repository.backfill()
            repository.recover()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        title="CodeInsight",
        version=__version__,
        description="基于持续项目认知的智能代码理解与知识探索 Agent",
    )
    app.include_router(health_router)
    app.include_router(local_router)
    app.include_router(projects_router)
    app.include_router(overview_router)
    app.include_router(knowledge_router)
    app.include_router(learning_router)
    app.include_router(code_router)
    app.include_router(conversations_router)
    app.include_router(insights_router)
    app.include_router(structure_router)
    app.include_router(query_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "CodeInsight",
            "version": __version__,
            "data_dir": str(settings.data_dir),
        }

    install_error_handlers(app)
    return app


app = create_app()
