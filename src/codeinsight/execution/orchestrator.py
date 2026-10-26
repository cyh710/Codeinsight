"""编排器：执行任务的状态机与后台执行（请求 0015 / ADR 0032）。

```
planned ──approve──▶ executing ──(完成)──▶ review ──merge──▶ merged（学习卡后台生成）
   │                    │                     │
 reject                abort                  abort
   ▼                    ▼                     ▼
rejected             aborted                aborted（均删隔离 worktree，仓库回原样）
                     （失败/超时）▶ failed
```

线程模型：一个常驻后台线程跑专属 asyncio 事件环，执行任务以协程提交
（`run_coroutine_threadsafe`）；HTTP 线程只做同步的 DB 迁移与提交。
每个协程自己开 SQLite 连接——连接不跨线程共享。
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from codeinsight.config import settings
from codeinsight.execution import worktree
from codeinsight.execution.claude_code import driver_from_settings
from codeinsight.execution.driver import ExecutionProgress, ExecutionRequest
from codeinsight.storage.sqlite import db_path, open_sqlite

PLANNED = "planned"
EXECUTING = "executing"
REVIEW = "review"
MERGED = "merged"
REJECTED = "rejected"
ABORTED = "aborted"
FAILED = "failed"

# (当前状态, 动作) → 目标状态。不在表里的迁移一律 409。
TRANSITIONS: dict[tuple[str, str], str] = {
    (PLANNED, "approve"): EXECUTING,
    (PLANNED, "reject"): REJECTED,
    (EXECUTING, "abort"): ABORTED,
    (REVIEW, "abort"): ABORTED,
    (REVIEW, "merge"): MERGED,
}

_PROGRESS_CAP = 200


class TransitionError(Exception):
    """非法状态迁移或任务不存在。API 层转 409/404。"""

    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


# ─── 后台事件环 ───────────────────────────────────────────────

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()
_tasks: dict[str, asyncio.Task[None]] = {}


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is not None and not _loop.is_closed():
            return _loop

        ready = threading.Event()

        def _run() -> None:
            global _loop
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
            ready.set()
            _loop.run_forever()

        threading.Thread(target=_run, name="ci-exec", daemon=True).start()
        ready.wait(timeout=10)
        assert _loop is not None
        return _loop


def _submit(task_id: str, coro: Any) -> Future[None]:
    loop = _ensure_loop()

    async def _wrapped() -> None:
        # 注册**环内**的 Task：跨线程取消必须 cancel 环内对象。
        running = asyncio.current_task()
        if running is not None:
            _tasks[task_id] = running
        try:
            await coro
        finally:
            _tasks.pop(task_id, None)

    return asyncio.run_coroutine_threadsafe(_wrapped(), loop)


# ─── DB 助手 ──────────────────────────────────────────────────


def _open() -> sqlite3.Connection:
    conn = open_sqlite(db_path(settings.data_dir), row_factory=True)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _load(conn: sqlite3.Connection, project_id: int, task_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM execution_task WHERE id = ? AND project_id = ?", (task_id, project_id)
    ).fetchone()
    if row is None:
        raise TransitionError(f"执行任务不存在：{task_id}", status_code=404)
    return dict(row)


def _patch(conn: sqlite3.Connection, task_id: str, **fields: Any) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE execution_task SET {sets} WHERE id = ?", (*fields.values(), task_id)
    )
    conn.commit()


def _result_json(row: dict[str, Any]) -> dict[str, Any]:
    return json.loads(row.get("result_json") or "{}")


# ─── 对外接口 ─────────────────────────────────────────────────


def new_task_id() -> str:
    return f"exec-{secrets.token_hex(4)}"


def create_execution(
    project_id: int, question: str, plan: dict[str, Any], conversation_id: str | None
) -> dict[str, Any]:
    task_id = new_task_id()
    conn = _open()
    try:
        conn.execute(
            "INSERT INTO execution_task (id, project_id, conversation_id, question, plan_json,"
            " status, driver, result_json) VALUES (?, ?, ?, ?, ?, 'planned', ?, '{}')",
            (
                task_id,
                project_id,
                conversation_id,
                question,
                json.dumps(plan, ensure_ascii=False),
                settings.executor if settings.executor != "off" else "claude-code",
            ),
        )
        conn.commit()
        return _load(conn, project_id, task_id)
    finally:
        conn.close()


def get_execution(project_id: int, task_id: str) -> dict[str, Any]:
    conn = _open()
    try:
        return _load(conn, project_id, task_id)
    finally:
        conn.close()


def execution_public(row: dict[str, Any]) -> dict[str, Any]:
    """契约 §16.2 的 execution 元数据形状。"""
    result = _result_json(row)
    return {
        "task_id": row["id"],
        "status": row["status"],
        "plan": json.loads(row["plan_json"]),
        "progress": result.get("progress", []),
        "diff_summary": result.get("diff_summary"),
        "change_card": result.get("change_card"),
        "summary": result.get("summary", ""),
        "error": result.get("error"),
    }


def transition(project_id: int, task_id: str, action: str) -> dict[str, Any]:
    """执行 approve/reject/abort/merge；返回迁移后的任务行。"""
    if action not in {"approve", "reject", "abort", "merge"}:
        raise TransitionError(f"未知动作：{action}", status_code=400)

    conn = _open()
    try:
        row = _load(conn, project_id, task_id)
        target = TRANSITIONS.get((row["status"], action))
        if target is None:
            raise TransitionError(
                f"任务处于 {row['status']}，不允许 {action}", status_code=409
            )

        if action == "approve":
            _patch(conn, task_id, status=EXECUTING)
            _submit(task_id, _execute_and_review(task_id))
        elif action in ("reject", "abort"):
            if action == "abort":
                _cancel_running(task_id)
            _cleanup_worktree_safely(row)
            _patch(
                conn,
                task_id,
                status=target,
                finished_at=sql_now(),
            )
        elif action == "merge":
            _do_merge(conn, row, target)
    finally:
        conn.close()
    return get_execution(project_id, task_id)


def sql_now() -> str:
    """与 sqlite datetime('now') 同口径的 UTC 时间串。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _cancel_running(task_id: str) -> None:
    """从 HTTP 线程取消后台环里的协程（handle 是环内 Task）。"""
    task = _tasks.get(task_id)
    loop = _loop
    if task is None or loop is None:
        return
    loop.call_soon_threadsafe(task.cancel)


