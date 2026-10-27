"""编排器与计划器测试：状态机全路径（FakeDriver 注入）+ 真实临时 git 仓。

不真起 claude——driver_from_settings 被 monkeypatch 成 FakeDriver；
增量索引与学习卡走真实引擎（迷你仓，秒级），验证的是编排闭环本身。
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from codeinsight.config import settings
from codeinsight.execution import orchestrator, worktree
from codeinsight.execution.planner import build_plan, classify, gate_is_dev_task
from codeinsight.storage.sqlite import db_path, ensure_schema, open_sqlite
from fake_driver import FakeDriver


class FakeProvider:
    """照 test_runtime.py 的假模型形状：返回预置的 complete 文本。"""

    model_id = "fake-model@1"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[str] = []

    async def complete(self, system, messages, **_kw) -> str:
        self.calls.append(str(messages[-1].get("content", "")))
        return self.replies.pop(0) if self.replies else "{}"


@pytest.fixture
def mini_repo_indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """迷你 git 仓 + 已建过一次全量索引的项目行（增量闭环的基准）。"""
    from codeinsight.cognitive.indexing import index_project

    data = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data)
    ensure_schema(db_path(data))

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('v1')\n", encoding="utf-8")
    for args in (
        ("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t"),
        ("add", "-A"), ("commit", "-qm", "init"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    index_project(db_path(data), root=repo, name="mini")  # 全量基准，供后续增量
    conn = open_sqlite(db_path(data), row_factory=True)
    try:
        pid = conn.execute("SELECT id FROM project WHERE name = 'mini'").fetchone()["id"]
    finally:
        conn.close()
    return {"repo": repo, "data": data, "project_id": int(pid)}


def _wait_until(cond, timeout: float = 20.0, interval: float = 0.1) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(interval)
    raise AssertionError("等待条件超时")


def _use_fake_driver(monkeypatch: pytest.MonkeyPatch, driver: FakeDriver) -> None:
    monkeypatch.setattr(orchestrator, "driver_from_settings", lambda: driver)


# ─── 计划器 ───────────────────────────────────────────────────


def test_gate_catches_dev_intent_and_lets_questions_pass() -> None:
    assert gate_is_dev_task("帮我给 API 加个限流")
    assert gate_is_dev_task("修复登录页面的空指针")
    assert not gate_is_dev_task("对话流程是怎么走的？")
    assert not gate_is_dev_task("jwt 是什么意思")


@pytest.mark.asyncio
async def test_classify_via_llm_and_degrades_safe() -> None:
    assert await classify("帮我修 X", FakeProvider(['{"dev_task": true}'])) is True
    assert await classify("帮我修 X", FakeProvider(['{"dev_task": false}'])) is False
    # 坏输出 / 抛错都降级为 False（宁可漏判不可误判）
    assert await classify("帮我修 X", FakeProvider(["not json"])) is False


@pytest.mark.asyncio
async def test_build_plan_normalizes_output() -> None:
    provider = FakeProvider([
        json.dumps({"intent": "加限流", "files": ["backend/api.py", 5, None],
                    "approach": "中间件", "risks": ["误伤"], "extra": "丢弃"})
    ])
    plan = await build_plan("帮我加限流", provider, "backend/api.py:42 stream_chat")
    assert plan["files"] == ["backend/api.py"]
    assert plan["intent"] == "加限流"
    assert "extra" not in plan


@pytest.mark.asyncio
async def test_build_plan_falls_back_to_minimal() -> None:
    class Boom(FakeProvider):
        async def complete(self, *a, **kw) -> str:
            raise RuntimeError("llm down")

    plan = await build_plan("帮我修 X", Boom([]), "")
    assert plan["intent"] == "帮我修 X"
    assert plan["files"] == []


# ─── 状态机 ───────────────────────────────────────────────────


def test_create_and_public_shape(mini_repo_indexed: dict) -> None:
    row = orchestrator.create_execution(
        mini_repo_indexed["project_id"], "帮我加限流",
        {"intent": "加限流", "files": ["app.py"], "approach": "", "risks": []},
        conversation_id="conv-1",
    )
    assert row["status"] == "planned"
    public = orchestrator.execution_public(row)
    assert public["task_id"] == row["id"]
    assert public["plan"]["files"] == ["app.py"]
    assert public["diff_summary"] is None and public["change_card"] is None


def test_approve_runs_to_review_with_user_repo_untouched(
    mini_repo_indexed: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = FakeDriver(ok=True)
    _use_fake_driver(monkeypatch, driver)
    pid = mini_repo_indexed["project_id"]

    row = orchestrator.create_execution(pid, "改 app", {"intent": "x", "files": [], "approach": "", "risks": []}, None)
    after = orchestrator.transition(pid, row["id"], "approve")
    assert after["status"] == "executing"

    _wait_until(lambda: orchestrator.get_execution(pid, row["id"])["status"] == "review")
    done = orchestrator.get_execution(pid, row["id"])
    public = orchestrator.execution_public(done)
    assert public["summary"] == "改完了"
    assert public["diff_summary"]["files_changed"] == 1
    assert public["progress"][0]["tool"] == "Edit"
    # 用户检出零影响（ADR 0035 核心不变量）
    assert (mini_repo_indexed["repo"] / "app.py").read_text(encoding="utf-8") == "print('v1')\n"
    assert worktree.repo_is_clean(mini_repo_indexed["repo"])


def test_reject_from_planned_cleans_nothing_to_clean(
    mini_repo_indexed: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_driver(monkeypatch, FakeDriver())
    pid = mini_repo_indexed["project_id"]
    row = orchestrator.create_execution(pid, "q", {"intent": "", "files": [], "approach": "", "risks": []}, None)
    after = orchestrator.transition(pid, row["id"], "reject")
    assert after["status"] == "rejected"
    assert not orchestrator._tasks  # 没有后台任务被提交


def test_invalid_transitions_raise(
    mini_repo_indexed: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_driver(monkeypatch, FakeDriver())
    pid = mini_repo_indexed["project_id"]
    row = orchestrator.create_execution(pid, "q", {"intent": "", "files": [], "approach": "", "risks": []}, None)
    with pytest.raises(orchestrator.TransitionError) as exc:
        orchestrator.transition(pid, row["id"], "merge")  # planned 不能直接 merge
    assert exc.value.status_code == 409
    with pytest.raises(orchestrator.TransitionError) as exc404:
        orchestrator.transition(pid, "exec-nope", "approve")
    assert exc404.value.status_code == 404


def test_failed_execution_marks_and_cleans(
    mini_repo_indexed: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_driver(monkeypatch, FakeDriver(ok=False))
    pid = mini_repo_indexed["project_id"]
    row = orchestrator.create_execution(pid, "q", {"intent": "", "files": [], "approach": "", "risks": []}, None)
    orchestrator.transition(pid, row["id"], "approve")
    _wait_until(lambda: orchestrator.get_execution(pid, row["id"])["status"] == "failed")
    done = orchestrator.get_execution(pid, row["id"])
    assert orchestrator.execution_public(done)["error"] == "boom"
    assert done["worktree_path"] is None or not Path(done["worktree_path"]).exists()


def test_merge_flow_produces_change_card(
    mini_repo_indexed: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_driver(monkeypatch, FakeDriver(ok=True))
    pid = mini_repo_indexed["project_id"]
    row = orchestrator.create_execution(pid, "改 app", {"intent": "", "files": [], "approach": "", "risks": []}, None)
    orchestrator.transition(pid, row["id"], "approve")
    _wait_until(lambda: orchestrator.get_execution(pid, row["id"])["status"] == "review")

    merged = orchestrator.transition(pid, row["id"], "merge")
    assert merged["status"] == "merged"
    # 合入即生效；学习卡由后台增量索引生成，等它落库
    assert (mini_repo_indexed["repo"] / "app.py").read_text(encoding="utf-8") == "print('v2 done')\n"
    _wait_until(
        lambda: (orchestrator.execution_public(orchestrator.get_execution(pid, row["id"]))
                 ["change_card"] is not None),
        timeout=60,
    )
    card = orchestrator.execution_public(orchestrator.get_execution(pid, row["id"]))["change_card"]
    assert any("app" in f["citation"]["path"] for f in card["facts"])
    # 收尾：学习卡完成后 worktree 应被清理
    _wait_until(
        lambda: not Path(orchestrator.get_execution(pid, row["id"])["worktree_path"]).exists(),
        timeout=30,
    )


def test_merge_requires_clean_user_repo(
    mini_repo_indexed: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_driver(monkeypatch, FakeDriver(ok=True))
    pid = mini_repo_indexed["project_id"]
    row = orchestrator.create_execution(pid, "q", {"intent": "", "files": [], "approach": "", "risks": []}, None)
    orchestrator.transition(pid, row["id"], "approve")
    _wait_until(lambda: orchestrator.get_execution(pid, row["id"])["status"] == "review")

    # 用户未提交改动：合入必须被拒
    (mini_repo_indexed["repo"] / "draft.txt").write_text("wip", encoding="utf-8")
    with pytest.raises(orchestrator.TransitionError) as exc:
        orchestrator.transition(pid, row["id"], "merge")
    assert exc.value.status_code == 409
    (mini_repo_indexed["repo"] / "draft.txt").unlink()
