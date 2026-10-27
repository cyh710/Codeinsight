"""保留解释、引用降级、续问取证和可信历史隔离的离线集成测试。"""

import json

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.answer import GroundedFile, Grounding, split_answer
from codeinsight.agent.runtime import AgentRuntime
from codeinsight.agent.tool import ToolRegistry, ToolResult
from codeinsight.api import query
from codeinsight.api.app import create_app
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.llm.provider import StreamChunk, ToolCall
from codeinsight.storage.conversations import ConversationRepository, PersistentConversationStore
from codeinsight.storage.sqlite import db_path, open_sqlite


class ReviewProvider:
    model_id = "offline-review"

    def __init__(self):
        self.calls = []

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        self.calls.append(messages)
        start = next(i for i in range(len(messages) - 1, -1, -1) if messages[i]["role"] == "user")
        question = messages[start]["content"].splitlines()[0]
        current = messages[start:]
        read = any(m["role"] == "tool" for m in current)
        if ("核对入口" in question or "策略与成绩" in question) and not read:
            yield StreamChunk(
                tool_calls=[
                    ToolCall(
                        "read",
                        "read_file",
                        {
                            "path": "app.py",
                            "start_line": 1,
                            "end_line": 6,
                        },
                    )
                ]
            )
            return
        if "策略与成绩" in question:
            text = "已读到保存函数，它接收一个值并返回该值。当前材料没有可比较的实验成绩，暂时不能排高低。"
        elif "核对入口" in question:
            text = "入口把值交给保存函数。 [app.py:2]"
        elif "听不懂" in question or "简单一点" in question:
            text = (
                "把它想成收件窗口：先收到值，再交给保存函数。 [app.py:2]"
                if read
                else "你希望我重新解释哪一段？也可以贴出刚才没明白的句子。"
            )
        elif "混合引用" in question:
            if not read:
                yield StreamChunk(tool_calls=[ToolCall("read", "read_file", {"path": "app.py"})])
                return
            text = "入口接收值 [app.py:2]。另一个入口可能在 [ghost.py:99]。"
        elif "未核实引用" in question:
            text = "我猜入口在 [ghost.py:99]，需要再核对。"
        elif "SQL" in question:
            text = "SQL 是查询和管理关系数据库的语言。"
        else:
            text = "可以先把它理解成收件窗口，具体项目实现还需要核对。"
        yield StreamChunk(text=text, finish_reason="stop")


@pytest.fixture
def reviewed(data_dir, tmp_path, monkeypatch):
    root = tmp_path / "receipt"
    root.mkdir()
    (root / "app.py").write_text("def save(value):\n    return value\n", encoding="utf-8")
    index_project(db_path(data_dir), root=root, name="receipt", embed=False)
    provider = ReviewProvider()
    monkeypatch.setattr(query, "_PROVIDER_FACTORY", lambda: provider)
    return provider


def test_unchecked_answer_keeps_body_raw_and_survives_restart(reviewed):
    with TestClient(create_app()) as client:
        cid = client.post("/projects/1/conversations").json()["id"]
        body = {
            "project_id": 1,
            "conversation_id": cid,
            "request_id": "unchecked",
            "question": "这个项目的收件窗口怎么实现",
        }
        answer = client.post("/query", json=body).json()
        assert "收件窗口" in answer["text"] == answer["raw_text"]
        assert answer["evidence_review"]["status"] == "unverified"
        assert not answer["facts"] and not answer["inferences"]
        assert not answer["abstained"]
    with TestClient(create_app()) as client:
        turn = client.get(f"/projects/1/conversations/{cid}/turns/unchecked").json()
        assert turn["answer"]["text"] == answer["text"]
        assert turn["answer"]["raw_text"] == answer["raw_text"]
        assert (
            client.get(f"/projects/1/conversations/{cid}").json()["exploration_state"].get("items")
        )
        assert (
            client.post("/query", json=body).json()["evidence_review"] == answer["evidence_review"]
        )
        assert len(reviewed.calls) == 1