def _cleanup_worktree_safely(row: dict[str, Any]) -> None:
    if not row.get("worktree_path") or not row.get("branch"):
        return
    try:
        worktree.remove_task_worktree(
            worktree.TaskWorktree(
                path=Path(row["worktree_path"]),
                branch=row["branch"],
                base_commit=row.get("commit_before") or "HEAD",
                repo_root=_repo_root(row),
            )
        )
    except Exception:
        # 清理失败不挡状态迁移；目录残留可人工删（worktree_path 已留痕）。
        pass


def _repo_root(row: dict[str, Any]) -> Path:
    conn = _open()
    try:
        proj = conn.execute(
            "SELECT root_path FROM project WHERE id = ?", (row["project_id"],)
        ).fetchone()
    finally:
        conn.close()
    if proj is None or not proj["root_path"]:
        raise TransitionError("项目缺少 root_path，无法操作 worktree", status_code=409)
    return Path(proj["root_path"])


# ─── 后台协程 ─────────────────────────────────────────────────


async def _execute_and_review(task_id: str) -> None:
    """approved 之后的主流程：建 worktree → 执行 → review/failed。"""
    conn = _open()
    try:
        row = _load_by_id(conn, task_id)
    finally:
        conn.close()

    repo_root = _repo_root_of(row["project_id"])
    driver = driver_from_settings()
    if driver is None:
        _mark(task_id, FAILED, error="执行器已关闭（CI_EXECUTOR=off）")
        return

    progress: list[dict[str, Any]] = []

    def emit(p: ExecutionProgress) -> None:
        entry = {"kind": p.kind, "tool": p.tool, "file": p.file, "detail": p.detail}
        if len(progress) < _PROGRESS_CAP:
            progress.append(entry)
            _merge_result(task_id, progress=progress)

    try:
        task = worktree.create_task_worktree(repo_root, task_id)
        _patch_by_id(task_id, branch=task.branch, worktree_path=str(task.path),
                     commit_before=task.base_commit)
        request = ExecutionRequest(
            worktree=task.path,
            repo_root=repo_root,
            prompt=_task_prompt(row),
            base_commit=task.base_commit,
            timeout_s=settings.executor_timeout_s,
            commit_message=f"ci-exec: {row['question'][:60]}",
        )
        result = await driver.execute(request, emit)
    except asyncio.CancelledError:
        _cleanup_row_worktree(task_id)
        _mark(task_id, ABORTED, error="用户中止")
        return
    except Exception as exc:
        _cleanup_row_worktree(task_id)
        _mark(task_id, FAILED, error=f"{type(exc).__name__}: {exc}")
        return

    if result.ok:
        summary_diff = worktree.diff_summary(_task_worktree_of(row, task_id), result.commit_sha or "")
        _mark(
            task_id,
            REVIEW,
            summary=result.summary,
            commit_after=result.commit_sha,
            changed_files=list(result.changed_files),
            diff_summary=summary_diff,
        )
    else:
        _cleanup_row_worktree(task_id)
        _mark(task_id, FAILED, summary=result.summary, error=result.error)


