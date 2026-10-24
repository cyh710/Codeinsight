"""A/C 共用的传输适配；不注册路由、不修改已冻结的问答模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from codeinsight.agent.tool import ToolResult
from codeinsight.cognitive.concepts.learning_models import (
    KnowledgeContext,
    LearningTarget,
)
from codeinsight.cognitive.concepts.links import link_answer, validate_answer_links
from codeinsight.cognitive.concepts.service import KnowledgeService, is_reading_follow_up


def _target(target: LearningTarget) -> dict[str, Any]:
    return {**asdict(target), "href": target.href}


def _sources(context: KnowledgeContext) -> list[dict[str, Any]]:
    return [{**asdict(hit), "target": _target(hit.target)} for hit in context.references]


@dataclass(frozen=True)
class PreparedKnowledge:
    """同一回合的只读快照；最终答案沿用本快照，不能重新检索后更换来源。"""

    context: KnowledgeContext
    entries: tuple[LearningTarget, ...]
    reading_status: str
    error: str | None = None

    def as_tool_result(self) -> ToolResult:
        """上下文预算只作用于模型正文；来源保留在不受截断的数据字段。"""
        return ToolResult(
            self.context.content,
            data={
                "knowledge_sources": _sources(self.context),
                "learning_entries": [_target(t) for t in self.entries],
                "reading_status": self.reading_status,
            },
            truncated=self.context.truncated,
            error=self.error,
        )


class LearningBridge:
    """提供可 JSON 序列化的目录、正文和回合元数据；所有正文从受维护资产重读。

    这是 B 线内部适配，不代表 A 已批准 HTTP 字段。C 可在契约冻结后用
    ToolResult.data 组装响应；A 通过 as_tool_result 注入独立知识通道。
    """

    def __init__(self, service: KnowledgeService) -> None:
        self.service = service
        self.library = service.library

    def tree(self) -> ToolResult:
        """全局目录不读取项目；知识库未导入项目时仍然可用。"""
        return ToolResult(
            f"内置知识库包含 {len(self.library.topics)} 个主题。",
            data={"groups": self.library.tree(), "version": self.library.version},
        )

    def topic(self, topic_id: str) -> ToolResult:
        """正文保留原始锚点，sections 提供可直接渲染的稳定章节 ID。"""
        topic = self.library.get(topic_id)
        if topic is None:
            return ToolResult("未找到这个知识主题，请从目录选择。", error="topic_not_found")
        return ToolResult(
            topic.summary,
            data={
                **asdict(topic),
                "href": self.library.target(topic_id).href,
                "sources": [asdict(self.library.sources[s]) for s in topic.source_ids],
                "prerequisite_targets": [
                    _target(self.library.target(t)) for t in topic.prerequisites
                ],
                "related_targets": [_target(self.library.target(t)) for t in topic.related],
            },
        )

    def search(self, query: str, limit: int = 5, *, max_bytes: int = 12_000) -> ToolResult:
        """列表返回实际章节；模型正文受预算约束，两者使用相同内容版本。"""
        hits = self.library.search(query, limit=limit)
        context = self.library.context(hits, max_bytes=max_bytes)
        return ToolResult(
            context.content,
            data={
                "items": [{**asdict(hit), "target": _target(hit.target)} for hit in hits],
                "total": len(hits),
                "knowledge_sources": _sources(context),
                "version": self.library.version,
            },
            truncated=context.truncated,
        )

    def prepare_turn(
        self,
        question: str,
        *,
        reading_context: Mapping[str, Any] | None = None,
        max_bytes: int = 12_000,
    ) -> PreparedKnowledge:
        """只接受知识 ID/章节/版本；客户端 title、snippet、正文均不能作为事实。

        code 类型由 A 线重新读取代码，本适配不把代码目标当教材处理。
        无效或过期阅读目标显式降级，仍允许独立检索问题本身。
        """
        reading = None
        status = "none"
        error = None
        if reading_context is not None:
            reading, status, error = self._reading_target(reading_context)
        elif is_reading_follow_up(question):
            status = "missing"
            error = "还没有可用的阅读目标；请先打开知识章节或明确要解释的内容。"
        context, entries = self.service.prepare_turn(question, reading=reading, max_bytes=max_bytes)
        if reading is not None and not any(
            hit.target.topic_id == reading.topic_id
            and (reading.section_id is None or hit.target.section_id == reading.section_id)
            for hit in context.references
        ):
            status = "outside_budget"
            error = "当前阅读章节超出上下文预算；请缩小范围后再问。"
        return PreparedKnowledge(context, entries, status, error)

    def prepare_goal(
        self,
        question: str,
        *,
        max_message_bytes: int,
        max_knowledge_bytes: int = 12_000,
        reading_context: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, str], PreparedKnowledge]:
        """在目标消息剩余预算内整节注入；不先注入再截掉章节却保留其引用。

        A 的 assemble 会继续处理整个回合的历史与工具结果。本方法只占用目标消息的
        明确剩余空间，不把教材夹进代码检索结果，也不改变原始问题的持久化内容。
        """
        opening = "\n\n以下为服务端读取的教材资料；教学示例不是当前项目的代码证据。\n<教材资料>\n"
        closing = "\n</教材资料>"
        overhead = len((question + opening + closing).encode("utf-8"))
        remaining = max(0, min(max_knowledge_bytes, max_message_bytes - overhead))
        prepared = self.prepare_turn(question, reading_context=reading_context, max_bytes=remaining)
        content = question
        if prepared.context.content:
            content += opening + prepared.context.content + closing
        return {"role": "user", "content": content}, prepared

    def _reading_target(
        self, raw: Mapping[str, Any]
    ) -> tuple[LearningTarget | None, str, str | None]:
        if raw.get("kind", "knowledge") != "knowledge":
            return None, "requires_code_reader", "代码阅读目标须由 Agent 的代码读取通道处理。"
        tid, sid, version = raw.get("topic_id"), raw.get("section_id"), raw.get("version")
        if (
            not isinstance(tid, str)
            or not isinstance(version, str)
            or not version
            or (sid is not None and (not isinstance(sid, str) or not sid))
        ):
            return None, "invalid", "阅读目标需要有效 topic_id、version 和可选 section_id。"
        target = self.library.target(tid, sid)
        if target is None:
            return None, "not_found", "当前阅读主题或章节已不存在，请重新选择。"
        if version != target.version:
            return None, "stale", "教材版本已更新，请重新打开章节后继续提问。"
        return target, "ok", None

    def finalize_answer(self, text: str, prepared: PreparedKnowledge) -> dict[str, Any]:
        """普通回答/SSE 最终答案共用同一投影；正文链接和引用分别保留。

        自动链接只表示可继续学习，不能充当回答已经引用该文章的证据。
        此方法仅给最终完整文本使用；流中增量由 C 线保持未完成链接不可点击。
        """
        linked = link_answer(
            validate_answer_links(text, self.library),
            self.library,
            recommendations=prepared.entries,
            context_topic_id=(
                prepared.context.references[0].target.topic_id
                if prepared.context.references
                else None
            ),
        )
        return {
            "text": linked.text,
            "knowledge_sources": _sources(prepared.context),
            "learning_entries": [_target(t) for t in linked.learning_entries],
            "learning_targets": [_target(t) for t in linked.targets],
            "reading_status": prepared.reading_status,
            "knowledge_error": prepared.error,
        }
