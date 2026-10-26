"""探索首版：迁移、通用导览、来源校验、附加降级、恢复与预算。"""

import subprocess

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.discovery import discover
from codeinsight.agent.exploration import normalize, version
from codeinsight.api import query
from codeinsight.api.app import create_app
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.llm.provider import StreamChunk, ToolCall
from codeinsight.storage.conversations import ConversationRepository, PersistentConversationStore
from codeinsight.storage.sqlite import db_path, ensure_schema, open_sqlite


def make_project(root, data_dir, git=True):
    root.mkdir()
    (root / "app.py").write_text(
        'import sqlite3\n\ndef write(conn):\n    conn.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER)")\n    conn.commit()\n\ndef main():\n    conn = sqlite3.connect(":memory:")\n    write(conn)\n\nif __name__ == "__main__":\n    main()\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# 收据演示\n\n这个离线项目演示如何把一条收据存入 SQLite，并通过命令行入口观察一次真实数据库写入。这里没有 Web 页面或身份认证功能。\n",
        encoding="utf-8",
    )
    if git:
        for args in [
            ["init"],
            ["add", "."],
            [
                "-c",
                "user.name=fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-m",
                "fixture",
            ],
        ]:
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    index_project(db_path(data_dir), root=root, name=root.name)
    return root


@pytest.fixture
def indexed(data_dir, tmp_path):
    root = make_project(tmp_path / "receipts", data_dir)
    with open_sqlite(db_path(data_dir), row_factory=True) as conn:
        yield conn, root


def proposal():
    return {
        "takeaways": ["写入函数执行数据库操作。"],
        "actions": [
            {
                "kind": "follow_up",
                "label": "比较不提交会怎样",
                "question": "如果不提交事务，会发生什么？",
                "target": {"path": "app.py", "lineno": 3},
            },
            {"kind": "code", "label": "查看写入实现", "target": {"path": "app.py", "lineno": 3}},
            {
                "kind": "knowledge",
                "label": "事务基础",
                "target": {"kind": "knowledge", "topic_id": "sql-transactions"},
            },
        ],
        "flow": {
            "title": "入口与写入的关系",
            "nodes": [
                {"id": "a", "label": "程序入口", "target": {"qualname": "app.main"}},
                {
                    "id": "b",
                    "label": "写入",
                    "role": "执行数据库操作",
                    "target": {"qualname": "app.write"},
                },
            ],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
        },
    }


def test_discovery_uses_indexed_document_and_real_objects(indexed):
    conn, root = indexed
    result = discover(conn, 1)
    assert "收据" in result["project_intro"]["text"]
    assert result["project_intro"]["source"]["path"] == "README.md"
    assert 1 <= len(result["exploration_entries"]) <= 4
    assert all(
        a["target"] is None or a["target"]["project_id"] == 1 for a in result["exploration_entries"]
    )
    (root / "README.md").write_text("工作区文字不能冒充已索引文档。", encoding="utf-8")
    assert discover(conn, 1)["project_intro"] == result["project_intro"]


def test_non_git_and_empty_project_have_honest_entries(data_dir, tmp_path):
    make_project(tmp_path / "plain", data_dir, git=False)
    with open_sqlite(db_path(data_dir), row_factory=True) as conn:
        result = discover(conn, 1)
        assert not result["head_commit"] and result["exploration_entries"]
        conn.execute("INSERT INTO project(name,root_path) VALUES('empty','unavailable')")
        empty = discover(conn, 2)
        assert empty["project_intro"] is None and not empty["exploration_entries"]


def test_proposal_removes_fabricated_edges_and_cross_project_targets(indexed):
    conn, _ = indexed
    result = normalize(conn, 1, proposal())
    assert len(result["flow"]["edges"]) == 1
    assert result["flow"]["edges"][0]["kind"] == "call"
    raw = {
        "actions": [
            {"kind": "code", "label": "外部", "target": {"project_id": 2, "path": "app.py"}},
            {"kind": "code", "label": "越界", "target": {"path": "../secret.py"}},
            {"kind": "follow_up", "label": "正常", "question": "继续解释"},
        ]
    }
    assert [a["label"] for a in normalize(conn, 1, raw)["actions"]] == ["正常"]
    conn.execute("UPDATE edge SET confidence=0.4 WHERE kind='call'")
    assert normalize(conn, 1, proposal())["flow"]["edges"][0]["uncertain"]


def test_old_code_target_is_not_silently_rebound(indexed):
    conn, _ = indexed
    for field in ("head_commit", "content_sha256"):
        raw = {
            "actions": [
                {
                    "kind": "code",
                    "label": "旧材料",
                    "target": {
                        "path": "app.py",
                        "lineno": 3,
                        field: "outdated",
                    },
                }
            ]
        }
        assert not normalize(conn, 1, raw)["actions"]


def test_failed_index_is_not_a_change_entry_and_plain_changes_can_be(indexed):
    conn, _ = indexed
    conn.execute(
        "INSERT INTO index_run(project_id,base_commit,head_commit,mode,ok) "
        "VALUES(1,'old','new','incremental',0)"
    )
    assert not any("变更" in a["label"] for a in discover(conn, 1)["exploration_entries"])
    conn.execute(
        "INSERT INTO index_run(project_id,base_commit,head_commit,mode,ok,files_changed) "
        "VALUES(1,'','','incremental',1,1)"
    )
    assert any("变更" in a["label"] for a in discover(conn, 1)["exploration_entries"])


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {
            "actions": [None, {"kind": []}],
            "flow": {"nodes": [None], "edges": [None, {"source": []}]},
        },
        {"takeaways": "wrong"},
    ],
)
def test_malformed_suggestions_degrade(indexed, raw):
    assert normalize(indexed[0], 1, raw)["actions"] == []


