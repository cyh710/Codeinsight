"""A/C 接入用的只读服务；不在 B 线写项目库或注册 HTTP 路由。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from codeinsight.cognitive.concepts.learning_models import KnowledgeContext, LearningTarget
from codeinsight.cognitive.concepts.library import LearningLibrary
from codeinsight.models import ConceptInstance


def is_reading_follow_up(question: str) -> bool:
    """只识别没有独立术语的常用指代问题，不能用它猜测未提供的阅读目标。"""
    return bool(
        re.fullmatch(
            r"(?:请|请问|帮我)?(?:解释一下)?(?:这里|这儿|这段|这段代码|这一节|这句话|当前章节|这个)"
            r"(?:是什么意思|是什么|什么意思|怎么理解|讲了什么|为什么这样写|为什么要这样写|是干什么的|指什么)"
            r"[?？。！!\s]*",
            question.strip(),
        )
    )


@dataclass(frozen=True)
class ProjectConcepts:
    project_id: int
    head_commit: str
    index_epoch: int
    instances: tuple[ConceptInstance, ...]


class KnowledgeService:
    """全局教材与项目索引分开；项目没有注册时明确 not_indexed。"""

    def __init__(
        self, library: LearningLibrary, projects: Mapping[int, ProjectConcepts] | None = None
    ) -> None:
        self.library = library
        self.projects = dict(projects or {})

    def prepare_turn(
        self,
        question: str,
        *,
        reading: LearningTarget | None = None,
        max_bytes: int = 12_000,
    ) -> tuple[KnowledgeContext, tuple[LearningTarget, ...]]:
        """为 A 线提供同源阅读/检索上下文和至多三个入口，不在这里调用模型。"""
        reading_context = (
            self.library.reading_context(reading, max_bytes=max_bytes) if reading else None
        )
        hits = (
            [] if reading or is_reading_follow_up(question) else self._automatic_chapter(question)
        )
        references = [*(reading_context.references if reading_context else ()), *hits]
        unique = {}
        for hit in references:
            unique.setdefault((hit.target.topic_id, hit.target.section_id), hit)
        context = self.library.context(unique.values(), max_bytes=max_bytes)
        if reading_context and reading_context.truncated:
            context = KnowledgeContext(context.content, context.references, True)
        entries: dict[str, LearningTarget] = {}
        for hit in context.references:
            target = self.library.target(hit.target.topic_id)
            entries.setdefault(target.topic_id, target)
        return context, tuple(list(entries.values())[:3])

    def _automatic_chapter(self, question: str) -> list:
        """仅唯一明确术语自动补一节；普通项目问题交给显式知识工具。"""
        term = question.strip().strip("?？。！! ")
        term = re.sub(r"^(?:请问|请|我想知道|我想了解一下|我想了解)\s*", "", term)
        match = re.fullmatch(r"(?:什么是|解释一下|解释)\s*(.+)|(.+?)\s*(?:是什么|是什么意思)", term)
        if match:
            term = (match[1] or match[2]).strip()
        target = self.library.resolve_term(term)
        if target is None:
            return []
        topic = self.library.get(target.topic_id)
        hits = [
            h for h in self.library.search(term, limit=50) if h.target.topic_id == target.topic_id
        ]
        if hits:
            return hits[:1]
        if not topic or not topic.sections:
            return []
        from codeinsight.cognitive.concepts.learning_models import KnowledgeHit

        section = topic.sections[0]
        return [
            KnowledgeHit(
                self.library.target(topic.id, section.id),
                section.content,
                1.0,
                tuple(self.library.sources[s] for s in topic.source_ids),
            )
        ]

    def find_instances(
        self,
        project_id: int,
        *,
        concept_id: str | None = None,
        topic_id: str | None = None,
    ) -> dict:
        """返回当前项目版本内的实例；不能把其他项目的证据带过来。"""
        project = self.projects.get(project_id)
        if project is None:
            return {"status": "not_indexed", "items": [], "total": 0}
        concept_ids = {concept_id} if concept_id else set()
        if topic_id:
            topic = self.library.get(topic_id)
            if topic is None:
                return {"status": "topic_not_found", "items": [], "total": 0}
            concept_ids.update(topic.concept_ids)
        items = [i for i in project.instances if i.concept_id in concept_ids]
        return {
            "status": "ok",
            "items": items,
            "total": len(items),
            "head_commit": project.head_commit,
            "index_epoch": project.index_epoch,
        }

    def concepts_at(self, project_id: int, path: str, lineno: int | None = None) -> dict:
        """代码→概念标签查询；只返回同项目、同路径的真实检测位置。"""
        project = self.projects.get(project_id)
        if project is None:
            return {"status": "not_indexed", "items": []}
        return {
            "status": "ok",
            "items": [
                i
                for i in project.instances
                if i.path == path and (lineno is None or i.lineno == lineno)
            ],
        }

    def compare_claims(self, project_id: int, claims: Sequence[dict]) -> list[dict]:
        """M6 概念侧投影：未检出仅记未获支持，不断言历史设计已失效。"""
        project = self.projects.get(project_id)
        output = []
        for claim in claims:
            concept_id = claim.get("concept_id")
            if project is None:
                state = "not_indexed"
                matches = []
            else:
                matches = [i for i in project.instances if i.concept_id == concept_id]
                pattern = claim.get("pattern")
                if isinstance(pattern, str) and pattern:
                    matches = [
                        i for i in matches if pattern in i.evidence or pattern in (i.qualname or "")
                    ]
                state = (
                    "supported"
                    if any(i.confidence >= 0.8 for i in matches)
                    else ("uncertain" if matches else "not_observed")
                )
            output.append({"claim": claim, "status": state, "instances": matches})
        return output
