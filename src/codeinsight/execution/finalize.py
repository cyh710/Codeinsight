"""执行收尾：无论驱动器成败，git 侧事实统一在这里核对。

驱动器（claude / zcode / 未来其它）只负责"跑完外部 agent"；改动是否落盘、
提交是否存在，以 worktree 里的 git 状态为准——驱动器的口头总结不是事实来源。
无头 agent 通常不主动 commit（prompt 里要求了，但不可信），这里兜底提交。
"""

from __future__ import annotations

from codeinsight.execution import worktree
from codeinsight.execution.driver import ExecutionRequest, ExecutionResult


def finalize(
    request: ExecutionRequest,
    *,
    ok: bool,
    summary: str,
    error: str | None,
    duration_s: float,
) -> ExecutionResult:
    """兜底提交 + 核对改动文件，组装最终 ExecutionResult。"""
    commit_sha: str | None = None
    changed: tuple[str, ...] = ()
    try:
        task = worktree.TaskWorktree(
            path=request.worktree,
            branch="",  # 分支名在核对阶段不需要
            base_commit=request.base_commit,
            repo_root=request.repo_root,
        )
        commit_sha = worktree.ensure_committed(task, request.commit_message)
        name_only = worktree._git(
            request.worktree, "diff", "--name-only", f"{request.base_commit}..{commit_sha}"
        )
        changed = tuple(sorted(p for p in name_only.splitlines() if p.strip()))
    except worktree.WorktreeError as exc:
        # git 收尾失败不掩盖执行结论，作为附注写进 error。
        note = f"git 收尾失败：{exc}"
        if error or not ok:
            error = f"{error}; {note}" if error else note
        else:
            error = note
    return ExecutionResult(
        ok=ok,
        summary=summary,
        duration_s=duration_s,
        commit_sha=commit_sha,
        changed_files=changed,
        error=error,
    )