def test_invalid_and_partial_references_keep_text_without_fact_promotion(reviewed, data_dir):
    with TestClient(create_app()) as client:
        cid = client.post("/projects/1/conversations").json()["id"]
        body = {"project_id": 1, "conversation_id": cid, "question": "未核实引用"}
        text = client.post("/query/stream", json={**body, "request_id": "bad-ref"}).text
        frames = [
            json.loads(f.split("data: ", 1)[1])
            for f in text.split("\n\n")
            if f.startswith("event: answer")
        ]
        answer = frames[0]
        assert answer["raw_text"] == "我猜入口在 [ghost.py:99]，需要再核对。"
        assert "ghost.py:99" not in answer["text"]
        assert "需要再核对" in answer["text"]
        assert not answer["citations"] and not answer["facts"]
        assert answer["evidence_review"]["unverified_citations"] == ["ghost.py:99"]
        mixed = client.post(
            "/query", json={**body, "request_id": "mixed", "question": "混合引用"}
        ).json()
        assert mixed["evidence_review"]["status"] == "partial"
        assert len(mixed["facts"]) == len(mixed["citations"]) == 1
        assert "ghost.py:99" not in mixed["text"]
        assert "另一个入口可能在" in mixed["text"]
        with open_sqlite(db_path(data_dir), row_factory=True) as conn:
            history = PersistentConversationStore(conn).history(f"1:{cid}")
            assert "未完全核实" not in history[-1]["content"]
            assert history[-1]["content"] == mixed["text"]
            assert "[ghost.py:99]" not in str(history)


def test_rephrase_rereads_real_sources_after_restart_and_isolates_conversation(reviewed, data_dir):
    with TestClient(create_app()) as client:
        cid = client.post("/projects/1/conversations").json()["id"]
        body = {"project_id": 1, "conversation_id": cid}
        first = client.post(
            "/query", json={**body, "request_id": "source", "question": "核对入口"}
        ).json()
        assert first["facts"] and first["evidence_review"]["status"] == "verified"
        with open_sqlite(db_path(data_dir), row_factory=True) as conn:
            repo = ConversationRepository(conn)
            repo.reserve(1, cid, "old-placeholder", "听不懂", None)
            repo.event(
                1,
                cid,
                "old-placeholder",
                "answer",
                {
                    "text": "在本项目的索引里没有找到与这个问题相关的代码位置。",
                    "abstained": True,
                },
            )
            repo.event(1, cid, "old-placeholder", "done", {"abstained": True})
    with TestClient(create_app()) as client:
        before = len(reviewed.calls)
        answer = client.post(
            "/query", json={**body, "request_id": "rephrase", "question": "听不懂"}
        ).json()
        assert len(reviewed.calls) == before + 1
        assert answer["response_kind"] == "rephrase" and not answer["abstained"]
        assert answer["tools_used"] == ["read_file"] and answer["citations"]
        assert answer["evidence_review"]["followup_from"] == "source"
        assert "收件窗口" in answer["text"]
        turn = client.get(f"/projects/1/conversations/{cid}/turns/rephrase").json()
        assert turn["reading_context"] is None  # 内部取证不改变客户端提问关联。
        other = client.post("/projects/1/conversations").json()["id"]
        missing = client.post(
            "/query", json={**body, "conversation_id": other, "question": "听不懂"}
        ).json()
        assert missing["response_kind"] == "clarification" and not missing["tools_used"]


def test_rephrase_does_not_rebind_old_index_or_unavailable_source(reviewed, data_dir):
    with TestClient(create_app()) as client:
        cid = client.post("/projects/1/conversations").json()["id"]
        body = {"project_id": 1, "conversation_id": cid}
        client.post("/query", json={**body, "question": "核对入口"})
        old_cid = client.post("/projects/1/conversations").json()["id"]
        client.post("/query", json={**body, "conversation_id": old_cid, "question": "核对入口"})
        with open_sqlite(db_path(data_dir)) as conn:
            conn.execute("UPDATE project SET root_path='unavailable' WHERE id=1")
            conn.commit()
        failed = client.post("/query", json={**body, "question": "听不懂"}).json()
        assert failed["text"] and not failed["citations"]
        assert failed["evidence_review"]["status"] == "unavailable"
        with open_sqlite(db_path(data_dir)) as conn:
            conn.execute("UPDATE repo_state SET index_epoch=index_epoch+1 WHERE project_id=1")
            conn.commit()
        stale = client.post(
            "/query", json={**body, "conversation_id": old_cid, "question": "再简单一点"}
        ).json()
        assert not stale["tools_used"] and not stale["citations"]
        assert any("版本已变化" in str(m.get("content")) for m in reviewed.calls[-1])


