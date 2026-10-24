"""版本化学习资产，同一文章供目录阅读和模型章节检索使用。"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from types import MappingProxyType
from urllib.parse import unquote, urlsplit

from codeinsight.cognitive.concepts.learning_models import (
    KnowledgeContext,
    KnowledgeError,
    KnowledgeHit,
    KnowledgeSource,
    LearningTarget,
    Section,
    Topic,
)
from codeinsight.cognitive.concepts.ontology import ID_PATTERN, _strings
from codeinsight.cognitive.retrieval.tokenizer import split_identifiers

_HEADING = re.compile(r"^## (.+?) \{#([a-z][a-z0-9-]*)\}\s*$", re.MULTILINE)

_NON_SEARCHABLE_SECTIONS = frozenset({"sources", "related", "self-check"})
"""不进检索索引的章节。

- `sources` / `related`：来源清单与延伸阅读，不是教学内容。
- `self-check`：自测练习。读者搜「函数参数是什么」时，先跳到练习题上
  只会打断阅读——练习要给已经在读的人看，不该参与检索。
"""


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _normalize(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value).casefold()


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KnowledgeError(f"{path}: 无法读取 JSON：{exc}") from exc


def _plain_snippet(content: str, limit: int = 160) -> str:
    """把章节原文压成一段纯文本摘要。

    搜索结果的摘要要在卡片里直接显示，所以不能带 Markdown 标记——
    `**第一步**` 和 `` `CREATE TABLE` `` 原样显示出来是噪音。
    """
    text = content
    # 围栏代码块整段去掉：它是代码，不是摘要。
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    # 行内代码保留内容，去掉反引号。
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # 标题、列表、强调标记都去掉。
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "")
    # 站内链接保留文字。
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


class LearningLibrary:
    """只读文章集合；构造时验证全部内部链接，检索连接不跨线程共享。"""

    def __init__(
        self,
        directory: Path,
        *,
        tokenizer: Callable[[str], Sequence[str]] = split_identifiers,
    ) -> None:
        self.directory = Path(directory).resolve()
        self.tokenizer = tokenizer
        self.sources = MappingProxyType(self._load_sources())
        self.topics = MappingProxyType(self._load_topics())
        self._aliases: dict[str, set[str]] = {}
        for topic in self.topics.values():
            for alias in (topic.id, topic.title, *topic.aliases):
                self._aliases.setdefault(_normalize(alias), set()).add(topic.id)
        self._validate_links()
        self.version = _digest({key: topic.version for key, topic in sorted(self.topics.items())})
        self._rows = tuple(
            (
                topic.id,
                section.id,
                " ".join(
                    tokenizer(
                        f"{topic.title} {' '.join(topic.aliases)} {section.title} {section.content}"
                    )
                ),
            )
            for topic in self.topics.values()
            for section in topic.sections
            # 自测章节不进检索索引：读者搜「函数参数是什么」不该先跳到练习题上。
            # 章节本身照常显示，只是不参与搜索与模型上下文。
            if section.id not in _NON_SEARCHABLE_SECTIONS
        )

    def _load_sources(self) -> dict[str, KnowledgeSource]:
        path = self.directory / "sources.json"
        raw = _read_json(path)
        if not isinstance(raw, list):
            raise KnowledgeError(f"{path}: 来源清单必须是列表")
        result: dict[str, KnowledgeSource] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise KnowledgeError(f"{path}: 来源记录必须是映射")
            try:
                source = KnowledgeSource(**item)
            except TypeError as exc:
                raise KnowledgeError(f"{path}: 来源字段错误：{exc}") from exc
            if any(not isinstance(v, str) or not v.strip() for v in asdict(source).values()):
                raise KnowledgeError(f"{path}: 来源字段不能为空")
            if source.id in result or not ID_PATTERN.fullmatch(source.id):
                raise KnowledgeError(f"{path}: 重复或非法来源 ID {source.id}")
            if not re.fullmatch(r"[0-9a-f]{64}", source.sha256):
                raise KnowledgeError(f"{path}: 来源 {source.id} 缺少有效快照哈希")
            if any(urlsplit(url).scheme != "https" for url in (source.url, source.license_url)):
                raise KnowledgeError(f"{path}: 来源链接必须为 HTTPS")
            result[source.id] = source
        return result

    def _load_topics(self) -> dict[str, Topic]:
        index_path = self.directory / "index.json"
        raw = _read_json(index_path)
        if not isinstance(raw, list) or not raw:
            raise KnowledgeError(f"{index_path}: 文章清单必须是非空列表")
        topics: dict[str, Topic] = {}
        for item in raw:
            try:
                if not isinstance(item, dict):
                    raise KnowledgeError("文章条目必须是映射")
                for key in ("id", "title", "group", "summary", "file"):
                    if not isinstance(item.get(key), str) or not item[key].strip():
                        raise KnowledgeError(f"缺少 {key}")
                tid = item["id"]
                if not ID_PATTERN.fullmatch(tid) or tid in topics:
                    raise KnowledgeError(f"重复或非法文章 ID {tid}")
                path = (self.directory / item["file"]).resolve()
                if not path.is_relative_to(self.directory) or path.suffix != ".md":
                    raise KnowledgeError("文章路径必须是目录内的 Markdown 文件")
                body = path.read_text(encoding="utf-8")
                headings = list(_HEADING.finditer(body))
                if not headings:
                    raise KnowledgeError("缺少带稳定锚点的二级章节")
                sections = tuple(
                    Section(
                        h[2],
                        h[1],
                        body[
                            h.end() : headings[i + 1].start()
                            if i + 1 < len(headings)
                            else len(body)
                        ].strip(),
                    )
                    for i, h in enumerate(headings)
                )
                if len({s.id for s in sections}) != len(sections) or any(
                    not s.content for s in sections
                ):
                    raise KnowledgeError("章节 ID 重复或正文为空")
                sequences = {
                    key: _strings(item.get(key, []), key)
                    for key in ("aliases", "prerequisites", "related", "concept_ids", "source_ids")
                }
                if not sequences["source_ids"] or any(
                    s not in self.sources for s in sequences["source_ids"]
                ):
                    raise KnowledgeError("文章引用了未知来源或缺少来源")
                dialect = item.get("dialect")
                if dialect is not None and not isinstance(dialect, str):
                    raise KnowledgeError("dialect 必须是字符串")
                topics[tid] = Topic(
                    id=tid,
                    title=item["title"],
                    group=item["group"],
                    summary=item["summary"],
                    **sequences,
                    body=body,
                    sections=sections,
                    version=_digest(
                        {
                            "metadata": item,
                            "body": body,
                            "sources": [asdict(self.sources[s]) for s in sequences["source_ids"]],
                        }
                    ),
                    dialect=dialect,
                )
            except (KnowledgeError, OSError) as exc:
                raise KnowledgeError(
                    f"{index_path} / {item.get('id', '?') if isinstance(item, dict) else '?'}: {exc}"
                ) from exc
        return topics

    def _validate_links(self) -> None:
        for topic in self.topics.values():
            for tid in (*topic.prerequisites, *topic.related):
                if tid not in self.topics:
                    raise KnowledgeError(f"{topic.id}: 关联不存在的文章 {tid}")
            for href in re.findall(r"\]\((/learn/[^)]+)\)", topic.body):
                if self.resolve_href(href) is None:
                    raise KnowledgeError(f"{topic.id}: 悬空站内链接 {href}")

    def tree(self) -> list[dict]:
        """返回稳定顺序的目录；全局知识不要求 project_id。"""
        groups: dict[str, list[dict]] = {}
        for topic in self.topics.values():
            groups.setdefault(topic.group, []).append(
                {
                    "id": topic.id,
                    "title": topic.title,
                    "summary": topic.summary,
                    "version": topic.version,
                    "href": self.target(topic.id).href,
                }
            )
        return [{"title": title, "topics": topics} for title, topics in groups.items()]

    def get(self, topic_id: str) -> Topic | None:
        """未知 ID 返回 None，不读取任意路径。"""
        return self.topics.get(topic_id)

    def target(self, topic_id: str, section_id: str | None = None) -> LearningTarget | None:
        """仅为真实文章/章节生成链接；不接受过期章节。"""
        topic = self.get(topic_id)
        if topic is None or (section_id and section_id not in {s.id for s in topic.sections}):
            return None
        section_title = None
        if section_id:
            section = next((s for s in topic.sections if s.id == section_id), None)
            section_title = section.title if section else None
        return LearningTarget(topic.id, topic.title, topic.version, section_id, section_title)

    def resolve_term(
        self, term: str, *, context_topic_id: str | None = None
    ) -> LearningTarget | None:
        """同名术语优先当前文章语言；仍有歧义时不随意挑一篇。"""
        ids = self._aliases.get(_normalize(term), set())
        if len(ids) > 1 and context_topic_id in self.topics:
            group = self.topics[context_topic_id].group
            groups = {
                "React": ("React", "JavaScript", "TypeScript"),
                "TypeScript": ("TypeScript", "JavaScript"),
                "工程概念": ("工程概念", "Python"),
            }.get(group, (group,))
            for preferred in groups:
                matches = {tid for tid in ids if self.topics[tid].group == preferred}
                if matches:
                    ids = matches
                    break
        return self.target(next(iter(ids))) if len(ids) == 1 else None

    def resolve_href(self, href: str) -> LearningTarget | None:
        """站内地址严格限制目标格式，不把外部 URL 当知识目标。"""
        try:
            parts = urlsplit(href)
        except ValueError:
            # 未闭合的 IPv6 地址等也可能来自流式文本，不能中断整个回答。
            return None
        if parts.scheme or parts.netloc or parts.query or not parts.path.startswith("/learn/"):
            return None
        tid = unquote(parts.path[len("/learn/") :])
        return self.target(tid, unquote(parts.fragment) or None)

    def topics_for_concept(self, concept_id: str) -> tuple[Topic, ...]:
        """教材关联只返回文章；不会凭知识内容制造项目实例。"""
        return tuple(t for t in self.topics.values() if concept_id in t.concept_ids)

    def search(self, query: str, limit: int = 5) -> list[KnowledgeHit]:
        """章节级 FTS5 检索；查询按字面 token 转义，空查询和无命中返回空列表。

        `limit` 是**章节**数。调用方（教材目录的搜索框）按文章展示，
        需要更多章节才能凑够几篇文章——所以这里按 limit 乘以倍数取，
        让上层有得挑。
        """
        if limit <= 0 or not query.strip():
            return []
        tokens = tuple(dict.fromkeys(self.tokenizer(query)))[:64]
        if not tokens:
            return []
        # 每次查询拥有自己的连接，API 后台线程不会复用别的线程的 SQLite 连接。
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute(
                "CREATE VIRTUAL TABLE sections USING fts5(topic UNINDEXED, section UNINDEXED, tokens)"
            )
            conn.executemany("INSERT INTO sections VALUES(?,?,?)", self._rows)
            expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
            rows = conn.execute(
                "SELECT topic,section,bm25(sections) FROM sections WHERE sections MATCH ? ORDER BY bm25(sections),rowid LIMIT ?",
                (expression, 200),
            ).fetchall()
        term = re.sub(
            r"(?:是什么|是啥|什么意思|怎么理解|what is)[?？。\s]*$",
            "",
            query.strip(),
            flags=re.IGNORECASE,
        ).strip()
        exact = self.resolve_term(term)
        if exact:
            # 命中主题时，优先它的**第一节**——每篇文章的第一节就是入门那一节，
            # 但不再强制叫 overview。
            exact_topic = self.get(exact.topic_id)
            first = exact_topic.sections[0].id if exact_topic and exact_topic.sections else ""
            rows.sort(key=lambda row: (row[0] != exact.topic_id, row[1] != first, row[2]))
        result: list[KnowledgeHit] = []
        for tid, sid, score in rows[: min(limit, 50)]:
            topic = self.topics[tid]
            section = next(s for s in topic.sections if s.id == sid)
            result.append(
                KnowledgeHit(
                    self.target(tid, sid),
                    section.content,
                    -score,
                    tuple(self.sources[s] for s in topic.source_ids),
                    _plain_snippet(section.content),
                )
            )
        return result

    def context(self, hits: Iterable[KnowledgeHit], max_bytes: int = 12_000) -> KnowledgeContext:
        """整节纳入预算；放不下则跳过，不截断 Markdown 和结构化来源。"""
        parts: list[str] = []
        refs: list[KnowledgeHit] = []
        size = 0
        truncated = False
        for hit in hits:
            topic = self.get(hit.target.topic_id)
            # 没指定章节时取文章第一节（每篇的第一节就是入门），
            # 不再假设它一定叫 overview。
            default_section = topic.sections[0].id if topic and topic.sections else ""
            section_id = hit.target.section_id or default_section
            target = self.target(hit.target.topic_id, section_id)
            if topic is None or target is None or target.version != hit.target.version:
                truncated = True
                continue
            section = next(s for s in topic.sections if s.id == target.section_id)
            block = f"[教材；非项目代码证据] {target.href} version={target.version}\n{section.content}\n"
            n_bytes = len(block.encode("utf-8"))
            if size + n_bytes > max(0, max_bytes):
                truncated = True
                continue
            parts.append(block)
            size += n_bytes
            refs.append(
                KnowledgeHit(
                    target,
                    section.content,
                    hit.score,
                    tuple(self.sources[s] for s in topic.source_ids),
                )
            )
        return KnowledgeContext("".join(parts), tuple(refs), truncated)

    def reading_context(self, target: LearningTarget, max_bytes: int = 12_000) -> KnowledgeContext:
        """从本地资产重读指定版本；客户端正文和旧版本不进入模型。"""
        topic = self.get(target.topic_id)
        if topic is None or topic.version != target.version:
            return KnowledgeContext("", (), True)
        sections = [s for s in topic.sections if not target.section_id or s.id == target.section_id]
        if not sections:
            return KnowledgeContext("", (), True)
        return self.context(
            [
                KnowledgeHit(
                    self.target(topic.id, s.id),
                    s.content,
                    1.0,
                    tuple(self.sources[x] for x in topic.source_ids),
                )
                for s in sections
            ],
            max_bytes,
        )
