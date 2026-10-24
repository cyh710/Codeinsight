"""验证知识工具可直接注册现有 Agent，而不伪造项目代码证据。"""

import sqlite3

import pytest

from codeinsight.agent.tool import Tool, ToolContext, ToolRegistry
from codeinsight.cognitive.concepts.integration import LearningBridge
from codeinsight.cognitive.concepts.service import KnowledgeService
from codeinsight.cognitive.concepts.tools import build_learning_tools


@pytest.fixture
def registry(library):
    bridge = LearningBridge(KnowledgeService(library))
    tools = build_learning_tools(bridge)
    assert all(isinstance(t, Tool) and not t.mutating for t in tools)
    return ToolRegistry(tools)


def context(project_id=1):
    return ToolContext(project_id=project_id, repo_root="not-read", conversation_id="example")


async def test_search_and_read_share_versions_and_never_add_code_citations(registry):
    search = registry.get("search_knowledge")
    result = await search.run({"query": "SQL 是什么"}, context())
    assert not result.error
    assert result.data["knowledge_sources"]
    assert "citations" not in result.data
    target = result.data["items"][0]["target"]
    read = await registry.get("read_knowledge_topic").run(target, context())
    assert not read.error
    assert read.data["knowledge_sources"][0]["target"] == target
    assert target["version"] == read.data["version"]
    assert target["section_id"] == "overview"
    assert "citations" not in read.data
    assert (
        read.content == (await registry.get("read_knowledge_topic").run(target, context(2))).content
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": []},
        {"query": ""},
        {"query": "SQL", "limit": True},
        {"query": "SQL", "limit": 99},
    ],
)
async def test_invalid_search_arguments_degrade(registry, arguments):
    result = await registry.get("search_knowledge").run(arguments, context())
    assert result.error == "bad_request"


async def test_search_no_match_has_no_false_sources(registry):
    result = await registry.get("search_knowledge").run({"query": "zxqv999nonexistent"}, context())
    assert not result.error
    assert result.data["items"] == result.data["knowledge_sources"] == []
    assert "没有匹配" in result.content


async def test_unknown_and_old_reading_targets_cannot_inject(registry):
    reader = registry.get("read_knowledge_topic")
    assert (await reader.run({"topic_id": {}}, context())).error == "bad_request"
    assert (await reader.run({"topic_id": "removed"}, context())).error == "topic_not_found"
    result = await reader.run({"topic_id": "sql-database", "version": "old"}, context())
    assert result.error and result.data["reading_status"] == "stale"
    assert not result.content and not result.data["knowledge_sources"]


async def test_small_budget_does_not_claim_material_was_injected(library):
    bridge = LearningBridge(KnowledgeService(library))
    search, reader = build_learning_tools(bridge, max_bytes=1)
    searched = await search.run({"query": "SQL 是什么"}, context())
    assert searched.error == "knowledge_budget_exceeded"
    assert searched.truncated and not searched.data["knowledge_sources"]
    result = await reader.run({"topic_id": "sql-database"}, context())
    assert result.error and result.data["reading_status"] == "outside_budget"
    assert not result.content and not result.data["knowledge_sources"]


async def test_fts_failure_degrades_without_claiming_project_failure(registry, monkeypatch):
    search = registry.get("search_knowledge")

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("offline fixture")

    monkeypatch.setattr(search.bridge, "search", fail)
    result = await search.run({"query": "SQL"}, context())
    assert result.error == "knowledge_search_failed"
    assert not result.data
    assert "从目录阅读" in result.content
