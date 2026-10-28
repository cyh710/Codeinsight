"""契约 §0.3：唯一的错误响应形状。

所有非 2xx 的 body 都是 ``{"error": {code, title, hint, detail}}``——
没有第二个变体。前端按 ``code`` switch，未知 code 兜底按 ``internal_error``
处理（前端 client.ts 已按此实现），后端要做的就是把一切失败归一到这个形状。
"""

from __future__ import annotations

import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiFailure(Exception):
    """抛出即返回契约错误形状。路由层唯一的失败表达方式。"""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        title: str,
        hint: str = "",
        detail: str = "",
    ) -> None:
        super().__init__(f"{title}（{code}）")
        self.status_code = status_code
        self.code = code
        self.title = title
        self.hint = hint
        self.detail = detail

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content={
                "error": {
                    "code": self.code,
                    "title": self.title,
                    "hint": self.hint,
                    "detail": self.detail,
                }
            },
        )


def not_found_project(project_id: int) -> ApiFailure:
    return ApiFailure(
        status_code=404,
        code="project_not_found",
        title="项目不存在",
        hint="先 POST /projects 建索引，再使用返回的 id",
        detail=f"project_id={project_id}",
    )


def not_found_symbol(qualname: str) -> ApiFailure:
    return ApiFailure(
        status_code=404,
        code="symbol_not_found",
        title="符号不存在",
        hint="检查 qualname 拼写，或先在符号列表里搜索",
        detail=f"qualname={qualname}",
    )


def not_found_concept(concept_id: str) -> ApiFailure:
    return ApiFailure(
        status_code=404,
        code="concept_not_found",
        title="概念不存在",
        hint="概念由本体定义并经检测器落到实例表；检查 concept_id 或等待检测器跑完",
        detail=f"concept_id={concept_id}",
    )


def bad_request(detail: str, *, hint: str = "") -> ApiFailure:
    return ApiFailure(
        status_code=400, code="bad_request", title="参数不合法", hint=hint, detail=detail
    )


def install_error_handlers(app: FastAPI) -> None:
    """把一切失败（含框架自身 404/422/500）归一到契约形状。"""

    @app.exception_handler(ApiFailure)
    async def _api_failure(_req: Request, exc: ApiFailure) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
        # 框架路由 404 等：归一为 internal_error 系的契约形状（code 保持机器可读）。
        code = {404: "project_not_found", 405: "bad_request", 422: "bad_request"}.get(
            exc.status_code, "internal_error"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "title": str(exc.detail) or "请求失败",
                    "hint": "",
                    "detail": f"HTTP {exc.status_code}",
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_req: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "bad_request",
                    "title": "参数不合法",
                    "hint": "对照 docs/api-contract.md 检查请求体字段",
                    "detail": str(exc.errors()[:3]),
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_req: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, sqlite3.OperationalError) and any(
            word in str(exc).lower() for word in ("locked", "busy")
        ):
            return ApiFailure(
                status_code=503,
                code="internal_error",
                title="本地数据库暂时繁忙",
                hint="请稍后重试；已保存的对话和资料仍会保留。",
                detail="database_busy",
            ).to_response()
        # 兜底：任何未捕获异常都不得返回非契约形状（前端不允许白屏）。
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "title": "服务异常",
                    "hint": "请稍后重试；若持续出现，查看后端日志",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            },
        )
