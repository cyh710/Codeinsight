"""Zcode 驱动器：`zcode -p` 无头模式（请求 0015 第二驱动器 / ADR 0032）。

调用形态：`<command> <extra_args…> -p <prompt> --output-format stream-json --mode edit`，
cwd 指向隔离 worktree。Zcode 桌面版不带 PATH shim，常见起法是
`node <ZCode>/resources/glm/zcode.cjs`——配置为
`CI_EXECUTOR_COMMAND=node` + `CI_EXECUTOR_EXTRA_ARGS=<cjs 路径>`（逗号分隔）；
若本机有 `zcode` shim，command=zcode、extra_args 留空即可。

事件 schema 与 Claude Code **不同**（`{type, payload, seq}` 包络）：
- 工具进度：`tool.call.started / completed / failed`（payload.toolName）
- 回合终点：`turn.completed` / `turn.failed`
解析保持宽容（ADR 0012）：不认识的形状跳过——进度流断了不毁执行；
成败以 turn 终点帧 + 退出码 + git 收尾为准。
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

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def parse_stream_line(line: str) -> tuple[ExecutionProgress | None, dict | None]:
    """解析 zcode stream-json 的一行。

    返回 (进度帧, 终点对象)。终点对象形如 {"ok": bool, "summary": str,
    "error": str | None}；不认识的形状返回 (None, None)。
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
    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}

    if kind == "turn.completed":
        summary = str(payload.get("content") or payload.get("result") or "").strip()
        return None, {"ok": True, "summary": summary, "error": None}
    if kind == "turn.failed":
        detail = str(
            payload.get("error") or payload.get("reason") or "zcode 回合失败"
        )
        return None, {"ok": False, "summary": "", "error": detail}

    if kind in ("tool.call.started", "tool.call.completed", "tool.call.failed"):
        tool = str(payload.get("toolName") or payload.get("name") or "tool")
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        file = args.get("file_path") or args.get("path") or args.get("notebook_path")
        detail = ""
        if kind == "tool.call.failed":
            detail = str(payload.get("error") or "失败")
        elif tool.lower() in ("bash", "run") and isinstance(args.get("command"), str):
            detail = args["command"][:80]
        return (
            ExecutionProgress(kind="tool", tool=tool, file=str(file) if file else None, detail=detail),
            None,
        )
    return None, None


class ZcodeDriver:
    """驱动 zcode CLI 的执行器。

    `command` 是 argv[0]（本机常见为 node），`script` 是可选的脚本路径
    （插在 command 与旗标之间）。
    """

    name = "zcode"

    def __init__(self, command: str = "node", extra_args: str = "") -> None:
        self.command = command
        # 附加项（通常是 zcode.cjs 的路径）作为 argv 中段插在命令与旗标之间。
        self.extra_args = [a.strip() for a in extra_args.split(",") if a.strip()]

    def _argv(self, prompt: str) -> list[str]:
        return [
            self.command,
            *self.extra_args,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--mode",
            "edit",
        ]

    async def execute(
        self,
        request: ExecutionRequest,
        emit: Callable[[ExecutionProgress], None] | None = None,
    ) -> ExecutionResult:
        argv = self._argv(request.prompt)
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(request.worktree),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=_CREATE_NO_WINDOW,
            )
        except OSError as exc:
            return ExecutionResult(
                ok=False,
                summary="",
                duration_s=0.0,
                error=f"无法启动 zcode（{self.command}）：{exc}",
            )

        deadline = started + max(request.timeout_s, 1)
        terminal: dict | None = None
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
                    terminal = final
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
        elif terminal is not None:
            ok, summary, error = terminal["ok"], terminal["summary"], terminal["error"]
            if not terminal["ok"] and terminal.get("error") is None and proc.returncode not in (0, None):
                error = f"zcode 退出码 {proc.returncode}"
        else:
            # 没有 turn 终点帧：按进程结果判断（宽容——有些版本终点帧缺失）。
            ok = proc.returncode == 0
            summary = ""
            error = None if ok else f"zcode 退出码 {proc.returncode}"
            if not ok:
                stderr_tail = stderr_bytes.decode("utf-8", errors="replace")[-400:]
                summary = stderr_tail

        return finalize(request, ok=ok, summary=summary, error=error, duration_s=duration_s)
