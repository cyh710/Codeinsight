"""健康检查与索引状态端点。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter

from codeinsight import __version__
from codeinsight.config import settings
from codeinsight.runtime_version import runtime_status
from codeinsight.storage.sqlite import db_path, open_sqlite

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    """存活探针 + 索引库是否已建。"""
    path = db_path(settings.data_dir)
    indexed = False
    projects = 0
    if path.exists():
        try:
            with open_sqlite(path, row_factory=True) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name='project'"
                ).fetchone()
                if row and row["n"]:
                    indexed = True
                    projects = conn.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"]
        except sqlite3.Error:
            indexed = False
    return {
        "status": "ok",
        "version": __version__,
        "db_path": str(path),
        "db_exists": path.exists(),
        "schema_applied": indexed,
        "projects": projects,
        **runtime_status(),
    }


@router.get("/projects")
def list_projects() -> list[dict[str, object]]:
    """已索引的项目列表。"""
    path = db_path(settings.data_dir)
    if not path.exists():
        return []
    try:
        with open_sqlite(path, row_factory=True) as conn:
            exists = conn.execute(
                "SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name='project'"
            ).fetchone()["n"]
            if not exists:
                return []
            rows = conn.execute(
                """
                SELECT p.id, p.name, p.root_path, rs.head_commit, rs.head_branch,
                       rs.indexed_at, rs.index_epoch,
                       (SELECT COUNT(*) FROM file f WHERE f.project_id = p.id) AS files,
                       (SELECT COUNT(*) FROM symbol s WHERE s.project_id = p.id) AS symbols,
                       (SELECT COUNT(*) FROM chunk c WHERE c.project_id = p.id) AS chunks
                FROM project p
                LEFT JOIN repo_state rs ON rs.project_id = p.id
                ORDER BY p.id
                """
            ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(r) for r in rows]
