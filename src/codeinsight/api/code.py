"""代码阅读只接受当前项目索引中的路径，并读取与索引匹配的源码快照。"""

import hashlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from codeinsight.api.errors import ApiFailure
from codeinsight.api.projects import connect_db, require_project
from codeinsight.cognitive.indexing.scanner import read_blobs

router = APIRouter(tags=["code"])


@router.get("/projects/{project_id}/code")
def read_code(
    project_id: int, path: str, start_line: int = Query(1, ge=1), end_line: int | None = None
) -> dict[str, Any]:
    """返回最多 200 行；客户端说明和未索引文件都不能提供代码证据。"""
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        row = conn.execute(
            "SELECT f.content_sha256, p.root_path, rs.head_commit FROM file f "
            "JOIN project p ON p.id = f.project_id "
            "LEFT JOIN repo_state rs ON rs.project_id = p.id WHERE f.project_id = ? AND f.path = ?",
            (project_id, path),
        ).fetchone()
        if row is None:
            raise ApiFailure(status_code=404, code="symbol_not_found", title="索引中没有这个文件")
        if end_line is not None and end_line < start_line:
            raise ApiFailure(status_code=400, code="bad_request", title="结束行不能早于起始行")
        try:
            raw = read_blobs(Path(row["root_path"]), row["head_commit"], [path])[path]
        except (OSError, ValueError, KeyError) as exc:
            raise ApiFailure(
                status_code=409,
                code="not_indexed",
                title="无法读取对应的源码快照",
                hint="请确认仓库可用，必要时重建索引。",
            ) from exc
        if hashlib.sha256(raw).hexdigest() != row["content_sha256"]:
            raise ApiFailure(
                status_code=409,
                code="not_indexed",
                title="源码与索引版本不一致",
                hint="请重建索引后继续阅读。",
            )
        lines = raw.decode("utf-8", "replace").splitlines()
        if start_line > len(lines):
            raise ApiFailure(status_code=400, code="bad_request", title="起始行超出文件范围")
        end = min(end_line or start_line + 199, start_line + 199, len(lines))
        return {
            "path": path,
            "start_line": start_line,
            "end_line": max(start_line, end),
            "content": "\n".join(lines[start_line - 1 : end]),
            "head_commit": row["head_commit"],
            "content_sha256": row["content_sha256"],
            "total_lines": len(lines),
        }
    finally:
        conn.close()
