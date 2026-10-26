"""对话内识别（runtime 早退分支）与执行端点的集成测试。

离线：Provider/Driver 全假，真实部分只有迷你仓的 git 与索引。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.runtime import AgentRuntime, RuntimeConfig
from codeinsight.agent.tool import ToolRegistry
from codeinsight.config import settings
from codeinsight.llm.provider import StreamChunk
from codeinsight.storage.sqlite import db_path, ensure_schema, open_sqlite


class FakeProvider:
    """按调用次序回放文本：先 classify 再 build_plan（或普通问答的流式轮）。"""

    model_id = "fake-model@1"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)

    async def complete(self, system, messages, **_kw) -> str:
        return self.replies.pop(0) if self.replies else "{}"

    async def stream_with_tools(self, system, messages, tools, **_kw):
        yield StreamChunk(text="普通回答。", finish_reason="stop")

    def complete_with_tools(self, *a, **kw):  # pragma: no cover 主循环不走到
        raise AssertionError("测试不期待非流式接口")


class FakeSearchTool:
    name = "search_code"
    description = "搜代码"
    parameters: dict = {}
    mutating = False

    async def run(self, arguments, ctx):
        from codeinsight.agent.tool import ToolResult

        return ToolResult(
            text="命中",
            data={"items": [{"path": "app.py", "lineno": 1, "qualname": "app.main"}],
                  "citations": []},
        )


@pytest.fixture
def mini(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    from codeinsight.cognitive.indexing import index_project

    data = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data)
    ensure_schema(db_path(data))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('v1')\n", encoding="utf-8")
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t"),
                 ("add", "-A"), ("commit", "-qm", "init")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    index_project(db_path(data), root=repo, name="mini")
    conn = open_sqlite(db_path(data), row_factory=True)
    try:
        pid = int(conn.execute("SELECT id FROM project WHERE name = 'mini'").fetchone()["id"])
    finally:
        conn.close()
    return {"repo": repo, "pid": pid}


async def _collect(events: list, runtime, **kw):
    async def emit(ev):
        events.append(ev)

    return await runtime.run(emit=emit, **kw)


def test_dev_task_short_circuits_to_execution_plan(mini: dict) -> None:
    import json

    provider = FakeProvider([
        '{"dev_task": true}',  # classify
        json.dumps({"intent": "加限流", "files": ["app.py"], "approach": "改 app",
                    "risks": []}),  # build_plan
    ])
    runtime = AgentRuntime(
        provider=provider,
        registry=ToolRegistry([FakeSearchTool()]),
        repo_root=str(mini["repo"]),
        config=RuntimeConfig(max_model_turns=2),
    )
    events: list = []
    import asyncio

    answer = asyncio.run(
        _collect(events, runtime, project_id=mini["pid"], question="帮我给 app 加限流")
    )

    kinds = [e.type for e in events]
    # 早退：meta → answer → done，没有 delta/工具循环
    assert kinds == ["meta", "answer", "done"], kinds
    assert events[0].data["execution_enabled"] is True
    payload = events[1].data
    assert payload["execution"]["status"] == "planned"
    assert payload["execution"]["plan"]["files"] == ["app.py"]
    assert answer.execution is not None
    assert "执行计划" in answer.text
    # 计划已在库里（可被 approve 端点接续）
    from codeinsight.execution import orchestrator

    row = orchestrator.get_execution(mini["pid"], answer.execution["task_id"])
    assert row["status"] == "planned"


def test_normal_question_untouched(mini: dict) -> None:
    provider = FakeProvider([])  # 词法闸门就拦下，不该有任何 complete 调用
    runtime = AgentRuntime(
        provider=provider,
        registry=ToolRegistry([FakeSearchTool()]),
        repo_root=str(mini["repo"]),
        config=RuntimeConfig(max_model_turns=1),
    )
    events: list = []
    import asyncio

    answer = asyncio.run(
        _collect(events, runtime, project_id=mini["pid"], question="对话流程是怎么走的？")
    )
    assert answer.execution is None
    payload = next(e.data for e in events if e.type == "answer")
    assert payload["execution"] is None
    assert provider.replies == []  # 没有为识别付过模型调用


def test_executor_off_disables_detection(mini: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "executor", "off")
    provider = FakeProvider([])
    runtime = AgentRuntime(
        provider=provider,
        registry=ToolRegistry([FakeSearchTool()]),
        repo_root=str(mini["repo"]),
        config=RuntimeConfig(max_model_turns=1),
    )
    events: list = []
    import asyncio

    asyncio.run(_collect(events, runtime, project_id=mini["pid"], question="帮我修 app"))
    assert events[0].data["execution_enabled"] is False
    assert all(e.type != "answer" or e.data["execution"] is None for e in events)


# ─── 端点 ─────────────────────────────────────────────────────


def test_execution_endpoints_contract(mini: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from codeinsight.api.app import create_app
    from codeinsight.execution import orchestrator
    from fake_driver import FakeDriver

    monkeypatch.setattr(orchestrator, "driver_from_settings", lambda: FakeDriver(ok=True))
    client = TestClient(create_app())
    pid = mini["pid"]

    row = orchestrator.create_execution(
        pid, "改 app", {"intent": "x", "files": [], "approach": "", "risks": []}, None
    )
    tid = row["id"]

    # GET 形状（契约 §16.2）
    body = client.get(f"/projects/{pid}/executions/{tid}").json()
    assert body["status"] == "planned" and body["task_id"] == tid
    assert set(body) >= {"task_id", "status", "plan", "progress", "diff_summary", "change_card"}

    # planned 直接 merge → 409 契约错误形状
    res = client.post(f"/projects/{pid}/executions/{tid}/merge")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "bad_request"

    # approve → 后台执行到 review（FakeDriver 秒级完成）
    assert client.post(f"/projects/{pid}/executions/{tid}/approve").json()["status"] == "executing"
    import time

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        body = client.get(f"/projects/{pid}/executions/{tid}").json()
        if body["status"] == "review":
            break
        time.sleep(0.1)
    assert body["status"] == "review"
    assert body["diff_summary"]["files_changed"] == 1

    # 未知任务 → 404
    res = client.get(f"/projects/{pid}/executions/exec-nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "bad_request"
