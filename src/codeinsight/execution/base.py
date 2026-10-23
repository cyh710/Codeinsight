"""受控命令执行接口。

**当前不实现**。源文档 §2.7-4「执行受控开发命令」与 §3.2「Docker 沙箱」是重资产，
单人项目里把这一段交给外部 agent（Claude Code / Codex 自带沙箱与审批）更划算。

保留这个 Protocol 是为了：将来若要把执行侧收回自己手里，接口已就位，
且可以照搬织忆 `agent-v1` 的三层防护（action digest 审批 / 子进程最小环境 / 白名单校验）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CommandOutcome:
    """一次命令执行的结果。"""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_ms: int = 0


@runtime_checkable
class CommandRunner(Protocol):
    """在受限环境里执行命令。"""

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float = 60.0,
        env: Mapping[str, str] | None = None,
    ) -> CommandOutcome:
        """执行一条命令。

        实现方**不得**使用 shell（`shell=True`），必须以 argv 列表调用，
        否则命令注入无从防范。
        """
        ...
