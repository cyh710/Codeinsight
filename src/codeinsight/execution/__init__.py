"""执行层。

- `base.py`        —— `CommandRunner` Protocol（ADR 0008 最初预留，保留作历史接口）
- `driver.py`      —— 驱动器 Protocol 与请求/结果类型（ADR 0032）
- `claude_code.py` —— 第一批驱动器：claude CLI 无头模式
- `worktree.py`    —— git worktree 隔离助手
- `prompt.py`      —— 执行 prompt 组装
"""

from codeinsight.execution.base import CommandOutcome, CommandRunner
from codeinsight.execution.driver import (
    ExecutionProgress,
    ExecutionRequest,
    ExecutionResult,
    ExecutorDriver,
)

__all__ = [
    "CommandOutcome",
    "CommandRunner",
    "ExecutionProgress",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutorDriver",
]
