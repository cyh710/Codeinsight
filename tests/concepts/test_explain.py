"""模型不能升级事实；离线层级和降级行为有真实调用断言。"""

import json

import pytest

from codeinsight.cognitive.concepts.explain import explain
from codeinsight.cognitive.concepts.learning_models import Relation
from codeinsight.models import ConceptDepth, ConceptInstance


class FakeProvider:
    model_id = "offline-fixture"

    def __init__(self, response=None, error=None):
        self.calls = 0
        self.response = response
        self.error = error

    async def complete(self, *args, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return json.dumps(self.response, ensure_ascii=False)


@pytest.mark.parametrize("depth", [ConceptDepth.QUICK, ConceptDepth.PROJECT])
async def test_quick_project_never_call_provider(concepts, depth):
    provider = FakeProvider(error=AssertionError("不得调用"))
    result = await explain(concepts["jwt"], depth=depth, provider=provider)
    assert not result.llm_used and provider.calls == 0


async def test_facts_are_traceable_and_uncertain_edges_remain_inferences(concepts):
    instances = [
        ConceptInstance("jwt", "a.py", 4, "a.decode", evidence="call jwt.decode", confidence=1),
        ConceptInstance("jwt", "b.py", 8, evidence="同名 decode", confidence=0.4),
    ]
    relation = Relation("a.decode", "helper", "a.py", 5, 0.5)
    result = await explain(
        concepts["jwt"], depth=ConceptDepth.PROJECT, instances=instances, relations=[relation]
    )
    assert len(result.facts) == 1
    assert result.facts[0]["citation"]["path"] == "a.py"
    assert len(result.inferences) == 2
    assert all(item["confidence"] < 1 for item in result.inferences)


async def test_no_instances_preserves_general_explanation(concepts):
    project = await explain(concepts["jwt"], depth=ConceptDepth.PROJECT)
    assert "不等于项目一定没有" in project.summary and not project.facts
    deep = await explain(concepts["jwt"], depth=ConceptDepth.DEEP)
    assert "JWT" in deep.summary and deep.error and not deep.facts


async def test_provider_failure_preserves_existing_evidence(concepts):
    instance = ConceptInstance("jwt", "a.py", 3, evidence="call jwt.decode")
    provider = FakeProvider(error=TimeoutError("secret-key must not be leaked"))
    result = await explain(
        concepts["jwt"], depth=ConceptDepth.DEEP, instances=[instance], provider=provider
    )
    assert result.error and "secret-key" not in result.error
    assert result.facts and provider.calls == 1


async def test_model_cannot_add_project_facts(concepts):
    provider = FakeProvider(
        response={
            "summary": "原理",
            "facts": [{"text": "编造", "citation": {"path": "fake.py", "lineno": 999}}],
        }
    )
    result = await explain(concepts["jwt"], depth=ConceptDepth.DEEP, provider=provider)
    assert result.error and not result.facts and not result.llm_used


async def test_deep_adds_explicit_inferences_only(concepts):
    provider = FakeProvider(
        response={
            "summary": "签名验证用于检查声明的完整性。",
            "inferences": [{"text": "可能便于多个服务共享身份", "confidence": 0.6}],
        }
    )
    result = await explain(concepts["jwt"], depth=ConceptDepth.DEEP, provider=provider)
    assert result.llm_used and not result.error and not result.facts
    assert result.inferences[0]["confidence"] == 0.6


async def test_input_budget_is_checked_before_model_call(concepts):
    provider = FakeProvider()
    result = await explain(
        concepts["jwt"], depth=ConceptDepth.DEEP, provider=provider, knowledge_content="字" * 9000
    )
    assert "预算" in result.error and provider.calls == 0


async def test_unknown_locations_in_free_text_are_rejected(concepts):
    provider = FakeProvider(response={"summary": "见 fake.py:999", "inferences": []})
    result = await explain(concepts["jwt"], depth=ConceptDepth.DEEP, provider=provider)
    assert result.error and "fake.py" not in result.summary


async def test_provider_timeout_does_not_hang_the_learning_service(concepts):
    import asyncio

    class Slow:
        async def complete(self, *args, **kwargs):
            await asyncio.sleep(10)

    result = await explain(
        concepts["jwt"], depth=ConceptDepth.DEEP, provider=Slow(), timeout_s=0.001
    )
    assert result.error and "TimeoutError" in result.error
