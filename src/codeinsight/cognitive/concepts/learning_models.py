"""学习服务内部模型；不代替由 A 线冻结的 HTTP 契约。"""

from __future__ import annotations

from dataclasses import dataclass, field


class KnowledgeError(ValueError):
    """知识资产校验错误，必须在加载期暴露文件与原因。"""


@dataclass(frozen=True)
class KnowledgeSource:
    id: str
    title: str
    author: str
    url: str
    version: str
    license: str
    license_url: str
    retrieved_at: str
    sha256: str
    modifications: str


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    content: str


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    group: str
    aliases: tuple[str, ...]
    summary: str
    prerequisites: tuple[str, ...]
    related: tuple[str, ...]
    concept_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    body: str
    sections: tuple[Section, ...]
    version: str
    dialect: str | None = None


@dataclass(frozen=True)
class LearningTarget:
    topic_id: str
    title: str
    version: str
    section_id: str | None = None
    section_title: str | None = None
    """章节标题（如「跟着例子理解」）——给界面用。

    `section_id` 是内部锚点（overview / example / mechanism），
    直接显示给用户是内部术语，读不懂。
    """

    @property
    def href(self) -> str:
        """只生成资产目录中已校验 ID 的站内地址。"""
        suffix = f"#{self.section_id}" if self.section_id else ""
        return f"/learn/{self.topic_id}{suffix}"


@dataclass(frozen=True)
class KnowledgeHit:
    target: LearningTarget
    snippet: str
    score: float
    sources: tuple[KnowledgeSource, ...]


@dataclass(frozen=True)
class KnowledgeContext:
    content: str
    references: tuple[KnowledgeHit, ...]
    truncated: bool = False


@dataclass(frozen=True)
class Relation:
    src_qualname: str
    dst_qualname: str
    path: str
    lineno: int
    confidence: float = 1.0


@dataclass(frozen=True)
class Explanation:
    concept_id: str
    depth: str
    summary: str
    facts: tuple[dict, ...] = ()
    inferences: tuple[dict, ...] = ()
    instances: tuple = ()
    llm_used: bool = False
    error: str | None = None
    knowledge_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinkedAnswer:
    text: str
    targets: tuple[LearningTarget, ...]
    learning_entries: tuple[LearningTarget, ...] = field(default_factory=tuple)
