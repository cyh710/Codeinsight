"""回放重复失配与无进展；正常推进不限制总轮次，脚本化 Provider 零真实调用。"""

import pytest

from codeinsight.agent.runtime import AgentRuntime
from codeinsight.agent.tool import ToolRegistry, ToolResult
from codeinsight.llm.provider import StreamChunk, ToolCall


class StaleFile:
    name = "read_file"
    description = "离线读取失败"
    parameters = {"type": "object", "properties": {}}
    mutating = False

    def __init__(self):
        self.calls = 0

    async def run(self, arguments, ctx):
        self.calls += 1
        return ToolResult("该文件版本不一致，需要更新索引。", error="stale_source")


class RepeatProvider:
    model_id = "offline-replay"

    def __init__(self):
        self.calls = []

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        self.calls.append((messages, tools, kwargs))
        if kwargs.get("tool_choice") == "none":
            yield StreamChunk(
                text="这次无法读取旧版文件。已有检索片段可以作为定位线索；成绩缺少可读取的结果记录，暂时不能比较高低。",
                finish_reason="stop",
            )
        else:
            yield StreamChunk(
                tool_calls=[
                    ToolCall(
                        str(len(self.calls)),
                        "read_file",
                        {"path": "bootstrap_ci.py", "start_line": len(self.calls)},
                    )
                ]
            )


@pytest.mark.asyncio
async def test_stale_file_is_not_reopened_with_different_windows_and_answer_finishes():
    tool, provider = StaleFile(), RepeatProvider()
    events = []

    async def emit(event):
        events.append(event)

    answer = await AgentRuntime(provider=provider, registry=ToolRegistry([tool])).run(
        project_id=1, question="策略和成绩", emit=emit
    )
    assert tool.calls == 1 and len(provider.calls) == 4
    assert "暂时不能比较高低" in answer.text
    assert not answer.error and not answer.incomplete
    assert provider.calls[-1][1] == []
    assert provider.calls[-1][2]["tool_choice"] == "none"
    assert [e.type for e in events].count("done") == 1


@pytest.mark.asyncio
async def test_identical_successful_material_also_cannot_loop_forever():
    class SameMaterial(StaleFile):
        async def run(self, arguments, ctx):
            self.calls += 1
            return ToolResult(
                "同一片段", data={"citations": [{"path": "a.py", "lineno": 1, "end_lineno": 2}]}
            )

    tool, provider = SameMaterial(), RepeatProvider()
    answer = await AgentRuntime(provider=provider, registry=ToolRegistry([tool])).run(
        project_id=1, question="解释"
    )
    assert len(provider.calls) == 5 and tool.calls == 4
    assert answer.text and not answer.incomplete


@pytest.mark.asyncio
async def test_index_change_during_tool_does_not_inject_new_version_result(conn):
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(1,'fixture','missing')")
    conn.execute(
        "INSERT INTO repo_state(project_id,head_commit,index_epoch,parser_version) VALUES(1,'',1,'fixture')"
    )
    conn.commit()

    class ChangedIndex(StaleFile):
        async def run(self, arguments, ctx):
            conn.execute("UPDATE repo_state SET index_epoch=2 WHERE project_id=1")
            conn.commit()
            return ToolResult(
                "新版内容不能混入", data={"citations": [{"path": "new.py", "lineno": 1}]}
            )

    class IndexProvider(RepeatProvider):
        async def stream_with_tools(self, *args, **kwargs):
            async for chunk in super().stream_with_tools(*args, **kwargs):
                for call in chunk.tool_calls or []:
                    call.arguments["source_kind"] = "index"
                yield chunk

    provider = IndexProvider()
    answer = await AgentRuntime(
        provider=provider, registry=ToolRegistry([ChangedIndex()]), conn=conn
    ).run(project_id=1, question="解释")
    assert len(provider.calls) == 4 and not answer.citations
    assert "新版内容不能混入" not in str(provider.calls[-1][0])
    assert provider.calls[-1][2]["tool_choice"] == "none"
