"""执行层测试：驱动器解析（录制样本）+ worktree 隔离（真实临时仓）+ prompt。

驱动器不真起 claude——stream-json 的解析用录制的样本人工构造回归；
worktree 助手对真实临时 git 仓操作，验证用户检出零影响的关键不变量。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from codeinsight.execution import worktree
from codeinsight.execution.claude_code import (
    ClaudeCodeDriver,
    _result_to_outcome,
    parse_stream_line,
)
from codeinsight.execution.prompt import ContextBundle, build_task_prompt

# ─── stream-json 解析 ─────────────────────────────────────────


def test_parse_tool_use_line() -> None:
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": "t1", "name": "Edit",
                             "input": {"file_path": "backend/a.py"}}]
            },
        }
    )
    progress, final = parse_stream_line(line)
    assert progress is not None and final is None
    assert progress.kind == "tool"
    assert progress.tool == "Edit"
    assert progress.file == "backend/a.py"


def test_parse_bash_shows_command_snippet() -> None:
    line = json.dumps(
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q tests/"}}
        ]}}
    )
    progress, _ = parse_stream_line(line)
    assert progress is not None
    assert progress.tool == "Bash"
    assert "pytest" in progress.detail
    assert progress.file is None


def test_parse_result_line() -> None:
    line = json.dumps({"type": "result", "subtype": "success", "result": "改完了"})
    progress, final = parse_stream_line(line)
    assert progress is None
    assert final is not None and final["subtype"] == "success"
    ok, summary, error = _result_to_outcome(final)
    assert (ok, summary, error) == (True, "改完了", None)


def test_parse_error_max_turns() -> None:
    _, final = parse_stream_line(json.dumps({"type": "result", "subtype": "error_max_turns"}))
    ok, _, error = _result_to_outcome(final)
    assert ok is False and "error_max_turns" in (error or "")


def test_parse_garbage_lines_are_skipped() -> None:
    """坏行/未知形状跳过不抛错——进度流断了不能毁掉执行（ADR 0012）。"""
    for junk in ("", "not json", '{"type":"weird"}', "[1,2]", "null"):
        progress, final = parse_stream_line(junk)
        assert progress is None and final is None


# ─── worktree 隔离（真实临时 git 仓） ─────────────────────────


@pytest.fixture
def user_repo(tmp_path: Path) -> Path:
    """模拟用户的真实仓库：一提交 + 干净检出。"""
    repo = tmp_path / "userrepo"
    repo.mkdir()
    (repo / "app.py").write_text("print('v1')\n", encoding="utf-8")
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@t"),
        ("config", "user.name", "t"),
        ("add", "-A"),
        ("commit", "-qm", "init"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


def _monkey_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """worktree 目录指到临时数据目录，不污染真实 .ci/。"""
    from codeinsight import config

    monkeypatch.setattr(config.settings, "data_dir", tmp_path / "data")


def test_worktree_isolates_user_checkout(
    user_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """核心不变量：worktree 里的提交不改变用户检出（分支、文件内容、干净度）。"""
    _monkey_settings(monkeypatch, tmp_path)
    base = worktree.head_sha(user_repo)
    current_branch = worktree._git(user_repo, "rev-parse", "--abbrev-ref", "HEAD")

    task = worktree.create_task_worktree(user_repo, "t1")
    (task.path / "app.py").write_text("print('v2')\n", encoding="utf-8")
    worktree.ensure_committed(task, "ci-exec: 改 app")

    # 用户侧零影响
    assert (user_repo / "app.py").read_text(encoding="utf-8") == "print('v1')\n"
    assert worktree.repo_is_clean(user_repo)
    assert worktree._git(user_repo, "rev-parse", "--abbrev-ref", "HEAD") == current_branch
    # 任务分支上有提交
    assert worktree._git(user_repo, "rev-parse", task.branch) != base


def test_diff_summary_counts(user_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _monkey_settings(monkeypatch, tmp_path)
    task = worktree.create_task_worktree(user_repo, "t2")
    (task.path / "app.py").write_text("print('v2 extra')\n", encoding="utf-8")
    (task.path / "new.py").write_text("x = 1\n", encoding="utf-8")
    head = worktree.ensure_committed(task, "two files")
    summary = worktree.diff_summary(task, head)
    assert summary["files_changed"] == 2
    assert summary["insertions"] >= 1
    statuses = {f["path"]: f["status"] for f in summary["files"]}
    assert statuses["new.py"] == "added"
    assert statuses["app.py"] == "modified"


def test_remove_worktree_restores_repo(
    user_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """拒绝/放弃路径：目录删干净、任务分支消失、worktree 列表不留残迹。"""
    _monkey_settings(monkeypatch, tmp_path)
    task = worktree.create_task_worktree(user_repo, "t3")
    worktree.remove_task_worktree(task)
    assert not task.path.exists()
    listing = worktree._git(user_repo, "worktree", "list")
    assert str(task.path) not in listing


def test_merge_requires_clean_repo_and_uses_no_ff(
    user_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _monkey_settings(monkeypatch, tmp_path)
    task = worktree.create_task_worktree(user_repo, "t4")
    (task.path / "app.py").write_text("print('v3')\n", encoding="utf-8")
    worktree.ensure_committed(task, "change")
    merged = worktree.merge_into_current(task, "merge: t4")
    assert (user_repo / "app.py").read_text(encoding="utf-8") == "print('v3')\n"
    assert merged != worktree.head_sha(task.path)


# ─── prompt 组装 ──────────────────────────────────────────────


def test_build_task_prompt_contains_plan_and_boundaries() -> None:
    bundle = ContextBundle(
        requirement="给 API 加限流",
        plan_json={"intent": "加限流", "files": ["backend/api.py"], "approach": "中间件",
                   "risks": ["误伤内部调用"]},
        symbols_block="backend/api.py:42 stream_chat",
        conventions="注释用中文",
    )
    prompt = build_task_prompt(bundle, commit_message="ci-exec: 限流")
    assert "给 API 加限流" in prompt
    assert "backend/api.py" in prompt
    assert "已经用户批准" in prompt
    assert "不要 push" in prompt
    assert "git add -A" in prompt
    # 边界指令放末尾（长上下文首尾权重高）
    assert prompt.rstrip().endswith("改了什么、为什么这样改、还有什么没做。")


def test_driver_from_settings_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from codeinsight.config import settings
    from codeinsight.execution.selection import build_driver as driver_from_settings

    monkeypatch.setattr(settings, "executor", "off")
    assert driver_from_settings() is None
    monkeypatch.setattr(settings, "executor", "claude-code")
    driver = driver_from_settings()
    assert isinstance(driver, ClaudeCodeDriver)
