"""驱动器选择：按 `CI_EXECUTOR` 配置构造执行器（请求 0018 / ADR 0035）。

中立入口——orchestrator 与可用性判定都从这里拿驱动器，不感知具体实现。
未知名字返回 None（调用方降级为普通问答，不报错）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from codeinsight.config import settings
from codeinsight.execution.claude_code import ClaudeCodeDriver
from codeinsight.execution.driver import ExecutorDriver
from codeinsight.execution.zcode import ZcodeDriver


def build_driver() -> ExecutorDriver | None:
    """按配置构造驱动器；off / 未知名字返回 None。"""
    if settings.executor == "off":
        return None
    if settings.executor == "claude-code":
        return ClaudeCodeDriver(command=settings.executor_command or "claude")
    if settings.executor == "zcode":
        return ZcodeDriver(
            command=settings.executor_command or "node",
            extra_args=settings.executor_extra_args,
        )
    return None


def executor_available(repo_root: Path) -> bool:
    """契约 §16.1 的可用性判定：驱动器可构造、命令可寻、仓库是 git。"""
    from codeinsight.execution import worktree

    driver = build_driver()
    if driver is None:
        return False
    if not shutil.which(driver.command):
        return False
    return worktree.is_git_repo(repo_root)
