"""执行层。

- `base.py`        —— `CommandRunner` Protocol（ADR 0008 最初预留，保留作历史接口）
- `driver.py`      —— 驱动器 Protocol 与请求/结果类型（ADR 0032）
- `claude_code.py` —— 驱动器：claude CLI 无头模式（第一批）
- `zcode.py`       —— 驱动器：zcode CLI 无头模式（第二批，事件 schema 不同）
- `selection.py`   —— 按 CI_EXECUTOR 配置构造驱动器的中立入口
- `worktree.py`    —— git worktree 隔离助手
- `finalize.py`    —— 执行收尾（git 兜底提交与改动核对，驱动器共用）
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
