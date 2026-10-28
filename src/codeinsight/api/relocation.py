"""源码重新定位：路径与完整索引一起提交，失败保留原有项目和历史。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from codeinsight.api.indexing import _default_concepts_dir
from codeinsight.cognitive.indexing.staging import build_and_publish_index
from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path, open_sqlite


def rebuild_relocated_project(
    project_id: int,
    root_path: str,
    run_id: int,
    *,
    ref: str | None = None,
    operation: str = "relocate",
) -> None:
    """只处理已预留的运行记录；重建失败回滚路径、索引及其版本，不删除会话。"""
    with closing(open_sqlite(db_path(settings.data_dir))) as conn:
        try:
            stats = build_and_publish_index(
                conn,
                project_id,
                root_path,
                ref,
                max_chunk_lines=settings.max_chunk_lines,
                concepts_dir=_default_concepts_dir(),
            )
            conn.execute(
                "UPDATE index_run SET head_commit = ?, finished_at = datetime('now'), ok = 1, "
                "files_total = ?, symbols_added = ? WHERE id = ? AND project_id = ?",
                (stats["head_commit"], stats["files"], stats["symbols"], run_id, project_id),
            )
            conn.commit()
        except Exception as exc:
            # 后台任务不能把异常丢给已返回 202 的页面；回滚后另记失败原因供轮询展示。
            conn.rollback()
            conn.execute(
                "UPDATE index_run SET finished_at = datetime('now'), ok = 0, stats_json = ? "
                "WHERE id = ? AND project_id = ?",
                (
                    json.dumps(
                        {
                            "operation": operation,
                            "error": "索引未完成，请检查项目目录和提交版本后重试；原记录已保留。",
                            "detail": str(exc)[:500],
                        },
                        ensure_ascii=False,
                    ),
                    run_id,
                    project_id,
                ),
            )
            conn.commit()


def recover_relocations(conn: sqlite3.Connection) -> None:
    """单后端进程重启后将遗留重新定位标为失败；事务未提交的旧数据自动恢复。"""
    conn.execute(
        "UPDATE index_run SET finished_at = datetime('now'), ok = 0, "
        "stats_json = json_set(stats_json, '$.error', ?) "
        "WHERE finished_at IS NULL AND json_valid(stats_json) "
        "AND json_extract(stats_json, '$.operation') IN ('relocate', 'import')",
        ("服务重启中断了索引，原记录已保留，请重试。",),
    )
    conn.commit()


def latest_index_error(conn: sqlite3.Connection, project_id: int) -> str | None:
    """只暴露最后一次失败记录的已有说明，不从源码缺失推测失败原因。"""
    row = conn.execute(
        "SELECT ok, stats_json FROM index_run WHERE project_id = ? ORDER BY id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row is None or row[0] or not row[1]:
        return None
    try:
        stats = json.loads(row[1])
        return str(stats.get("error", "")) or None
    except (ValueError, AttributeError):
        return None
