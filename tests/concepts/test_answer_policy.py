"""知识资格与项目证据分开；不将静态判断冒充回答语义质量评测。"""

import pytest

from codeinsight.cognitive.concepts.answer_policy import can_answer_from_knowledge
from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.concepts.integration import LearningBridge
from codeinsight.cognitive.concepts.learning_models import KnowledgeError
from codeinsight.cognitive.concepts.service import KnowledgeService


@pytest.fixture
def bridge(library):
    return LearningBridge(KnowledgeService(library))


def test_textbook_explanation_does_not_require_project_file_line(bridge):
    prepared = bridge.prepare_turn("SQL 是什么")
    assert can_answer_from_knowledge("SQL 是什么", "SQL 是查询和管理数据的语言。", prepared)


@pytest.mark.parametrize(
    "question",
    [
        "这个项目哪里用了 SQL",
        "仓库中的 SQL 怎么实现",
        "代码里哪里用了 SQL",
        "Does this project use SQL?",
    ],
)
def test_project_question_requires_project_evidence(bridge, question):
    assert not can_answer_from_knowledge(question, "SQL 是语言。", bridge.prepare_turn("SQL"))


@pytest.mark.parametrize(
    "text",
    ["本项目使用 SQL。", "this project uses SQLite", "代码中使用事务。", "入口为 example.py:77。"],
)
def test_generated_project_claim_does_not_gain_evidence_from_textbook(bridge, text):
    assert not can_answer_from_knowledge("SQL 是什么", text, bridge.prepare_turn("SQL"))


def test_invalid_or_unseen_material_cannot_bypass_abstention(bridge):
    prepared = bridge.prepare_turn("SQL 是什么")
    assert not can_answer_from_knowledge(
        "SQL", "SQL 是语言。", prepared, dropped_citations=["a.py:7"]
    )
    assert not can_answer_from_knowledge("SQL", "未完成", prepared, incomplete=True)
    assert not can_answer_from_knowledge(
        "SQL", "SQL 是语言。", bridge.prepare_turn("SQL", max_bytes=0)
    )
    assert not can_answer_from_knowledge("SQL", "SQL 是语言。", None)
    assert not can_answer_from_knowledge("这里是什么意思", "SQL 是语言。", prepared)


def test_goal_budget_keeps_whole_sections_and_same_references(bridge):
    goal, prepared = bridge.prepare_goal("SQL 是什么", max_message_bytes=2000)
    assert len(goal["content"].encode("utf-8")) <= 2000
    assert prepared.context.references
    for hit in prepared.context.references:
        assert hit.snippet in goal["content"] and hit.target.href in goal["content"]
    assert goal["content"].startswith("SQL 是什么")


def test_question_itself_can_use_entire_budget_without_false_knowledge_sources(bridge):
    question = "SQL 是什么" * 100
    goal, prepared = bridge.prepare_goal(question, max_message_bytes=100)
    assert goal["content"] == question
    assert not prepared.context.content and not prepared.context.references
    assert prepared.context.truncated


def test_reading_goal_reloads_target_under_remaining_budget(bridge):
    target = bridge.library.target("python-functions", "example")
    goal, prepared = bridge.prepare_goal(
        "这里是什么意思",
        max_message_bytes=3000,
        reading_context={
            "topic_id": target.topic_id,
            "section_id": target.section_id,
            "version": target.version,
            "snippet": "客户端编造内容",
        },
    )
    assert prepared.reading_status == "ok"
    assert "calculate_total" in goal["content"]
    assert "客户端编造内容" not in goal["content"]


def test_builtin_assets_are_independent_of_process_working_directory(tmp_path, monkeypatch):
    (tmp_path / "knowledge" / "learning").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert knowledge_directory("learning") != tmp_path / "knowledge" / "learning"
    assert (knowledge_directory("learning") / "index.json").is_file()
    assert (knowledge_directory("concepts") / "jwt.yaml").is_file()
    with pytest.raises(KnowledgeError):
        knowledge_directory("../../outside")
