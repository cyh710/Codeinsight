"""默认阅读当前工作区，显式历史目标按已登记源码版本恢复。"""

from typing import Any

from fastapi import APIRouter, Query

from codeinsight.api.errors import ApiFailure
from codeinsight.api.projects import connect_db, require_project
from codeinsight.cognitive.indexing.source_store import SourceError, read_source
from codeinsight.cognitive.workspace import read_workspace

router = APIRouter(tags=["code"])


@router.get("/projects/{project_id}/code")
def read_code(
    project_id: int,
    path: str,
    start_line: int = Query(1, ge=1),
    end_line: int | None = None,
    content_sha256: str | None = None,
    head_commit: str | None = None,
    index_epoch: int | None = Query(None, ge=1),
    source_kind: str | None = None,
) -> dict[str, Any]:
    """返回最多200行真实字节；历史身份按项目/路径核对，不信任客户端正文。"""
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        if end_line is not None and end_line < start_line:
            raise ApiFailure(status_code=400, code="bad_request", title="结束行不能早于起始行")
        try:
            kind = source_kind or (
                "index"
                if index_epoch is not None or head_commit is not None or content_sha256 is not None
                else "workspace"
            )
            if kind not in {"workspace", "index"}:
                raise SourceError("未知源码类型。", "bad_request")
            source = (
                read_workspace(conn, project_id, path, content_sha256)
                if kind == "workspace"
                else read_source(
                    conn,
                    project_id,
                    path,
                    expected_sha=content_sha256,
                    head_commit=head_commit,
                    index_epoch=index_epoch,
                )
            )
        except SourceError as exc:
            raise ApiFailure(
                status_code=404
                if exc.code == "not_found"
                else 400
                if exc.code == "bad_request"
                else 409,
                code="symbol_not_found"
                if exc.code == "not_found"
                else "bad_request"
                if exc.code == "bad_request"
                else "reading_invalid"
                if kind == "workspace"
                else "not_indexed",
                title="无法读取对应源码版本",
                hint=str(exc),
            ) from exc
        raw = source.raw
        lines = raw.decode("utf-8", "replace").splitlines()
        if start_line > max(1, len(lines)):
            raise ApiFailure(status_code=400, code="bad_request", title="起始行超出文件范围")
        end = min(end_line or start_line + 199, start_line + 199, len(lines))
        return {
            "path": path,
            "source_kind": kind,
            "start_line": start_line,
            "end_line": max(start_line, end),
            "content": "\n".join(lines[start_line - 1 : end]),
            "head_commit": source.head_commit,
            "content_sha256": source.sha256,
            "workspace_changed": source.workspace_changed,
            "total_lines": len(lines),
            **({"index_epoch": source.index_epoch} if source.index_epoch is not None else {}),
        }
    finally:
        conn.close()
