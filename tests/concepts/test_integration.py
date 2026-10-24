"""跨线适配验收；不把本测试当成 HTTP/前端已经接线的证明。"""

import json
from dataclasses import asdict, replace

import pytest

from codeinsight.cognitive.concepts.integration import LearningBridge
from codeinsight.cognitive.concepts.learning_models import KnowledgeHit
from codeinsight.cognitive.concepts.service import KnowledgeService


@pytest.fixture
def bridge(library):
    return LearningBridge(KnowledgeService(library))


def test_directory_detail_and_search_use_identical_asset_version(bridge):
    tree = bridge.tree().data
    topics = [t for group in tree["groups"] for t in group["topics"]]
    assert len(topics) == 66
    for item in topics:
        detail = bridge.topic(item["id"]).data
        assert detail["version"] == item["version"]
        assert detail["sources"]
        assert detail["href"] == item["href"]
        assert all("{#" not in s["title"] for s in detail["sections"])
        json.dumps(detail)
    hit = bridge.search("SQL 是什么").data["items"][0]
    detail = bridge.topic(hit["target"]["topic_id"]).data
    section = next(s for s in detail["sections"] if s["id"] == hit["target"]["section_id"])
    assert section["content"] == hit["snippet"]
    assert detail["version"] == hit["target"]["version"]


def test_follow_up_reloads_article_instead_of_client_description(bridge):
    target = bridge.library.target("python-functions", "example")
    raw = {**asdict(target), "kind": "knowledge", "snippet": "伪造的客户端正文"}
    turn = bridge.prepare_turn("这里是什么意思", reading_context=raw)
    result = turn.as_tool_result()
    assert turn.reading_status == "ok"
    assert "calculate_total" in result.content
    assert "伪造的客户端正文" not in result.content
    assert result.data["knowledge_sources"][0]["target"]["href"] == target.href
    assert not result.error
    json.dumps(asdict(result))


@pytest.mark.parametrize(
    ("update", "status"),
    [
        ({"version": "old"}, "stale"),
        ({"section_id": "removed"}, "not_found"),
        ({"topic_id": "removed"}, "not_found"),
        ({"section_id": []}, "invalid"),
        ({"topic_id": {}}, "invalid"),
        ({"version": None}, "invalid"),
        ({"kind": "code"}, "requires_code_reader"),
    ],
)
def test_invalid_reading_context_degrades_explicitly(bridge, update, status):
    raw = {**asdict(bridge.library.target("python-functions", "example")), **update}
    turn = bridge.prepare_turn("SQL 是什么", reading_context=raw)
    assert turn.reading_status == status
    assert turn.error
    assert "calculate_total" not in turn.context.content
    assert turn.context.references[0].target.topic_id == "sql-database"


def test_insufficient_reading_budget_does_not_appear_successful(bridge):
    target = asdict(bridge.library.target("python-functions", "example"))
    turn = bridge.prepare_turn("这里是什么意思", reading_context=target, max_bytes=1)
    assert turn.reading_status == "outside_budget"
    assert not turn.context.content
    assert turn.context.truncated and turn.error


def test_answer_projection_preserves_same_sources_and_repairs_bad_links(bridge):
    prepared = bridge.prepare_turn("SQL 是什么")
    result = bridge.finalize_answer("SQL 是语言。[虚构](/learn/no-such-topic)。", prepared)
    assert result["text"].startswith("[SQL](/learn/sql-database)")
    assert "[虚构]" not in result["text"]
    assert result["knowledge_sources"] == prepared.as_tool_result().data["knowledge_sources"]
    assert len(result["learning_entries"]) <= 3
    assert all(bridge.library.resolve_href(t["href"]) for t in result["learning_targets"])
    assert "citations" not in result
    json.dumps(result)


def test_link_target_does_not_create_unretrieved_source(bridge):
    prepared = bridge.prepare_turn("zxqv999nonexistent")
    result = bridge.finalize_answer("SQL", prepared)
    assert result["learning_targets"]
    assert result["knowledge_sources"] == []


def test_zero_budget_preserves_search_items_without_claiming_injected_sources(bridge):
    result = bridge.search("SQL 是什么", max_bytes=0)
    assert result.data["items"]
    assert result.data["knowledge_sources"] == []
    assert result.truncated and not result.content
    assert bridge.topic("missing").error == "topic_not_found"
    assert bridge.search("zxqv999nonexistent").data["items"] == []


def test_article_level_hit_has_safe_default_section(library):
    target = library.target("sql-database")
    context = library.context([KnowledgeHit(target, "客户端正文", 1, ())])
    assert context.references[0].target.section_id == "overview"
    assert "客户端正文" not in context.content
    assert not library.context(
        [replace(context.references[0], target=replace(target, version="old"))]
    ).content


def test_malformed_url_is_not_a_valid_learning_target(library):
    assert library.resolve_href("https://[invalid") is None


def test_same_name_links_follow_current_language_instead_of_python_default(bridge):
    prepared = bridge.prepare_turn("React state 是什么")
    answer = bridge.finalize_answer(
        "调用状态更新函数会请求新的渲染；事件处理函数读取状态快照。", prepared
    )
    assert "[函数](/learn/js-functions)" in answer["text"]
    assert "[事件](/learn/react-events)" in answer["text"]
    assert "/learn/python-functions" not in answer["text"]
    assert "/learn/web-http" not in answer["text"]
    assert bridge.library.resolve_term("函数") is None
    assert (
        bridge.library.resolve_term("函数", context_topic_id="python-functions").topic_id
        == "python-functions"
    )


def test_anaphoric_question_without_target_does_not_invent_relevance(bridge):
    prepared = bridge.prepare_turn("这里是什么意思")
    assert prepared.reading_status == "missing"
    assert prepared.error
    assert not prepared.context.content
    assert not prepared.entries


def test_anaphoric_reading_only_recommends_current_topic_and_its_navigation(bridge):
    target = bridge.library.target("python-functions", "example")
    prepared = bridge.prepare_turn("这里是什么意思", reading_context=asdict(target))
    assert [hit.target for hit in prepared.context.references] == [target]
    topic = bridge.library.get(target.topic_id)
    assert all(
        t.topic_id in {topic.id, *topic.prerequisites, *topic.related} for t in prepared.entries
    )
    stale = bridge.prepare_turn(
        "这里是什么意思", reading_context={**asdict(target), "version": "old"}
    )
    assert stale.reading_status == "stale"
    assert not stale.context.content and not stale.entries