def _do_merge(conn: sqlite3.Connection, row: dict[str, Any], target: str) -> None:
    """merge 动作的同步部分：干净检查 → 合入 → 交后台生成学习卡。"""
    repo_root = _repo_root(row)
    if not worktree.repo_is_clean(repo_root):
        raise TransitionError(
            "用户工作区有未提交改动，请先处理（你的改动永远优先）", status_code=409
        )
    task = worktree.TaskWorktree(
        path=Path(row["worktree_path"]),
        branch=row["branch"],
        base_commit=row["commit_before"] or "HEAD",
        repo_root=repo_root,
    )
    merged_sha = worktree.merge_into_current(task, f"merge {row['id']}: {row['question'][:50]}")
    _patch(conn, row["id"], status=target, commit_after=merged_sha, finished_at=sql_now())
    # 学习卡与清理在后台：增量索引以秒计，不该占住 HTTP 请求。
    _submit(row["id"], _finalize_learning(row["id"]))


async def _finalize_learning(task_id: str) -> None:
    """merged 之后的闭环：增量索引 → 变更学习卡 → 清理 worktree。"""
    from codeinsight.api.indexing import _default_concepts_dir
    from codeinsight.cognitive.changes.service import build_changes
    from codeinsight.cognitive.indexing import index_project

    conn = _open()
    try:
        row = _load_by_id(conn, task_id)
        proj = conn.execute(
            "SELECT name, root_path FROM project WHERE id = ?", (row["project_id"],)
        ).fetchone()
    finally:
        conn.close()
    if proj is None:
        return

    try:
        index_project(
            db_path(settings.data_dir),
            root=Path(proj["root_path"]),
            name=proj["name"],
            incremental=True,
            concepts_dir=_default_concepts_dir(),
        )
    except Exception as exc:
        # 索引失败不影响 merge 结果本身：学习卡缺位、原因可读（降级不抛，ADR 0012）。
        _merge_result(task_id, change_card_error=f"增量索引失败：{exc}")
        _cleanup_row_worktree(task_id)
        return

    conn = _open()
    try:
        changes = build_changes(conn, row["project_id"])
    finally:
        conn.close()
    _merge_result(task_id, change_card=_change_card(changes))
    _cleanup_row_worktree(task_id)


def _change_card(changes: dict[str, Any]) -> dict[str, Any]:
    """/changes 的数据 → 契约 §16.3 的 change_card（全部来自索引事实）。"""
    facts = [
        {
            "text": f"{s['qualname']}：{s['change']}",
            "citation": {
                "path": s["path"],
                "lineno": s["lineno"],
                "end_lineno": s["lineno"],
                "qualname": s["qualname"],
                "snippet": "",
            },
        }
        for s in changes.get("changed_symbols", [])
    ]
    impacted = changes.get("impacted", {})
    return {
        "facts": facts,
        "impacted": {
            "modules": impacted.get("modules", []),
            "symbols": impacted.get("symbols", []),
        },
        "concept_ids": impacted.get("concept_ids", []),
    }


# ─── 行级小助手 ───────────────────────────────────────────────


def _load_by_id(conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM execution_task WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise TransitionError(f"执行任务不存在：{task_id}", status_code=404)
    return dict(row)


def _patch_by_id(task_id: str, **fields: Any) -> None:
    conn = _open()
    try:
        _patch(conn, task_id, **fields)
    finally:
        conn.close()


def _merge_result(task_id: str, **fields: Any) -> None:
    """往 result_json 里合并字段（进度/摘要/diff/学习卡共用）。"""
    conn = _open()
    try:
        row = _load_by_id(conn, task_id)
        result = _result_json(row)
        result.update(fields)
        _patch(conn, task_id, result_json=json.dumps(result, ensure_ascii=False))
    finally:
        conn.close()


def _mark(task_id: str, status: str, **result_fields: Any) -> None:
    conn = _open()
    try:
        row = _load_by_id(conn, task_id)
        result = _result_json(row)
        result.update(result_fields)
        _patch(
            conn,
            task_id,
            status=status,
            result_json=json.dumps(result, ensure_ascii=False),
            finished_at=sql_now(),
        )
    finally:
        conn.close()


def _cleanup_row_worktree(task_id: str) -> None:
    conn = _open()
    try:
        row = _load_by_id(conn, task_id)
    finally:
        conn.close()
    _cleanup_worktree_safely(row)


def _task_prompt(row: dict[str, Any]) -> str:
    from codeinsight.execution.prompt import ContextBundle, build_task_prompt

    bundle = ContextBundle(
        requirement=row["question"],
        plan_json=json.loads(row["plan_json"]),
    )
    return build_task_prompt(bundle, commit_message=f"ci-exec: {row['question'][:60]}")


def _task_worktree_of(row: dict[str, Any], task_id: str) -> worktree.TaskWorktree:
    fresh = get_execution(row["project_id"], task_id)
    return worktree.TaskWorktree(
        path=Path(fresh["worktree_path"]),
        branch=fresh["branch"],
        base_commit=fresh["commit_before"] or "HEAD",
        repo_root=_repo_root_of(row["project_id"]),
    )


def _repo_root_of(project_id: int) -> Path:
    conn = _open()
    try:
        proj = conn.execute(
            "SELECT root_path FROM project WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()
    if proj is None or not proj["root_path"]:
        raise TransitionError("项目缺少 root_path", status_code=409)
    return Path(proj["root_path"])
