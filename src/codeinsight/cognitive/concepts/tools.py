"""可注册到 A 线 Agent 的知识工具；教材来源不进入项目代码证据通道。"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from codeinsight.agent.tool import ToolContext, ToolResult
from codeinsight.cognitive.concepts.integration import LearningBridge


class SearchKnowledgeTool:
    """仅检索受维护教材，不读取项目、不调用 Provider。"""

    name = "search_knowledge"
    description = (
        "检索内置的编程基础教材。解释 SQL、Python、React 等概念时使用；"
        "返回的是教学资料，不能证明当前项目使用了相应技术。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "知识术语或问题，如 SQL 是什么"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    }
    mutating = False

    def __init__(self, bridge: LearningBridge, *, max_bytes: int = 12_000) -> None:
        self.bridge = bridge
        self.max_bytes = max(0, max_bytes)

    async def run(self, arguments: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        """参数错误、FTS 失败均可解释降级；结构化来源不受模型正文预算截断。"""
        query = arguments.get("query")
        limit = arguments.get("limit", 5)
        if not isinstance(query, str) or not query.strip():
            return ToolResult("请提供需要查询的知识术语或问题。", error="bad_request")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            return ToolResult("limit 必须为 1 到 10 的整数。", error="bad_request")
        try:
            result = self.bridge.search(query, limit, max_bytes=self.max_bytes)
        except sqlite3.Error:
            return ToolResult(
                "知识检索暂时不可用，仍可从目录阅读已有章节。", error="knowledge_search_failed"
            )
        if not result.data["items"]:
            return ToolResult(
                "内置知识库没有匹配章节，请尝试明确术语或从目录选择。", data=result.data
            )
        if not result.content:
            return ToolResult(
                "当前预算无法容纳完整章节，请缩小范围后重试。",
                data=result.data,
                truncated=True,
                error="knowledge_budget_exceeded",
            )
        return result


class ReadKnowledgeTopicTool:
    """按真实章节 ID 重读教材，客户端正文不能成为知识证据。"""

    name = "read_knowledge_topic"
    description = (
        "读取内置教材的一个章节。使用 search_knowledge 或目录返回的 topic_id 和 section_id；"
        "不指定章节时读取入门定义。内容标为教学资料，来源与项目 file:line 分开。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "topic_id": {"type": "string"},
            "section_id": {"type": "string", "description": "稳定章节 ID；缺省取文章第一节"},
            "version": {"type": "string", "description": "可选；提供时拒绝过期版本"},
        },
        "required": ["topic_id"],
    }
    mutating = False

    def __init__(self, bridge: LearningBridge, *, max_bytes: int = 12_000) -> None:
        self.bridge = bridge
        self.max_bytes = max(0, max_bytes)

    async def run(self, arguments: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        """仅返回实际注入的章节来源；章节导航作为独立结构化数据保留。"""
        topic_id = arguments.get("topic_id")
        section_id = arguments.get("section_id")
        if not isinstance(topic_id, str):
            return ToolResult("topic_id 必须为有效字符串。", error="bad_request")
        if section_id is None:
            # 缺省读第一节——每篇文章的第一节就是入门那节，章节名随内容而定。
            topic = self.bridge.library.get(topic_id)
            if topic is None or not topic.sections:
                return ToolResult("知识主题或章节不存在，请从目录重新选择。", error="topic_not_found")
            section_id = topic.sections[0].id
        if not isinstance(section_id, str):
            return ToolResult("section_id 必须为有效字符串。", error="bad_request")
        target = self.bridge.library.target(topic_id, section_id)
        if target is None:
            return ToolResult("知识主题或章节不存在，请从目录重新选择。", error="topic_not_found")
        raw = {**asdict(target), "version": arguments.get("version", target.version)}
        prepared = self.bridge.prepare_turn("", reading_context=raw, max_bytes=self.max_bytes)
        result = prepared.as_tool_result()
        topic = self.bridge.library.get(topic_id)
        data = {
            **result.data,
            "topic_id": topic.id,
            "version": topic.version,
            "sections": [
                {
                    "id": s.id,
                    "title": s.title,
                    "href": self.bridge.library.target(topic.id, s.id).href,
                }
                for s in topic.sections
            ],
        }
        return ToolResult(result.content, data, result.truncated, result.error)


def build_learning_tools(
    bridge: LearningBridge, *, max_bytes: int = 12_000
) -> tuple[SearchKnowledgeTool, ReadKnowledgeTopicTool]:
    """由 A 注册到现有 ToolRegistry；不修改既有 12 个项目工具及检索评测通道。"""
    return (
        SearchKnowledgeTool(bridge, max_bytes=max_bytes),
        ReadKnowledgeTopicTool(bridge, max_bytes=max_bytes),
    )
