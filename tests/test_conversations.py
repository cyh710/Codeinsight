"""会话恢复、去重与源码定位的离线集成验证。"""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.selection import SelectionError, utf16_slice
from codeinsight.api import query
from codeinsight.api.app import create_app
from codeinsight.llm.provider import StreamChunk
from codeinsight.storage.conversations import ConversationRepository, PersistentConversationStore
from codeinsight.storage.sqlite import db_path, ensure_schema, open_sqlite


@pytest.fixture
def repository(conn):
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(1,'sample','unavailable')")
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(2,'other','unavailable')")
    conn.commit()
    return ConversationRepository(conn)


def finish(repo, cid, rid, question="SQL 是什么", text="SQL 教材回答"):
    repo.reserve(1, cid, rid, question, None)
    repo.event(1, cid, rid, "answer", {"text": text, "knowledge_sources": [{"version": "v1"}]})
    repo.event(1, cid, rid, "done", {"abstained": False})


def test_deduplication_is_atomic_and_scoped(repository):
    repo = repository
    reading = {"kind": "knowledge", "topic_id": "sql-database", "version": "v1"}
    assert repo.reserve(1, "c", "r", "这里是什么", reading)[1]
    assert not repo.reserve(1, "c", "r", "这里是什么", reading)[1]
    with pytest.raises(ValueError):
        repo.reserve(1, "c", "r", "另一个问题", reading)
    with pytest.raises(sqlite3.IntegrityError):
        repo.reserve(1, "c", "other", "并发请求", None)
    assert repo.reserve(2, "c", "r", "其他项目", None)[1]


def test_history_window_is_not_display_retention(repository):
    repo = repository
    for number in range(8):
        finish(repo, "c", str(number), f"第 {number} 问", f"答 {number}")
    repo.reserve(1, "c", "broken", "中断问题", None)
    repo.event(1, "c", "broken", "delta", {"text": "已经收到的半句"})
    repo.recover()
    history = PersistentConversationStore(repo.conn).history("1:c")
    assert len(history) == 12
    assert history[0]["content"] == "第 2 问"
    assert all("中断" not in item["content"] for item in history)
    first = repo.turns(1, "c", 0, 3)
    assert first["next_cursor"] is not None and len(first["items"]) == 3
    assert len(repo.turns(1, "c", first["next_cursor"], 100)["items"]) == 6
    broken = repo.turn(1, "c", "broken")
    assert broken["answer"]["text"] == "已经收到的半句"
    assert broken["status"] == "interrupted"
    assert len(repo.turns(1, "c", 0, 100)["items"]) == 9


def test_search_and_project_isolation(repository):
    repo = repository
    finish(repo, "a", "r1", "普通问题", "用中文识别连接池与 get_user")
    result = repo.list(project_id=1, query="连接池", archived=False, cursor=0, limit=10)
    assert result["items"][0]["match_request_id"] == "r1"
    assert not repo.list(project_id=2, query="连接池", archived=False, cursor=0, limit=10)["items"]
    repo.patch(1, "a", {"archived": True, "title": "数据库学习", "pinned": True})
    assert not repo.list(project_id=1, query="", archived=False, cursor=0, limit=10)["items"]
    assert repo.list(project_id=1, query="get_user", archived=True, cursor=0, limit=10)["items"]
    with pytest.raises(LookupError):
        repo.get(2, "a")


def test_v2_upgrade_and_legacy_backfill_preserve_project(repository, data_dir):
    conn = repository.conn
    conn.execute(
        "INSERT INTO agent_task(id,project_id,conversation_id,question,status) VALUES('old',1,'legacy','旧问题','completed')"
    )
    conn.execute(
        "INSERT INTO agent_event(task_id,type,payload_json) VALUES('old','assistant.answer',?)",
        (json.dumps({"text": "旧答案"}),),
    )
    conn.execute("PRAGMA user_version=2")
    conn.commit()
    ensure_schema(db_path(data_dir))
    repository.backfill()
    repository.backfill()
    turn = repository.turn(1, "legacy", "old")
    assert turn["legacy"] and turn["answer"] == {"text": "旧答案"}
    assert conn.execute("SELECT COUNT(*) FROM project").fetchone()[0] == 2
    assert len(repository.turns(1, "legacy", 0, 50)["items"]) == 1


class Provider:
    model_id = "offline-conversation-test"

    def __init__(self):
        self.calls = []

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        self.calls.append(messages)
        yield StreamChunk(text="SQL 是数据库查询语言。", finish_reason="stop")


def test_real_api_restores_context_after_app_restart_and_replays_request(repository, data_dir):
    provider = Provider()
    query.set_provider_factory(lambda: provider)
    try:
        with TestClient(create_app()) as client:
            cid = client.post("/projects/1/conversations").json()["id"]
            request = {
                "project_id": 1,
                "conversation_id": cid,
                "request_id": "stable",
                "question": "SQL 是什么",
            }
            first = client.post("/query", json=request)
            assert first.status_code == 200 and first.json()["knowledge_sources"]
            duplicate = client.post("/query", json=request)
            assert duplicate.status_code == 200 and len(provider.calls) == 1
            assert duplicate.json()["text"] == first.json()["text"]
            saved = client.get(f"/projects/1/conversations/{cid}/turns").json()["items"][0]
            assert saved["answer"]["knowledge_sources"] == first.json()["knowledge_sources"]
            assert client.get(f"/projects/2/conversations/{cid}/turns").status_code == 404
        with TestClient(create_app()) as restarted:
            response = restarted.post(
                "/query", json={**request, "request_id": "next", "question": "刚才的 SQL 是什么"}
            )
            assert response.status_code == 200
            assert any(
                message["role"] == "assistant" and "SQL" in message["content"]
                for message in provider.calls[-1]
            )
            assert restarted.get("/conversations?q=SQL&project_id=1").json()["items"]
        with open_sqlite(db_path(data_dir)) as conn:
            assert conn.execute("SELECT count(*) FROM conversation_turn").fetchone()[0] == 2
    finally:
        query.set_provider_factory(None)


def test_utf16_selection_does_not_split_emoji():
    assert utf16_slice("前😀后", 1, 3) == "😀"
    with pytest.raises(SelectionError):
        utf16_slice("前😀后", 1, 2)
    with pytest.raises(SelectionError):
        utf16_slice("abc", 0, 9)
