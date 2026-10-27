"""探索附加后的正文不能被短补充覆盖；历史恢复只改指定且版本匹配的回合。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeinsight.agent.answer_body import merge_answer_body
from codeinsight.agent.answer_recovery import apply_answer_restoration, prepare_answer_restoration
from codeinsight.agent.exploration import version
from codeinsight.agent.runtime import AgentRuntime, RuntimeConfig
from codeinsight.agent.tool import ToolRegistry, ToolResult
from codeinsight.llm.provider import StreamChunk, ToolCall

BODY = "## 已有策略\n\n采用按文档组织的策略。 [app.py:1]\n\n| 方式 | 用途 |\n|---|---|\n| A | 比较 |\n\n```py\nvalue = 1\n```"
SUPPLEMENT = "还可以继续核对结果。 [app.py:1]"


class Source:
    name = "read_file"
    description = "离线源码"
    parameters = {"type": "object", "properties": {}}
    mutating = False

    async def run(self, arguments, ctx):
        return ToolResult(
            "value = 1", data={"citations": [{"path": "app.py", "lineno": 1, "end_lineno": 3}]}
        )


class Metadata(Source):
    name = "propose_exploration"

    def __init__(self, failed=False):
        self.failed = failed

    async def run(self, arguments, ctx):
        return ToolResult(
            "建议已核对",
            data={"exploration": {"actions": []}},
            error="invalid" if self.failed else None,
        )


class Script:
    model_id = "offline-answer-body"

    def __init__(self, turns):
        self.turns = iter(turns)

    async def stream_with_tools(self, *args, **kwargs):
        text, names = next(self.turns)
        yield StreamChunk(text=text)
        if names:
            yield StreamChunk(
                tool_calls=[ToolCall(f"{i}-{name}", name, {}) for i, name in enumerate(names)]
            )


@pytest.mark.parametrize("final", [SUPPLEMENT, "", BODY, BODY + "\n\n" + SUPPLEMENT])
async def test_attachment_body_survives_final_tail_and_is_verified(final):
    runtime = AgentRuntime(
        provider=Script(
            [
                ("我先查一下", ["read_file"]),
                (BODY, ["propose_exploration"]),
                (final, []),
            ]
        ),
        registry=ToolRegistry([Source(), Metadata()]),
    )
    events = []

    async def emit(event):
        events.append(event)

    answer = await runtime.run(project_id=1, question="现有策略和成绩", emit=emit)
    assert "已有策略" in answer.text and "value = 1" in answer.text
    assert answer.raw_text.count("## 已有策略") == 1
    assert "我先查一下" not in answer.raw_text
    assert answer.citations and not answer.incomplete
    final_event = next(event for event in events if event.type == "answer")
    assert final_event.data["text"] == answer.text
    if SUPPLEMENT in final:
        assert SUPPLEMENT in answer.raw_text


async def test_failed_metadata_does_not_discard_body_or_validate_fake_citation():
    body = BODY + "\n\n猜测的位置 [ghost.py:99]。"
    runtime = AgentRuntime(
        provider=Script(
            [
                ("草稿中还不能确定", ["read_file"]),
                (body, ["propose_exploration"]),
                (SUPPLEMENT, []),
            ]
        ),
        registry=ToolRegistry([Source(), Metadata(failed=True)]),
    )
    answer = await runtime.run(project_id=1, question="解释")
    assert BODY in answer.raw_text and "ghost.py:99" in answer.raw_text
    assert "未核实位置：ghost.py:99" in answer.text
    assert all(citation.path != "ghost.py" for citation in answer.citations)
    assert "草稿中还不能确定" not in answer.raw_text
    assert not answer.exploration


async def test_explicit_limit_still_keeps_already_written_body():
    runtime = AgentRuntime(
        provider=Script(
            [
                ("查阅过程", ["read_file"]),
                (BODY, ["propose_exploration"]),
            ]
        ),
        registry=ToolRegistry([Source(), Metadata()]),
        config=RuntimeConfig(max_model_turns=2),
    )
    answer = await runtime.run(project_id=1, question="解释")
    assert answer.incomplete and "已有策略" in answer.text and BODY == answer.raw_text


def test_only_exact_containment_is_deduplicated():
    assert merge_answer_body([BODY], BODY + "\n\n" + SUPPLEMENT) == BODY + "\n\n" + SUPPLEMENT
    assert merge_answer_body([BODY, BODY], "") == BODY
    assert merge_answer_body(["策略 A"], "策略 B") == "策略 A\n\n策略 B"


@pytest.fixture
def recorded(conn):
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(1,'fixture','/fixture')")
    conn.execute(
        "INSERT INTO repo_state(project_id,head_commit,index_epoch,parser_version) VALUES(1,'v1',1,'fixture')"
    )
    conn.execute("INSERT INTO conversation(project_id,id,title) VALUES(1,'c','原对话')")
    conn.execute(
        "INSERT INTO agent_task(id,project_id,conversation_id,question,status) VALUES('t',1,'c','q','completed')"
    )
    original = {
        "text": SUPPLEMENT,
        "raw_text": SUPPLEMENT,
        "incomplete": False,
        "exploration": {"actions": [{"id": "keep"}]},
        "evidence_review": {"source_version": version(conn, 1), "checks": []},
    }
    encoded = json.dumps(original, ensure_ascii=False)
    conn.execute(
        "INSERT INTO conversation_turn(project_id,conversation_id,request_id,task_id,question,status,answer_json) VALUES(1,'c','r','t','q','completed',?)",
        (encoded,),
    )
    events = [
        (
            "tool.finished",
            {"data": {"citations": [{"path": "app.py", "lineno": 1, "end_lineno": 3}]}},
        ),
        (
            "assistant.tool_calls",
            {
                "content": BODY + "\n\n未核实 [ghost.py:99]。",
                "tool_calls": [{"name": "propose_exploration"}],
            },
        ),
        ("assistant.answer", {"text": SUPPLEMENT, "raw_text": SUPPLEMENT}),
    ]
    conn.executemany(
        "INSERT INTO agent_event(task_id,type,payload_json) VALUES('t',?,?)",
        [(kind, json.dumps(data, ensure_ascii=False)) for kind, data in events],
    )
    conn.commit()
    return conn, encoded


def test_restore_backs_up_one_row_verifies_sources_and_is_idempotent(recorded, tmp_path: Path):
    conn, original = recorded
    plan = prepare_answer_restoration(conn, 1, "c", "r")
    assert plan.summary()["changed"]
    assert plan.restored["exploration"]["actions"][0]["id"] == "keep"
    assert plan.restored["evidence_review"]["unverified_citations"] == ["ghost.py:99"]
    assert all(citation["path"] == "app.py" for citation in plan.restored["citations"])
    backup = apply_answer_restoration(conn, plan, tmp_path / "backups")
    assert json.loads(backup.read_text(encoding="utf-8"))["answer_json"] == original
    saved = json.loads(conn.execute("SELECT answer_json FROM conversation_turn").fetchone()[0])
    assert BODY in saved["raw_text"] and SUPPLEMENT in saved["raw_text"]
    assert conn.execute("SELECT COUNT(*) FROM agent_event").fetchone()[0] == 4
    again = prepare_answer_restoration(conn, 1, "c", "r")
    assert not again.summary()["changed"]
    assert apply_answer_restoration(conn, again, tmp_path / "backups") is None
    assert len(list((tmp_path / "backups").iterdir())) == 1


def test_restore_rejects_concurrent_row_changes_without_creating_backup(recorded, tmp_path):
    conn, _ = recorded
    plan = prepare_answer_restoration(conn, 1, "c", "r")
    conn.execute("UPDATE conversation_turn SET answer_json='{}'")
    conn.commit()
    with pytest.raises(ValueError, match="已被其他操作更新"):
        apply_answer_restoration(conn, plan, tmp_path / "backups")
    assert not (tmp_path / "backups").exists()


def test_restore_does_not_overwrite_a_changed_task_status(recorded, tmp_path):
    conn, _ = recorded
    plan = prepare_answer_restoration(conn, 1, "c", "r")
    conn.execute("UPDATE conversation_turn SET status='running'")
    conn.commit()
    with pytest.raises(ValueError, match="已被其他操作更新"):
        apply_answer_restoration(conn, plan, tmp_path / "backups")
    assert not (tmp_path / "backups").exists()


def test_restore_rejects_another_project_or_changed_version(recorded, tmp_path):
    conn, _ = recorded
    with pytest.raises(ValueError, match="不存在"):
        prepare_answer_restoration(conn, 2, "c", "r")
    plan = prepare_answer_restoration(conn, 1, "c", "r")
    conn.execute("UPDATE repo_state SET index_epoch=2")
    conn.commit()
    with pytest.raises(ValueError, match="版本已变化"):
        prepare_answer_restoration(conn, 1, "c", "r")
    with pytest.raises(ValueError, match="版本已变化"):
        apply_answer_restoration(conn, plan, tmp_path / "backups")
