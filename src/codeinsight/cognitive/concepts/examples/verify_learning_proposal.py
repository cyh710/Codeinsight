"""在内存中验证请求 0005，不写入 A/C 文件，不启动真实模型或网络服务。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import sys
import types
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from codeinsight.agent.context import ContextBudget
from codeinsight.agent.tool import ToolRegistry
from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.concepts.integration import LearningBridge
from codeinsight.cognitive.concepts.library import LearningLibrary
from codeinsight.cognitive.concepts.service import KnowledgeService
from codeinsight.llm.provider import StreamChunk


def _module(name: str, source: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, f"<请求0005:{name}>", "exec"), module.__dict__)
    return module


class FakeProvider:
    """只返回预写回答；保留模型实际收到的 messages 供预算与重读检查。"""

    model_id = "offline-proposal-fixture"

    def __init__(self, text: str) -> None:
        self.text = text
        self.messages: list[list[dict[str, Any]]] = []

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        self.messages.append(messages)
        yield StreamChunk(text=self.text[:8])
        yield StreamChunk(text=self.text[8:], finish_reason="stop")


def load_proposal(path: Path) -> tuple[dict, types.ModuleType]:
    """拒绝对漂移后的 A/C 文件验证旧补丁；校验对象是规范化的源码文本。"""
    proposal = json.loads(path.read_text(encoding="utf-8"))
    files = proposal["files"]
    for filename, item in files.items():
        current = Path(filename)
        source = current.read_text(encoding="utf-8") if current.exists() else ""
        if hashlib.sha256(source.encode()).hexdigest() != item["base_sha256"]:
            raise ValueError(f"请求 0005 的基础文件已变化，必须重新对齐：{filename}")
    _module("_learning_proposal_models", files["src/codeinsight/models.py"]["content"])
    source = files["src/codeinsight/agent/runtime.py"]["content"].replace(
        "from codeinsight.models import Answer", "from _learning_proposal_models import Answer"
    )
    return proposal, _module("_learning_proposal_runtime", source)


async def check_runtime(runtime_module: types.ModuleType, bridge: LearningBridge) -> dict:
    """验证真实运行时源码的拟议版本，现有工具循环回归同样在内存中执行。"""
    results = []

    async def run(question, text, *, reading=None, budget=None):
        events = []
        provider = FakeProvider(text)
        runtime = runtime_module.AgentRuntime(
            provider=provider, registry=ToolRegistry(), learning=bridge, budget=budget
        )

        async def emit(event):
            events.append(event)

        answer = await runtime.run(
            project_id=1, question=question, reading_context=reading, emit=emit
        )
        assert answer.error is None, answer.error
        assert events[0].type == "meta" and events[-1].type == "done"
        assert sum(e.type == "answer" for e in events) == 1
        final = next(e.data for e in events if e.type == "answer")
        assert final["text"] == answer.text
        assert final["knowledge_sources"] == answer.knowledge_sources
        assert not answer.facts and not answer.citations
        return answer, provider

    answer, provider = await run("SQL 是什么", "SQL 是查询和管理数据的语言。")
    assert not answer.abstained and answer.knowledge_sources
    assert not answer.inferences
    assert "[SQL](/learn/sql-database)" in answer.text
    assert "教学示例不是当前项目的代码证据" in provider.messages[0][0]["content"]
    results.append("纯知识问题无需代码位置")

    answer, _ = await run("这个项目哪里用了 SQL", "目前没有项目位置；SQL 是查询语言。")
    assert answer.abstained and not answer.facts
    results.append("项目问题仍须代码证据")

    answer, _ = await run("zxqv999nonexistent", "没有匹配资料。")
    assert answer.abstained and not answer.knowledge_sources
    results.append("无资料不虚构来源")

    answer, _ = await run("SQL 是什么", "入口为 [invented.py:99]。")
    assert answer.abstained and "invented.py:99" not in answer.text
    results.append("教材不为虚构代码位置背书")

    target = bridge.library.target("python-functions", "example")
    reading = {**asdict(target), "snippet": "客户端编造的正文"}
    answer, provider = await run("这里是什么意思", "函数通过参数接收输入。", reading=reading)
    assert not answer.abstained and answer.reading_status == "ok"
    assert "calculate_total" in provider.messages[0][0]["content"]
    assert "客户端编造" not in provider.messages[0][0]["content"]
    results.append("阅读续问从资产重读")

    answer, _ = await run(
        "这里是什么意思", "需要重新打开章节。", reading={**reading, "version": "old"}
    )
    assert answer.abstained and answer.reading_status == "stale"
    results.append("过期目标明确降级")

    answer, provider = await run(
        "SQL 是什么", "无法纳入教材。", budget=ContextBudget(max_message_bytes=50)
    )
    assert answer.abstained and not answer.knowledge_sources
    assert len(provider.messages[0][0]["content"].encode()) <= 50
    results.append("目标预算不会保留未注入来源")

    source = (
        Path("tests/test_runtime.py")
        .read_text(encoding="utf-8")
        .replace("from codeinsight.agent.runtime import", "from _learning_proposal_runtime import")
    )
    original_tests = _module("_learning_proposal_runtime_tests", source)
    count = 0
    for name, test in vars(original_tests).items():
        if name.startswith("test_") and inspect.iscoroutinefunction(test):
            await test()
            count += 1
    return {"new_scenarios": results, "existing_runtime_tests": count}


def check_http(proposal: dict, runtime_module: types.ModuleType, bridge: LearningBridge) -> dict:
    """新路由与真实拟议运行时一起跑；HTTP/SSE 均为进程内假 Provider。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from codeinsight.api.errors import install_error_handlers

    files = proposal["files"]
    reading_api = _module(
        "_learning_proposal_api", files["src/codeinsight/api/learning.py"]["content"]
    )
    query_api = _module(
        "_learning_proposal_query", files["src/codeinsight/api/query.py"]["content"]
    )
    closed = []

    def session(project_id):
        runtime = runtime_module.AgentRuntime(
            provider=FakeProvider("SQL 是查询和管理数据的语言。"),
            registry=ToolRegistry(),
            learning=bridge,
        )
        return SimpleNamespace(
            runtime=runtime, project_id=project_id, close=lambda: closed.append(project_id)
        )

    query_api._open_session = session
    app = FastAPI()
    app.include_router(reading_api.router)
    app.include_router(query_api.router)
    install_error_handlers(app)
    with TestClient(app) as client:
        directory = client.get("/knowledge/tree")
        assert directory.status_code == 200
        assert sum(len(g["topics"]) for g in directory.json()["groups"]) == 66
        topic = client.get("/knowledge/topics/sql-database")
        assert topic.status_code == 200
        assert client.get("/knowledge/topics/removed").status_code == 404
        search = client.get("/knowledge/search", params={"q": "SQL 是什么"})
        assert search.status_code == 200
        assert search.json()["items"][0]["target"]["version"] == topic.json()["version"]
        assert client.get("/knowledge/search", params={"limit": -1}).status_code == 400
        body = {"project_id": 1, "question": "SQL 是什么"}
        answer = client.post("/query", json=body)
        assert answer.status_code == 200
        assert not answer.json()["abstained"]
        assert answer.json()["knowledge_sources"] and not answer.json()["citations"]
        stream = client.post("/query/stream", json=body)
        assert stream.status_code == 200
        frames = [s for s in stream.text.split("\n\n") if s.strip()]
        assert frames[0].startswith("event: meta") and frames[-1].startswith("event: done")
        final = next(s for s in frames if s.startswith("event: answer"))
        payload = json.loads(next(s[6:] for s in final.splitlines() if s.startswith("data: ")))
        assert payload["text"] == answer.json()["text"]
        assert payload["knowledge_sources"] == answer.json()["knowledge_sources"]
    assert len(closed) == 2
    return {
        "directory_topics": 66,
        "knowledge_routes": "passed",
        "query": "passed",
        "sse": "passed",
    }


def main() -> None:
    """只验证补丁内容；不应用补丁、不修改任一工作树中的 A/C 实现。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--proposal", type=Path, default=Path("docs/requests/0005-learning-runtime.proposal.json")
    )
    parser.add_argument("--out", type=Path, default=Path(".ci/learning-proposal-validation.json"))
    args = parser.parse_args()
    proposal, runtime = load_proposal(args.proposal)
    bridge = LearningBridge(KnowledgeService(LearningLibrary(knowledge_directory("learning"))))
    results = asyncio.run(check_runtime(runtime, bridge))
    results["http"] = check_http(proposal, runtime, bridge)
    results["base_commit"] = proposal["base_commit"]
    results["real_provider_calls"] = 0
    results["limitations"] = (
        "拟议源码在内存中运行；当前产品仍未应用补丁。未验证浏览器导航或真实模型效果。"
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