def test_knowledge_followup_reuses_versioned_chapter_without_project_citations(reviewed):
    with TestClient(create_app()) as client:
        cid = client.post("/projects/1/conversations").json()["id"]
        body = {"project_id": 1, "conversation_id": cid}
        first = client.post("/query", json={**body, "question": "SQL 是什么"}).json()
        assert first["evidence_review"]["status"] == "knowledge"
        answer = client.post("/query", json={**body, "question": "听不懂"}).json()
        assert answer["reading_status"] == "ok" and answer["knowledge_sources"]
        assert not answer["citations"] and not answer["tools_used"]
        fresh = client.post("/projects/1/conversations").json()["id"]
        explicit = client.post(
            "/query",
            json={
                **body,
                "conversation_id": fresh,
                "question": "听不懂",
                "reading_context": {"kind": "knowledge", **first["knowledge_sources"][0]["target"]},
            },
        ).json()
        assert explicit["response_kind"] == "rephrase" and explicit["reading_status"] == "ok"


def test_citation_after_chinese_period_belongs_to_the_statement():
    grounding = Grounding()
    grounding.add(GroundedFile("app.py", 1, 9))
    split = split_answer("入口接收值。 [app.py:2]\n\n它可能是一个边界。", grounding)
    assert split.facts[0]["text"] == "入口接收值。"
    assert not split.inferences
    assert "它可能是一个边界。" in split.text
    mixed = split_answer(
        "入口接收值 [app.py:2]，还会写入其他文件 [ghost.py:99]。", grounding, preserve_invalid=True
    )
    assert mixed.facts and not mixed.inferences
    assert mixed.dropped_citations == ["ghost.py:99"]
    assert mixed.citations[0].path == "app.py"


def test_sparse_references_preserve_read_material_history_and_discussion(reviewed, data_dir):
    with TestClient(create_app()) as client:
        cid = client.post("/projects/1/conversations").json()["id"]
        body = {"project_id": 1, "conversation_id": cid}
        answer = client.post(
            "/query", json={**body, "request_id": "sparse", "question": "策略与成绩"}
        ).json()
        assert not answer["abstained"] and not answer["inferences"] and not answer["citations"]
        assert "没有可比较的实验成绩" in answer["text"]
        assert answer["evidence"][0]["path"] == "app.py"
        assert answer["evidence"][0]["snippet"]
        assert "score" not in answer["evidence"][0]
        assert answer["exploration"]["takeaways"] and not answer["exploration"]["actions"]
        state = client.get(f"/projects/1/conversations/{cid}").json()["exploration_state"]
        assert state["items"][0]["request_id"] == "sparse"
        with open_sqlite(db_path(data_dir), row_factory=True) as conn:
            history = PersistentConversationStore(conn).history(f"1:{cid}")
            assert history[-1]["content"] == answer["text"]
        rephrase = client.post("/query", json={**body, "question": "听不懂"}).json()
        assert rephrase["tools_used"] == ["read_file"]
        assert rephrase["evidence_review"]["followup_from"] == "sparse"


@pytest.mark.asyncio
async def test_tool_failure_is_not_reported_as_empty_search():
    class FailingTool:
        name = "read_file"
        description = "offline failure"
        parameters = {"type": "object", "properties": {}}
        mutating = False

        async def run(self, arguments, ctx):
            return ToolResult("源码目录不可用。", error="source_unavailable")

    provider = ReviewProvider()
    runtime = AgentRuntime(provider=provider, registry=ToolRegistry([FailingTool()]))
    answer = await runtime.run(project_id=1, question="核对入口")
    assert answer.evidence_review["status"] == "unavailable"
    assert answer.text and answer.raw_text
