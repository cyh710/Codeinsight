"""执行驱动器接口（请求 0018 / ADR 0035）。

CodeInsight 自身不写文件、不跑任意命令（ADR 0008 内核不变）——
执行由**驱动器**完成：它以子进程方式调用外部 agent 的无头模式，
把变更落到隔离 worktree 的任务分支上，并回流进度事件。

对驱动器的全部假设只有一条契约：给它隔离检出目录与组装好的 prompt，
它把变更提交到该目录的 git 分支并回流进度。不假设 agent 的内部状态。
第一批实现 `claude_code.ClaudeCodeDriver`；Zcode 等后续按同一 Protocol 接入。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExecutionRequest:
    """一次执行的全部输入。驱动器只许在 `worktree` 里工作。"""

    worktree: Path
    repo_root: Path
    prompt: str
    base_commit: str
    timeout_s: int = 1800
    commit_message: str = "ci-exec: 执行任务"


@dataclass(frozen=True)
class ExecutionProgress:
    """执行进度的一帧。kind 词汇：start/tool/message/done/error。"""

    kind: str
    detail: str = ""
    tool: str = ""
    file: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    """执行结束的事实快照（git 侧事实由 worktree 助手核对后填入）。"""

    ok: bool
    summary: str
    duration_s: float
    commit_sha: str | None = None
    changed_files: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None


@runtime_checkable
class ExecutorDriver(Protocol):
    """外部执行 agent 的适配层。"""

    name: str

    async def execute(
        self,
        request: ExecutionRequest,
        emit: Callable[[ExecutionProgress], None] | None = None,
    ) -> ExecutionResult: ...
