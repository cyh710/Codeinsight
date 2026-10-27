"""只读回放已保存的工具账本，验证失败收束；没有真实模型请求。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from pathlib import Path

from codeinsight.agent.runtime import AgentRuntime
from codeinsight.agent.tool import ToolRegistry, ToolResult
from codeinsight.llm.provider import StreamChunk, ToolCall


async def replay(db: Path, task_id: str) -> dict:
    """回放原始调用顺序与工具响应，不重建索引、不写用户会话或执行外部工具。"""
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        events = [
            (kind, json.loads(raw))
            for kind, raw in conn.execute(
                "SELECT type,payload_json FROM agent_event WHERE task_id=? ORDER BY id",
                (task_id,),
            )
        ]
    turns = deque(p for kind, p in events if kind == "assistant.tool_calls")
    results = [p for kind, p in events if kind == "tool.finished"]
    answers = defaultdict(deque)
    counts: Counter = Counter()
    for item in results:
        answers[(item["name"], json.dumps(item["arguments"], sort_keys=True))].append(item)

    class RecordedTool:
        parameters = {"type": "object", "properties": {}}
        description = "返回本次账本已有结果，不执行原工具"
        mutating = False

        def __init__(self, name):
            self.name = name

        async def run(self, arguments, ctx):
            counts[self.name] += 1
            key = (self.name, json.dumps(arguments, sort_keys=True))
            if not answers[key]:
                return ToolResult("回放账本没有这个调用。", error="not_found")
            item = answers[key].popleft()
            return ToolResult(
                item["content"],
                item.get("data") or {},
                item.get("truncated", False),
                item.get("error"),
            )

    class RecordedProvider:
        model_id = "offline-ledger-replay"
        calls = 0
        final_requested = False

        async def stream_with_tools(self, system, messages, tools, **kwargs):
            self.calls += 1
            if kwargs.get("tool_choice") == "none":
                self.final_requested = True
                yield StreamChunk(
                    text="离线回放已进入整理阶段：使用已取得材料，并具体说明旧版文件不可读的缺口。",
                    finish_reason="stop",
                )
                return
            if turns:
                item = turns.popleft()
                yield StreamChunk(
                    text=item.get("content", ""),
                    tool_calls=[ToolCall(**call) for call in item["tool_calls"]],
                )
            else:
                yield StreamChunk(text="回放已完成。", finish_reason="stop")

    provider = RecordedProvider()
    runtime = AgentRuntime(
        provider=provider,
        registry=ToolRegistry(
            [RecordedTool(name) for name in sorted({r["name"] for r in results})]
        ),
    )
    answer = await runtime.run(project_id=1, question="回放已保存的策略和成绩查阅，不执行真实工具")
    return {
        "task_id": task_id,
        "original_tools": len(results),
        "original_errors": dict(Counter(r.get("error") or "success" for r in results)),
        "replayed_model_rounds": provider.calls,
        "executed_recorded_tools": dict(counts),
        "final_requested": provider.final_requested,
        "incomplete": answer.incomplete,
        "error": answer.error,
        "remaining_original_rounds": len(turns),
        "real_model_calls": 0,
        "semantic_quality_evaluated": False,
        "answer": asdict(answer),
    }


def main() -> None:
    """输出只包含回放结果；账本以 SQLite 只读连接打开。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(replay(args.db, args.task))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "answer"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
