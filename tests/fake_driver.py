"""跨测试文件共享的可控执行驱动器。"""

from __future__ import annotations


class FakeDriver:
    """可控执行驱动器：成功时在 worktree 里真改一个文件（走真 git 路径）。"""

    name = "fake"

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.requests: list = []

    async def execute(self, request, emit=None):
        from codeinsight.execution import worktree
        from codeinsight.execution.driver import ExecutionProgress, ExecutionResult

        self.requests.append(request)
        if emit is not None:
            emit(ExecutionProgress(kind="tool", tool="Edit", file="app.py"))
        if not self.ok:
            return ExecutionResult(ok=False, summary="", duration_s=0.0, error="boom")
        (request.worktree / "app.py").write_text("print('v2 done')" + chr(10), encoding="utf-8")
        task = worktree.TaskWorktree(
            path=request.worktree, branch="", base_commit=request.base_commit,
            repo_root=request.repo_root,
        )
        sha = worktree.ensure_committed(task, request.commit_message)
        return ExecutionResult(
            ok=True, summary="改完了", duration_s=0.01, commit_sha=sha,
            changed_files=("app.py",),
        )
