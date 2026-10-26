"""Claude Code 驱动器：以无头子进程执行任务（请求 0015 / ADR 0032）。

调用形态：`claude -p <prompt> --output-format stream-json --verbose
--permission-mode acceptEdits`，cwd 指向**隔离 worktree**。

两个刻意的结构决定：

1. **解析与子进程分离**：`parse_stream_line` 是纯函数，吃一行 JSON 吐一帧
   进度——测试喂录制的 stream-json 样本即可回归，不用真起 claude
   （claude CLI 的 stream-json 格式会演进，回归样本比集成测试可靠）。
2. **容错解析**：遇到不认识的行形状跳过而不是抛错——驱动器断了进度流
   不该毁掉执行本身；真正的成败以进程退出码 + result 帧为准。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import Callable

from codeinsight.execution.driver import (
    ExecutionProgress,
    ExecutionRequest,
    ExecutionResult,
)
from codeinsight.execution.finalize import finalize

# Windows：不给每次执行弹一个控制台窗口（先例 api/local.py）。
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def parse_stream_line(line: str) -> tuple[ExecutionProgress | None, dict | None]:
    """解析 stream-json 的一行。

    返回 (进度帧, 最终 result 对象)。普通行只有其一；不认识的形状
    返回 (None, None)——调用方跳过。
    """
    text = line.strip()
    if not text:
        return None, None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(obj, dict):
        return None, None

    kind = obj.get("type")
    if kind == "result":
        return None, obj

    if kind == "assistant":
        message = obj.get("message")
        if not isinstance(message, dict):
            return None, None
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool = str(block.get("name") or "tool")
                inputs = block.get("input") if isinstance(block.get("input"), dict) else {}
                file = inputs.get("file_path") or inputs.get("path") or inputs.get("notebook_path")
                detail = ""
                if not file and tool.lower() in ("bash", "run"):
                    detail = str(inputs.get("command") or "")[:80]
                progress = ExecutionProgress(
                    kind="tool",
                    tool=tool,
                    file=str(file) if file else None,
                    detail=detail,
                )
                return progress, None
    return None, None


def _result_to_outcome(result_obj: dict | None) -> tuple[bool, str, str | None]:
    """result 帧 → (ok, summary, error)。无 result 帧时按退出码由调用方定。"""
    if result_obj is None:
        return False, "", None
    subtype = result_obj.get("subtype")
    summary = str(result_obj.get("result") or "").strip()
    if subtype == "success":
        return True, summary, None
    return False, summary, f"claude 未能完成：{subtype or "unknown"}"


class ClaudeCodeDriver:
    """驱动 claude CLI 的执行器。命令路径可注入（测试/自定义安装位置）。"""

    name = "claude-code"

    def __init__(self, command: str = "claude") -> None:
        self.command = command

    async def execute(
        self,
        request: ExecutionRequest,
        emit: Callable[[ExecutionProgress], None] | None = None,
    ) -> ExecutionResult:
        argv = [
            self.command,
            "-p",
            request.prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "acceptEdits",
        ]
        flags = _CREATE_NO_WINDOW
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(request.worktree),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=flags,
            )
        except OSError as exc:
            return ExecutionResult(
                ok=False,
                summary="",
                duration_s=0.0,
                error=f"无法启动 {self.command}：{exc}",
            )

        deadline = started + max(request.timeout_s, 1)
        result_obj: dict | None = None
        timed_out = False

        async def drain_stderr() -> bytes:
            return await proc.stderr.read() if proc.stderr else b""

        stderr_task = asyncio.create_task(drain_stderr())

        def _emit(progress: ExecutionProgress) -> None:
            if emit is not None:
                emit(progress)

        try:
            assert proc.stdout is not None
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    proc.kill()
                    break
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                if not line:
                    break
                progress, final = parse_stream_line(line.decode("utf-8", errors="replace"))
                if progress is not None:
                    _emit(progress)
                if final is not None:
                    result_obj = final
            await proc.wait()
        except TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
        except BaseException:
            # 用户中止（CancelledError）等一切异常：先杀子进程不留孤儿，再向上抛。
            proc.kill()
            try:
                await proc.wait()
            except BaseException:
                pass
            raise
        finally:
            stderr_bytes = await stderr_task

        duration_s = time.monotonic() - started
        if timed_out:
            ok, summary, error = False, "", f"执行超时（>{request.timeout_s}s），已终止"
        else:
            ok, summary, error = _result_to_outcome(result_obj)
            if not result_obj and proc.returncode not in (0, None):
                stderr_tail = stderr_bytes.decode("utf-8", errors="replace")[-400:]
                error = error or f"claude 退出码 {proc.returncode}"
                summary = summary or stderr_tail

        # git 侧事实（兜底提交 + 改动核对）统一走共享收尾件。
        return finalize(request, ok=ok, summary=summary, error=error, duration_s=duration_s)
