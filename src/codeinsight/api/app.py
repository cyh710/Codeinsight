"""FastAPI 应用。

当前只提供骨架与健康检查；各业务端点在对应里程碑接入。
"""

from __future__ import annotations

from fastapi import FastAPI

from codeinsight import __version__
from codeinsight.api.health import router as health_router
from codeinsight.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="CodeInsight",
        version=__version__,
        description="基于持续项目认知的智能代码理解与知识探索 Agent",
    )
    app.include_router(health_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "CodeInsight",
            "version": __version__,
            "data_dir": str(settings.data_dir),
        }

    return app


app = create_app()
