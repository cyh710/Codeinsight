"""Zcode 驱动器测试：事件解析（真机录制样本 + 构造样本）+ 选择与收尾。

zcode 的 stream-json 包络是 {type, payload, seq}（与 claude 不同）；
样本里的 session.* / model.streaming 帧来自真机录制，
tool.call.* 与 turn.completed 按 bundle 内的事件词汇构造。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeinsight.config import settings
from codeinsight.execution.claude_code import ClaudeCodeDriver
from codeinsight.execution.finalize import finalize
from codeinsight.execution.selection import build_driver
from codeinsight.execution.zcode import ZcodeDriver, parse_stream_line


def _line(payload: dict, type_: str) -> str:
    return json.dumps({"type": type_, "payload": payload, "seq": 1, "sessionId": "sess_x"})


# ─── 解析 ─────────────────────────────────────────────────────


def test_parse_tool_call_frames() -> None:
    progress, final = parse_stream_line(
        _line({"toolCallId": "t1", "toolName": "Edit", "args": {"file_path": "calc.py"}},
              "tool.call.started")
    )
    assert progress is not None and final is None
    assert progress.kind == "tool"
    assert progress.tool == "Edit"
    assert progress.file == "calc.py"


def test_parse_tool_failed_carries_detail() -> None:
    progress, _ = parse_stream_line(
        _line({"toolName": "Bash", "error": "权限不足"}, "tool.call.failed")
    )
    assert progress is not None
    assert progress.tool == "Bash"
    assert "权限不足" in progress.detail


def test_parse_turn_completed_is_terminal() -> None:
    progress, final = parse_stream_line(
        _line({"content": "改完了", "toolCallCount": 2}, "turn.completed")
    )
    assert progress is None and final is not None
    assert final["ok"] is True and final["summary"] == "改完了"


def test_parse_turn_failed_is_terminal_error() -> None:
    _, final = parse_stream_line(_line({"error": "上游 502"}, "turn.failed"))
    assert final is not None
    assert final["ok"] is False and "502" in final["error"]


def test_parse_ignores_noise_frames() -> None:
    """真机录制里的非终点帧（session.*/model.streaming）与坏行全部跳过。"""
    for raw in (
        json.dumps({"type": "session.titleUpdated", "payload": {"title": "x"}, "seq": 1}),
        json.dumps({"type": "model.streaming", "payload": {"kind": "text_delta", "delta": "好"}, "seq": 2}),
        json.dumps({"type": "session.updated", "payload": {"messageCount": 3}, "seq": 3}),
        "not json", "", "null",
    ):
        progress, final = parse_stream_line(raw)
        assert progress is None and final is None


def test_parse_model_streaming_never_floods_progress() -> None:
    """文本增量不该变成进度帧——执行卡只显示工具时间线。"""
    progress, _ = parse_stream_line(
        json.dumps({"type": "model.streaming", "payload": {"kind": "text_delta", "delta": "长文本"}})
    )
    assert progress is None


# ─── argv 组装 ────────────────────────────────────────────────


def test_argv_with_node_and_script() -> None:
    driver = ZcodeDriver(command="node", extra_args="D:/zc/ZCode/resources/glm/zcode.cjs")
    argv = driver._argv("修 bug")
    assert argv[:3] == ["node", "D:/zc/ZCode/resources/glm/zcode.cjs", "-p"]
    assert "stream-json" in argv and "edit" in argv


def test_argv_with_path_shim() -> None:
    driver = ZcodeDriver(command="zcode")
    assert driver._argv("x")[:2] == ["zcode", "-p"]


# ─── 选择逻辑 ─────────────────────────────────────────────────


def test_selection_by_executor_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "executor", "zcode")
    monkeypatch.setattr(settings, "executor_command", "node")
    monkeypatch.setattr(settings, "executor_extra_args", "D:/zc/ZCode/resources/glm/zcode.cjs")
    driver = build_driver()
    assert isinstance(driver, ZcodeDriver)

    monkeypatch.setattr(settings, "executor", "claude-code")
    monkeypatch.setattr(settings, "executor_command", "")
    assert isinstance(build_driver(), ClaudeCodeDriver)

    monkeypatch.setattr(settings, "executor", "unknown-thing")
    assert build_driver() is None

    monkeypatch.setattr(settings, "executor", "off")
    assert build_driver() is None


# ─── 收尾件（claude/zcode 共用） ──────────────────────────────


def test_finalize_collects_changed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from codeinsight.execution import worktree as wt
    from codeinsight.execution.driver import ExecutionRequest

    data = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("v1\n", encoding="utf-8")
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t"),
                 ("add", "-A"), ("commit", "-qm", "init")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    task = wt.create_task_worktree(repo, "tf")
    request = ExecutionRequest(
        worktree=task.path, repo_root=repo, prompt="", base_commit=task.base_commit,
    )
    (task.path / "a.py").write_text("v2\n", encoding="utf-8")
    result = finalize(request, ok=True, summary="done", error=None, duration_s=1.0)
    assert result.ok and result.commit_sha
    assert result.changed_files == ("a.py",)
    wt.remove_task_worktree(task)