def test_migration_v3_keeps_history_and_index(indexed, data_dir):
    conn, _ = indexed
    repo = ConversationRepository(conn)
    cid = repo.create(1)["id"]
    repo.reserve(1, cid, "keep", "问题", None)
    repo.event(1, cid, "keep", "answer", {"text": "旧答案"})
    repo.event(1, cid, "keep", "done", {})
    conn.execute("ALTER TABLE conversation DROP COLUMN exploration_json")
    conn.execute("PRAGMA user_version=3")
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM symbol").fetchone()[0]
    ensure_schema(db_path(data_dir))
    assert conn.execute("SELECT COUNT(*) FROM symbol").fetchone()[0] == count
    assert repo.turn(1, cid, "keep")["answer"]["text"] == "旧答案"
    assert repo.get(1, cid)["exploration_state"] == {"stale": False}


class ExplorerProvider:
    model_id = "offline-exploration"

    def __init__(self):
        self.calls = []

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        self.calls.append(messages)
        recent = messages[
            next(i for i in range(len(messages) - 1, -1, -1) if messages[i]["role"] == "user") :
        ]
        if not any(m["role"] == "tool" for m in recent):
            yield StreamChunk(
                tool_calls=[
                    ToolCall(
                        "read", "read_file", {"path": "app.py", "start_line": 1, "end_line": 12}
                    ),
                    ToolCall("plan", "propose_exploration", proposal()),
                ]
            )
        else:
            yield StreamChunk(text="写入函数执行数据库操作。 [app.py:4]", finish_reason="stop")


def test_api_actions_memory_replay_and_restart(indexed, data_dir, monkeypatch):
    provider = ExplorerProvider()
    monkeypatch.setattr(query, "_PROVIDER_FACTORY", lambda: provider)
    with TestClient(create_app()) as client:
        overview = client.get("/projects/1/overview").json()
        assert overview["exploration_entries"] and not provider.calls
        cid = client.post("/projects/1/conversations").json()["id"]
        request = {
            "project_id": 1,
            "conversation_id": cid,
            "request_id": "first",
            "question": "请解释项目写入流程",
        }
        response = client.post("/query", json=request)
        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["exploration"]["flow"] and len(answer["exploration"]["actions"]) == 3
        saved = client.get(f"/projects/1/conversations/{cid}/turns/first").json()
        assert saved["answer"]["exploration"] == answer["exploration"]
        calls = len(provider.calls)
        assert (
            client.post("/query", json=request).status_code == 200 and len(provider.calls) == calls
        )
        action = answer["exploration"]["actions"][0]
        payload = {
            **request,
            "request_id": "follow",
            "question": "客户端说明不能替换来源问题",
            "action_origin": {
                "kind": "answer",
                "request_id": "first",
                "action_id": action["id"],
                "index_epoch": answer["exploration"]["index_epoch"],
            },
        }
        before_invalid = len(provider.calls)
        assert (
            client.post(
                "/query",
                json={
                    **payload,
                    "action_origin": {
                        **payload["action_origin"],
                        "action_id": "fabricated",
                    },
                },
            ).status_code
            == 400
        )
        other = client.post("/projects/1/conversations").json()["id"]
        assert client.post("/query", json={**payload, "conversation_id": other}).status_code == 400
        assert len(provider.calls) == before_invalid
        assert client.post("/query", json=payload).status_code == 200
        assert (
            client.get(f"/projects/1/conversations/{cid}/turns/follow").json()["question"]
            == action["question"]
        )
        assert client.get(f"/projects/2/conversations/{cid}/turns/first").status_code == 404
        memory = client.get(f"/projects/1/conversations/{cid}").json()["exploration_state"]
        assert memory["items"] and not memory["stale"]
    with TestClient(create_app()) as restarted:
        meta = restarted.get(f"/projects/1/conversations/{cid}").json()
        assert meta["exploration_state"] == memory
        conn = indexed[0]
        conn.execute("UPDATE repo_state SET index_epoch=index_epoch+1 WHERE project_id=1")
        conn.commit()
        assert restarted.get(f"/projects/1/conversations/{cid}").json()["exploration_state"][
            "stale"
        ]
        before = len(provider.calls)
        assert restarted.post("/query", json=payload).status_code == 200
        assert restarted.post("/query", json={**payload, "request_id": "stale"}).status_code == 409
        assert len(provider.calls) == before
        assert restarted.patch(
            f"/projects/1/conversations/{cid}", json={"clear_exploration": True}
        ).json()["exploration_state"] == {"stale": False}
        assert len(restarted.get(f"/projects/1/conversations/{cid}/turns").json()["items"]) == 2


def test_memory_is_bounded_and_omits_failed_turns(indexed):
    conn, _ = indexed
    repo = ConversationRepository(conn)
    cid = repo.create(1)["id"]
    for i in range(14):
        rid = str(i)
        repo.reserve(1, cid, rid, "问题" * 500, None)
        repo.event(
            1,
            cid,
            rid,
            "answer",
            {"text": "内容", "exploration": {**version(conn, 1), "takeaways": ["中文😀" * 80]}},
        )
        repo.event(1, cid, rid, "done", {})
    state = repo.get(1, cid)["exploration_state"]
    assert len(state["items"]) == 12
    context = PersistentConversationStore(conn).exploration_context(f"1:{cid}")
    assert len(context.encode()) <= 4096
    assert "不代表用户掌握" in context
