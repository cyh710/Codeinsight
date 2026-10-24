"""导入项目的索引调度（契约 §3.3 的异步建索引）。

直接调 A 线的 `index_project`（`cognitive/indexing/indexer.py`）——引擎
自带全套记账（repo_state、成功路径的 index_run），这里只补两件事：

1. **失败记账**：引擎只在成功路径写 index_run；异常抛出时 API 层补一条
   ok=0 的 run，让 `GET /projects/{id}` 的状态推导能如实给出 `failed`，
   而不是永远停在 `indexing`。
2. **同名复用语义**：引擎按名字复用项目行，API 层的重复导入规则与之对齐
   （见 `projects.create_project`）。
"""

from __future__ import annotations

import json
import subprocess

from codeinsight.api.errors import bad_request
from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.indexing import index_project
from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path, open_sqlite


def validate_root_path(root_path: str) -> None:
    """POST /projects 的前置校验（契约 §3.3 的 bad_request 场景）。"""
    from pathlib import Path

    p = Path(root_path)
    if not root_path.strip():
        raise bad_request("root_path 不能为空")
    if not p.is_dir():
        raise bad_request(f"root_path 不是目录：{root_path}", hint="给一个本地仓库的绝对路径")


def _git_head(root_path: str, ref: str | None) -> str | None:
    """取 ref（缺省 HEAD）的 commit sha；取不到返回 None。"""
    cmd = ["git", "-C", root_path, "rev-parse", ref or "HEAD"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
    except (subprocess.SubprocessError, OSError):
        return None
    return out.stdout.strip() or None


def start_indexing(project_id: int, name: str, root_path: str, ref: str | None) -> None:
    """后台索引任务：调引擎；引擎抛异常时补记失败的 index_run。"""
    path = db_path(settings.data_dir)
    try:
        index_project(
            path,
            root=root_path,
            name=name,
            ref=ref,
            max_chunk_lines=settings.max_chunk_lines,
            concepts_dir=knowledge_directory("concepts"),
        )
    except Exception as exc:
        # 引擎失败不算 API 失败：项目状态如实转 failed，错误写进 run 的
        # stats_json 供排查；不往上抛（后台任务里抛了也没人接）。
        conn = open_sqlite(path, row_factory=True)
        try:
            conn.execute(
                "INSERT INTO index_run (project_id, head_commit, mode, started_at, finished_at,"
                " ok, stats_json) VALUES (?, ?, 'full', datetime('now'), datetime('now'), 0, ?)",
                (
                    project_id,
                    _git_head(root_path, ref) or "",
                    json.dumps(
                        {"error": type(exc).__name__, "detail": str(exc)[:500]},
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.commit()
        finally:
            conn.close()
