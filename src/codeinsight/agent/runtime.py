"""Agent 运行时（源文档 §3.1 第一层「任务规划与工具调用」，A12）。

循环很短，但它要同时守住四件事：

1. **有界**：≤10 次模型轮次、每轮 ≤16 次工具调用、两层字节预算
   （`context.py`）。超了就明确说「没做完」，不硬编答案。
2. **可追溯**：每条证据都进 grounded 集合；模型引用对不上的 `file:line`
   会被删掉（`answer.py`）。**编造的位置永远到不了用户眼前**。
3. **可复现**：每一步先落 `agent_event`，再由同一份记录折回 messages。
4. **诚实**：没有证据就弃答。`abstained` 是产品能力，不是失败。

事件流（SSE 契约 §8.3）通过 `emit` 回调交出：
`meta → (tool|evidence|delta)* → answer → done`，`answer` 与 `done` 各恰好一次。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from codeinsight.agent.answer import GroundedFile, Grounding, split_answer
from codeinsight.agent.context import ContextBudget, assemble, truncate_bytes
from codeinsight.agent.ledger import EventLedger, new_task_id
from codeinsight.agent.prompts import SYSTEM_PROMPT
from codeinsight.agent.session import ConversationStore, Focus
from codeinsight.agent.tool import ToolContext, ToolRegistry
from codeinsight.llm.provider import ToolCall
from codeinsight.models import Answer

Emit = Callable[["RuntimeEvent"], Awaitable[None]]

ABSTAIN_TEXT = "在本项目的索引里没有找到与这个问题相关的代码位置。"


@dataclass(frozen=True)
class RuntimeEvent:
    """一条流式事件。`type` 与 SSE 契约 §8.3 的事件名一致。"""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeConfig:
    max_model_turns: int = 10
    max_tool_calls_per_turn: int = 16
    max_tokens: int = 2000
    temperature: float = 0.0


class AgentRuntime:
    """一次问答 = 一个 task；会话历史来自 `ConversationStore`。"""

    def __init__(
        self,
        *,
        provider: Any,
        registry: ToolRegistry,
        store: ConversationStore | None = None,
        conn: sqlite3.Connection | None = None,
        repo_root: str = "",
        budget: ContextBudget | None = None,
        config: RuntimeConfig | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.store = store or ConversationStore()
        self.conn = conn
        self.repo_root = repo_root
        self.budget = budget or ContextBudget()
        self.config = config or RuntimeConfig()

    async def run(
        self,
        *,
        project_id: int,
        question: str,
        conversation_id: str = "",
        emit: Emit | None = None,
    ) -> Answer:
        task_id = new_task_id()
        answer = Answer(task_id=task_id, model_id=str(getattr(self.provider, "model_id", "")))
        ledger = (
            EventLedger(self.conn, project_id=project_id, conversation_id=conversation_id)
            if self.conn is not None
            else None
        )
        if ledger is not None:
            ledger.start(task_id, question)
        await _emit(
            emit,
            RuntimeEvent(
                "meta",
                {
                    "task_id": task_id,
                    "conversation_id": conversation_id,
                    "model": answer.model_id,
                    "tools": self.registry.names,
                },
            ),
        )

        prior = self.store.history(conversation_id)
        goal = {"role": "user", "content": question}
        current: list[dict[str, Any]] = []
        grounding = Grounding()
        focus = self.store.focus(conversation_id)
        final_text = ""

        try:
            for _turn in range(self.config.max_model_turns):
                messages, _dropped = assemble(prior, current, goal, self.budget)
                text, calls = await self._one_turn(messages, emit)

                if not calls:
                    final_text = text
                    break

                current.append(_assistant_message(text, calls))
                if ledger is not None:
                    ledger.record(
                        task_id,
                        "assistant.tool_calls",
                        {
                            "content": text,
                            "tool_calls": [
                                {"id": call.id, "name": call.name, "arguments": call.arguments}
                                for call in calls
                            ],
                        },
                    )

                for index, call in enumerate(calls):
                    if index >= self.config.max_tool_calls_per_turn:
                        result_text = "本轮工具调用次数已达上限，未执行。"
                        current.append(_tool_message(call.id, result_text))
                        continue
                    if call.name not in self.registry.names:
                        await _emit(
                            emit,
                            RuntimeEvent(
                                "tool",
                                {"name": call.name, "status": "error", "summary": "未知工具"},
                            ),
                        )
                        current.append(
                            _tool_message(call.id, f"错误：没有名为 {call.name} 的工具。")
                        )
                        continue
                    await _emit(
                        emit,
                        RuntimeEvent(
                            "tool",
                            {
                                "name": call.name,
                                "status": "running",
                                "summary": _summarize(call),
                            },
                        ),
                    )
                    tool = self.registry.get(call.name)
                    assert tool is not None
                    result = await tool.run(
                        call.arguments,
                        ToolContext(
                            project_id=project_id,
                            repo_root=self.repo_root,
                            conversation_id=conversation_id,
                        ),
                    )
                    if call.name not in answer.tools_used:
                        answer.tools_used.append(call.name)
                    focus = _update_focus(focus, call.name, result.data)
                    _absorb_grounding(grounding, result.data)
                    _collect_evidence(answer, call.name, result.data)
                    await _emit_evidence(emit, call.name, result.data)
                    await _emit(
                        emit,
                        RuntimeEvent(
                            "tool",
                            {
                                "name": call.name,
                                "status": "error" if result.error else "ok",
                                "summary": _result_summary(result.error, result.data),
                            },
                        ),
                    )
                    payload = {
                        "name": call.name,
                        "arguments": call.arguments,
                        "content": result.content,
                        "data": result.data,
                        "truncated": result.truncated,
                        "error": result.error,
                    }
                    if ledger is not None:
                        ledger.record(task_id, "tool.finished", payload)
                    content = result.content
                    if result.error:
                        content = f"（{result.error}）{content}"
                    current.append(_tool_message(call.id, content))
            else:
                answer.incomplete = True
                final_text = ""

            if not final_text:
                answer.incomplete = True
                final_text = (
                    "这个问题在允许的轮次内没有分析完。可以把问题缩小到具体模块或符号再问。"
                )

            split = split_answer(final_text, grounding)
            answer.text = split.text
            answer.facts = split.facts
            answer.inferences = split.inferences
            answer.citations = split.citations

            if len(grounding) == 0:
                # 一条证据都没有：模型说的任何话都不是项目事实。
                answer.abstained = True
                answer.abstention_reason = "检索与工具调用都没有返回可引用的代码位置"
                answer.inferences = []
                answer.facts = []
                answer.citations = []
                if not answer.text.strip() or answer.text.strip() == ABSTAIN_TEXT:
                    answer.text = ABSTAIN_TEXT
                else:
                    answer.text = (
                        "（本项目的索引里没有找到相关代码位置；"
                        "下面的内容不是项目事实，也没有工具证据支持。）\n\n" + answer.text
                    )

            await _emit(
                emit,
                RuntimeEvent(
                    "answer",
                    {
                        "facts": answer.facts,
                        "inferences": answer.inferences,
                        "citations": _citations_payload(answer),
                        "abstained": answer.abstained,
                        "reason": answer.abstention_reason,
                        "incomplete": answer.incomplete,
                    },
                ),
            )
        except Exception as exc:  # noqa: BLE001 —— 流中途出错也必须走完 done
            answer.error = _error_payload(exc)
            await _emit(emit, RuntimeEvent("error", answer.error))
        finally:
            status = "failed" if answer.error else ("abstained" if answer.abstained else "completed")
            if ledger is not None:
                if not answer.error:
                    ledger.record(
                        task_id,
                        "assistant.answer",
                        {
                            "text": answer.text,
                            "facts": answer.facts,
                            "inferences": answer.inferences,
                            "abstained": answer.abstained,
                        },
                    )
                ledger.finish(task_id, status=status, reason=answer.abstention_reason)
            await _emit(
                emit,
                RuntimeEvent(
                    "done",
                    {"abstained": answer.abstained, "reason": answer.abstention_reason},
                ),
            )

        if answer.error is None:
            self.store.record_turn(conversation_id, question, answer.text, focus=focus)
        return answer

    async def _one_turn(
        self, messages: list[dict[str, Any]], emit: Emit | None
    ) -> tuple[str, list[ToolCall]]:
        """跑一次模型调用，把正文增量实时交出去，返回 (正文, 工具调用)。"""
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        async for chunk in self.provider.stream_with_tools(
            SYSTEM_PROMPT,
            messages,
            self.registry.schemas(),
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        ):
            if chunk.text:
                text_parts.append(chunk.text)
                await _emit(emit, RuntimeEvent("delta", {"text": chunk.text}))
            if chunk.tool_calls:
                calls = chunk.tool_calls
        return "".join(text_parts), calls


# ── 消息构造 ──────────────────────────────────────────────────


def _assistant_message(text: str, calls: list[ToolCall]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": text,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in calls
        ],
    }


def _tool_message(call_id: str, content: str) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


# ── 证据与焦点 ────────────────────────────────────────────────


def _absorb_grounding(grounding: Grounding, data: dict[str, Any]) -> None:
    for item in data.get("citations") or []:
        try:
            path = str(item["path"])
            lineno = int(item["lineno"])
        except (KeyError, TypeError, ValueError):
            continue
        grounding.add(
            GroundedFile(
                path,
                lineno,
                int(item.get("end_lineno") or lineno),
                item.get("qualname"),
                str(item.get("snippet") or ""),
            )
        )


def _update_focus(focus: Focus, tool_name: str, data: dict[str, Any]) -> Focus:
    """从工具结果里推断「这轮在聊什么」，供下一轮追问使用。"""
    items = data.get("items") or []
    if tool_name == "find_symbol" and items:
        return focus.merge(symbol=items[0].get("qualname"))
    if tool_name == "search_code" and items:
        return focus.merge(
            symbol=items[0].get("qualname") or focus.symbol,
            paths=tuple(item.get("path") for item in items[:3] if item.get("path")),
        )
    if tool_name in {"list_concepts", "explain_concept", "find_concept_instances"}:
        concept_id = data.get("concept_id") or (
            items[0].get("concept_id") if items else None
        )
        if concept_id:
            return focus.merge(concept_ids=(*focus.concept_ids, str(concept_id)))
    if tool_name == "get_module_overview" and data.get("path"):
        return focus.merge(module=data.get("module"), paths=(data["path"],))
    return focus


def _collect_evidence(answer: Answer, tool_name: str, data: dict[str, Any]) -> None:
    """把检索命中的完整字段留在 Answer 上，供非流式端点组装 `evidence`。

    流式的 `evidence` 事件按契约 §8.3 只要 6 个字段；`chunk_id` / `score`
    是 §8.1 才有的，所以放在这里而不是事件里——事件词汇表是冻结的。
    """
    if tool_name != "search_code":
        return
    seen = {item.get("chunk_id") for item in answer.evidence}
    for item in data.get("items") or []:
        if item.get("chunk_id") in seen:
            continue
        answer.evidence.append(
            {
                "chunk_id": item.get("chunk_id"),
                "path": item.get("path"),
                "lineno": item.get("lineno"),
                "end_lineno": item.get("end_lineno"),
                "qualname": item.get("qualname"),
                "snippet": str(item.get("snippet") or "")[:400],
                "score": item.get("score", 0.0),
                "lanes": item.get("lanes") or [],
                "concept_ids": item.get("concepts") or [],
            }
        )


async def _emit_evidence(emit: Emit | None, tool_name: str, data: dict[str, Any]) -> None:
    """检索证据边流边推，前端右栏不必等 `answer`。"""
    if tool_name != "search_code":
        return
    for item in data.get("items") or []:
        await _emit(
            emit,
            RuntimeEvent(
                "evidence",
                {
                    "path": item.get("path"),
                    "lineno": item.get("lineno"),
                    "end_lineno": item.get("end_lineno"),
                    "qualname": item.get("qualname"),
                    "snippet": str(item.get("snippet") or "")[:400],
                    "lanes": item.get("lanes") or [],
                    "concepts": item.get("concepts") or [],
                },
            ),
        )


# ── 小工具 ────────────────────────────────────────────────────


async def _emit(emit: Emit | None, event: RuntimeEvent) -> None:
    if emit is not None:
        await emit(event)


def _summarize(call: ToolCall) -> str:
    args = call.arguments
    label = {
        "search_code": "搜索",
        "find_symbol": "查找符号",
        "read_file": "读取",
        "get_callers": "查调用者",
        "get_callees": "查被调用者",
        "list_concepts": "列出概念",
        "explain_concept": "解释概念",
        "find_concept_instances": "查概念实例",
        "get_flow": "查流程",
        "get_changes": "查变更",
        "get_design_decisions": "查设计说明",
        "get_module_overview": "看模块",
    }.get(call.name, call.name)
    target = (
        args.get("query")
        or args.get("name")
        or args.get("symbol")
        or args.get("concept_id")
        or args.get("path")
        or args.get("flow_name")
        or ""
    )
    text = f"{label} {target}".strip()
    return text[:40]


def _result_summary(error: str | None, data: dict[str, Any]) -> str:
    if error:
        return str(error)[:40]
    items = data.get("items")
    if isinstance(items, list):
        return f"返回 {len(items)} 条"
    return "完成"


def _citations_payload(answer: Answer) -> list[dict[str, Any]]:
    return [
        {
            "path": item.path,
            "lineno": item.lineno,
            "end_lineno": item.end_lineno or item.lineno,
            "qualname": item.qualname,
            "snippet": truncate_bytes(item.snippet, 400)[0],
        }
        for item in answer.citations
    ]


def _error_payload(exc: Exception) -> dict[str, Any]:
    name = type(exc).__name__
    if name in {"UpstreamCircuitOpen", "UpstreamError"}:
        return {
            "code": "upstream_error",
            "title": "模型服务暂时不可用",
            "hint": "检查 CI_LLM_API_KEY 与 CI_LLM_BASE_URL，或稍后重试",
        }
    if name == "LLMNotConfigured":
        return {
            "code": "upstream_error",
            "title": "没有配置模型 API key",
            "hint": "在 .env 里设置 CI_LLM_API_KEY",
        }
    if "Timeout" in name:
        return {"code": "timeout", "title": "模型服务超时", "hint": "稍后重试或换更小的模型"}
    return {"code": "internal_error", "title": "Agent 运行出错", "hint": str(exc)[:120]}
