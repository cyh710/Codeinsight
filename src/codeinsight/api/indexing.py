"""导入项目的索引调度（契约 §3.3 的异步建索引）。

**引擎接缝**：本模块是 API 层与索引引擎之间的**唯一接缝**。

A 线的落库索引器已落地（`cognitive/indexing/indexer.py::run_index`，
规格 §1.2 A3/A4/A5/A6/A7），按 `docs/requests/0002-index-engine-entry.md`
的约定签名接上：

    run_index(conn, project_id, root_path, ref) -> dict

引擎缺席时：索引 run 如实记为失败（status=failed），错误信息可读，
绝不假装索引成功（ADR 0007 的"事实与推断分开"在运维层面同理）。
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from collections.abc import Callable

from codeinsight.api.errors import bad_request
from codeinsight.cognitive.indexing.indexer import run_index
from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path, open_sqlite

# 引擎入口：A 线的落库索引器（docs/requests/0002-index-engine-entry.md）。
# 签名：(conn, project_id, root_path, ref) -> 统计字典
_ENGINE_CALLABLE: Callable[[sqlite3.Connection, int, str, str | None], None] | None = run_index


def validate_root_path(root_path: str) -> None:
    """POST /projects 的前置校验（契约 §3.3 的 bad_request 场景）。"""
    from pathlib import Path

    p = Path(root_path)
    if not root_path.strip():
        raise bad_request("root_path 不能为空")
    if not p.is_dir():
        raise bad_request(f"root_path 不是目录：{root_path}", hint="给一个本地仓库的绝对路径")


def _git_head(root_path: str, ref: str | None) -> tuple[str | None, str | None]:
    """取 head_commit / head_branch；非 git 目录返回 (None, ref)。"""
    cmd = ["git", "-C", root_path]
    if ref:
        cmd += ["rev-parse", ref]
    else:
        cmd += ["rev-parse", "HEAD"]
    try:
        sha = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
    except (subprocess.SubprocessError, OSError):
        return None, ref
    head = sha.stdout.strip() or None
    branch = ref
    if branch is None and head:
        try:
            sym = subprocess.run(
                ["git", "-C", root_path, "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            branch = sym.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            branch = None
    return head, branch


def start_indexing(project_id: int, root_path: str, ref: str | None) -> None:
    """后台索引任务：记 index_run、更新 repo_state、调引擎（或缺席记失败）。"""
    path = db_path(settings.data_dir)
    head, branch = _git_head(root_path, ref)

    conn = open_sqlite(path, row_factory=True)
    try:
        cur = conn.execute(
            "INSERT INTO index_run (project_id, base_commit, head_commit, mode, started_at) "
            "VALUES (?, NULL, ?, 'full', datetime('now'))",
            (project_id, head or ""),
        )
        run_id = int(cur.lastrowid)

        conn.execute(
            """
            INSERT INTO repo_state (project_id, head_commit, head_branch, parser_version)
            VALUES (?, ?, ?, 'pending')
            ON CONFLICT(project_id) DO UPDATE SET
                head_commit = excluded.head_commit,
                head_branch = excluded.head_branch,
                indexed_at = NULL
            """,
            (project_id, head, branch),
        )

        if _ENGINE_CALLABLE is None:
            conn.execute(
                "UPDATE index_run SET finished_at = datetime('now'), ok = 0, "
                "stats_json = ? WHERE id = ?",
                (
                    json.dumps(
                        {
                            "error": "索引引擎未合入",
                            "detail": "A 线 M1 落库索引器（规格 §1.2 A3）尚未落地；"
                            "见 docs/requests/0002-index-engine-entry.md",
                        },
                        ensure_ascii=False,
                    ),
                    run_id,
                ),
            )
            conn.commit()
            return

        try:
            _ENGINE_CALLABLE(conn, project_id, root_path, ref)
            conn.execute(
                "UPDATE index_run SET finished_at = datetime('now'), ok = 1 WHERE id = ?",
                (run_id,),
            )
            conn.execute(
                "UPDATE repo_state SET indexed_at = datetime('now'), "
                "index_epoch = index_epoch + 1 WHERE project_id = ?",
                (project_id,),
            )
        except Exception as exc:  # 引擎失败不算 API 失败：run 记失败，项目状态 failed
            conn.execute(
                "UPDATE index_run SET finished_at = datetime('now'), ok = 0, stats_json = ? "
                "WHERE id = ?",
                (
                    json.dumps(
                        {"error": type(exc).__name__, "detail": str(exc)[:500]}, ensure_ascii=False
                    ),
                    run_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()
