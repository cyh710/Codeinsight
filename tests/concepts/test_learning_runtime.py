"""真实装配/路由/SQLite/Git + 假 Provider；不调用网络或付费模型。"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.context import ContextBudget
from codeinsight.agent.runtime import AgentRuntime
from codeinsight.agent.service import open_agent
from codeinsight.agent.session import ConversationStore
from codeinsight.agent.tool import ToolRegistry
from codeinsight.api import knowledge, query
from codeinsight.api.app import create_app
from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.concepts.integration import LearningBridge
from codeinsight.cognitive.concepts.service import KnowledgeService
from codeinsight.cognitive.indexing.concepts_sync import refresh_project_concepts
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.llm.provider import StreamChunk
from codeinsight.storage.sqlite import db_path, open_sqlite


class FakeProvider:
    model_id = "offline-learning-runtime"

    def __init__(self, text="SQL 是查询和管理数据的语言。"):
        self.text = text
        self.messages = []

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        self.messages.append(messages)
        yield StreamChunk(text=self.text[:5])
        yield StreamChunk(text=self.text[5:], finish_reason="stop")


@pytest.fixture
def bridge(library):
    return LearningBridge(KnowledgeService(library))


@pytest.fixture
def indexed_repo(tmp_path, data_dir):
    root = tmp_path / "example-project"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / "store.py").write_text(
        "import sqlite3\n\n"
        "def save(conn):\n"
        '    conn.execute("BEGIN")\n'
        '    conn.execute("INSERT INTO items VALUES (1)")\n'
        "    conn.commit()\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    indexed = index_project(
        db_path(data_dir),
        root=root,
        name="learning-fixture",
        ref="HEAD",
        concepts_dir=knowledge_directory("concepts"),
    )
    return root, indexed.project_id


async def test_pure_knowledge_without_project_citations_is_supported(bridge):
    events = []

    async def emit(event):
        events.append(event)

    answer = await AgentRuntime(
        provider=FakeProvider(), registry=ToolRegistry(), learning=bridge
    ).run(project_id=1, question="SQL 是什么", emit=emit)
    assert not answer.abstained and answer.knowledge_sources
    assert not answer.facts and not answer.citations and not answer.inferences
    final = next(e.data for e in events if e.type == "answer")
    assert final["text"] == answer.text
    assert final["knowledge_sources"] == answer.knowledge_sources
    assert events[0].type == "meta" and events[-1].type == "done"


async def test_textbook_does_not_ground_project_questions_or_fabricated_code(bridge):
    runtime = AgentRuntime(provider=FakeProvider(), registry=ToolRegistry(), learning=bridge)
    answer = await runtime.run(project_id=1, question="这个项目哪里用了 SQL")
    assert answer.abstained and not answer.facts
    runtime.provider.text = "入口在 [fabricated.py:99]。"
    answer = await runtime.run(project_id=1, question="SQL 是什么")
    assert answer.abstained and not answer.citations and "fabricated.py:99" not in answer.text


async def test_reading_target_is_reloaded_and_old_versions_are_explicit(bridge):
    target = bridge.library.target("python-functions", "example")
    provider = FakeProvider("函数通过参数接收输入。")
    runtime = AgentRuntime(provider=provider, registry=ToolRegistry(), learning=bridge)
    reading = {**asdict(target), "snippet": "客户端伪造材料"}
    answer = await runtime.run(project_id=1, question="这里是什么意思", reading_context=reading)
    assert answer.reading_status == "ok" and not answer.abstained
    assert "calculate_total" in provider.messages[0][0]["content"]
    assert "客户端伪造材料" not in provider.messages[0][0]["content"]
    answer = await runtime.run(
        project_id=1, question="这里是什么意思", reading_context={**reading, "version": "old"}
    )
    assert answer.reading_status == "stale" and answer.knowledge_error and answer.abstained
    assert not answer.knowledge_sources


async def test_remaining_budget_does_not_claim_unseen_sources(bridge):
    provider = FakeProvider()
    runtime = AgentRuntime(
        provider=provider,
        registry=ToolRegistry(),
        learning=bridge,
        budget=ContextBudget(max_message_bytes=50),
    )
    answer = await runtime.run(project_id=1, question="SQL 是什么")
    assert answer.abstained and not answer.knowledge_sources
    assert len(provider.messages[0][0]["content"].encode()) <= 50


async def test_conversation_and_code_reading_are_isolated_by_project(
    bridge, indexed_repo, data_dir
):
    _, pid = indexed_repo
    provider = FakeProvider("代码在 [store.py:4]。")
    session = open_agent(db_path(data_dir), pid, provider=provider, embedder=None)
    try:
        answer = await session.runtime.run(
            project_id=pid,
            question="这里是什么意思",
            conversation_id="same",
            reading_context={
                "kind": "code",
                "project_id": pid,
                "path": "store.py",
                "lineno": 3,
                "end_lineno": 6,
                "snippet": "编造的代码",
            },
        )
        assert answer.reading_status == "ok" and answer.citations
        assert "编造的代码" not in str(provider.messages)
        assert "BEGIN" in str(provider.messages)
        assert "read_file" in answer.tools_used
        blocked = await session.runtime.run(
            project_id=pid,
            question="这里是什么意思",
            reading_context={
                "kind": "code",
                "project_id": pid + 1,
                "path": "store.py",
                "lineno": 3,
            },
        )
        assert blocked.reading_status == "invalid" and not blocked.citations
    finally:
        session.close()
    provider = FakeProvider()
    runtime = AgentRuntime(
        provider=provider, registry=ToolRegistry(), learning=bridge, store=ConversationStore()
    )
    await runtime.run(project_id=1, question="SQL 是什么", conversation_id="same")
    await runtime.run(project_id=2, question="SQL 是什么", conversation_id="same")
    assert len(provider.messages[-1]) == 1


def test_real_http_browsing_query_sse_and_project_examples(indexed_repo, monkeypatch):
    _, pid = indexed_repo
    monkeypatch.setattr(query, "_PROVIDER_FACTORY", FakeProvider)
    with TestClient(create_app()) as client:
        directory = client.get("/knowledge/tree").json()
        assert sum(len(g["topics"]) for g in directory["groups"]) == 66
        topic = client.get("/knowledge/topics/sql-database").json()
        searched = client.get("/knowledge/search", params={"q": "SQL 是什么"}).json()
        assert searched["items"][0]["target"]["version"] == topic["version"]
        assert client.get("/knowledge/topics/removed").status_code == 404
        assert (
            client.get("/knowledge/search", params={"q": "zxqv999nonexistent"}).json()["items"]
            == []
        )
        instances = client.get(
            f"/projects/{pid}/knowledge/topics/sql-transactions/instances"
        ).json()["items"]
        assert instances and all(i["evidence"] and i["path"] == "store.py" for i in instances)
        assert (
            client.get(f"/projects/{pid}/code", params={"path": "../../outside"}).status_code == 404
        )
        code = client.get(f"/projects/{pid}/code", params={"path": "store.py"}).json()
        assert "BEGIN" in code["content"]
        body = {"project_id": pid, "question": "SQL 是什么"}
        response = client.post("/query", json=body)
        assert response.status_code == 200
        assert not response.json()["abstained"] and response.json()["knowledge_sources"]
        stream = client.post("/query/stream", json=body)
        frames = [s for s in stream.text.split("\n\n") if s.strip()]
        assert frames[0].startswith("event: meta") and frames[-1].startswith("event: done")
        final = next(s for s in frames if s.startswith("event: answer"))
        payload = json.loads(
            next(line[6:] for line in final.splitlines() if line.startswith("data: "))
        )
        assert payload["text"] == response.json()["text"]
        assert payload["knowledge_sources"] == response.json()["knowledge_sources"]


def test_api_uncertainty_and_provider_failure_do_not_remove_textbook(
    indexed_repo, data_dir, monkeypatch
):
    _, pid = indexed_repo
    with open_sqlite(db_path(data_dir)) as conn:
        conn.execute(
            "UPDATE concept_instance SET confidence = 0.4 WHERE project_id = ? AND concept_id = 'db-transaction'",
            (pid,),
        )
        conn.commit()

    class BrokenProvider:
        async def complete(self, *args, **kwargs):
            raise RuntimeError("offline failure")

    monkeypatch.setattr(knowledge, "_PROVIDER_FACTORY", BrokenProvider)
    with TestClient(create_app()) as client:
        project = client.post(
            f"/projects/{pid}/concepts/db-transaction/explain", json={"depth": "project"}
        ).json()
        assert project["inferences"] and not any("检测证据" in f["text"] for f in project["facts"])
        deep = client.post(
            f"/projects/{pid}/concepts/db-transaction/explain", json={"depth": "deep"}
        )
        assert deep.status_code == 200 and deep.json()["error"]
        assert deep.json()["summary"] and not deep.json()["llm_used"]
        assert client.get("/knowledge/topics/db-transaction").status_code == 200


def test_rule_version_changes_only_for_rules_not_text(
    indexed_repo, data_dir, tmp_path, monkeypatch
):
    _, pid = indexed_repo
    assets = tmp_path / "concepts"
    shutil.copytree(knowledge_directory("concepts"), assets)
    import codeinsight.cognitive.indexing.concepts_sync as module

    calls = []
    original = module.RuleBasedDetector.detect

    def detect(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(module.RuleBasedDetector, "detect", detect)
    with open_sqlite(db_path(data_dir)) as conn:
        original_version = conn.execute(
            "SELECT concept_version FROM repo_state WHERE project_id = ?", (pid,)
        ).fetchone()[0]
        article = assets / "jwt.yaml"
        article.write_text(
            article.read_text(encoding="utf8").replace("JWT", "JWT（补充文案）", 1), encoding="utf8"
        )
        same = refresh_project_concepts(conn, project_id=pid, knowledge_dir=assets)
        assert not calls and same.version == original_version
        article.write_text(
            article.read_text(encoding="utf8").replace("jwt.decode", "jwt.decode_new"),
            encoding="utf8",
        )
        changed = refresh_project_concepts(conn, project_id=pid, knowledge_dir=assets)
        assert calls and changed.version > original_version
