"""为回答提供可解析的学习目标；代码与已有 Markdown 链接保持原样。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from codeinsight.cognitive.concepts.learning_models import LearningTarget, LinkedAnswer
from codeinsight.cognitive.concepts.library import LearningLibrary

_PROTECTED = re.compile(
    r"(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[^\n]*(?:\n|$)"
    r"|(?m:^(`{3,}|~{3,})[^\n]*\n[\s\S]*\Z)"
    r"|(?m:^[ \t]{4}[^\n]*(?:\n|$))"
    r"|`+[^`\n]*`+|!?\[[^\]\n]*\]\([^\n)]*\)|<[^>\n]*>"
)


def link_answer(
    text: str,
    library: LearningLibrary,
    *,
    recommendations: Iterable[LearningTarget] = (),
) -> LinkedAnswer:
    """首次出现的无歧义术语加站内链接；末尾入口最多三项，正文不截数。"""
    terms = {
        term: library.resolve_term(term)
        for topic in library.topics.values()
        for term in (topic.title, *topic.aliases)
        if term
    }
    terms = {term: target for term, target in terms.items() if target is not None}
    pattern = re.compile(
        "|".join(
            (r"(?<![A-Za-z_0-9])" + re.escape(term) + r"(?![A-Za-z_0-9])")
            if term.isascii()
            else (
                r"(?<![\u3400-\u9fffA-Za-z_0-9])"
                + re.escape(term)
                + r"(?![\u3400-\u9fffA-Za-z_0-9])"
                if len(term) == 1
                else re.escape(term)
            )
            for term in sorted(terms, key=lambda term: (-len(term), term))
        )
        or r"(?!x)x",
        re.IGNORECASE,
    )
    visited: dict[str, LearningTarget] = {}
    seen_terms: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        term = match[0]
        if not term.isascii() and re.fullmatch(r"[\u3400-\u9fff]+", term):
            start, end = match.span()
            whole = match.string
            while start and re.fullmatch(r"[\u3400-\u9fff]", whole[start - 1]):
                start -= 1
            while end < len(whole) and re.fullmatch(r"[\u3400-\u9fff]", whole[end]):
                end += 1
            run = whole[start:end]
            # 不把“数据表示”里的“数据表”当术语；A 的中文分词器可提供精确词界。
            # 独立回退分词只在可确认的词界或独立术语上链接，未知词界宁可保留文字。
            if run != term and term not in library.tokenizer(run):
                return term
        target = library.resolve_term(term)
        normalized = re.sub(r"\s+", "", term).casefold()
        if target is None or normalized in seen_terms:
            return term
        seen_terms.add(normalized)
        visited[target.topic_id] = target
        return f"[{term}]({target.href})"

    pieces: list[str] = []
    cursor = 0
    for match in _PROTECTED.finditer(text):
        pieces.append(pattern.sub(replace, text[cursor : match.start()]))
        protected = match[0]
        for label, href in re.findall(r"\[([^\]]*)\]\((/learn/[^)]+)\)", protected):
            target = library.resolve_href(href)
            if target is not None:
                visited.setdefault(target.topic_id, target)
                seen_terms.add(re.sub(r"\s+", "", label).casefold())
        pieces.append(protected)
        cursor = match.end()
    pieces.append(pattern.sub(replace, text[cursor:]))
    entries: dict[str, LearningTarget] = {}
    for candidate in recommendations:
        target = library.target(candidate.topic_id, candidate.section_id)
        if target and target.version == candidate.version:
            entries.setdefault(target.topic_id, target)
        if len(entries) == 3:
            break
    return LinkedAnswer("".join(pieces), tuple(visited.values()), tuple(entries.values()))


def validate_answer_links(text: str, library: LearningLibrary) -> str:
    """将无效站内链接还原为文字；已验证链接与普通外链不变。"""
    pattern = re.compile(r"\[([^\]\n]+)\]\((/learn/[^)\n]+)\)")
    parts = []
    cursor = 0
    for match in _PROTECTED.finditer(text):
        parts.append(text[cursor : match.start()])
        protected = match[0]
        if protected.startswith("["):
            protected = pattern.sub(
                lambda m: m[0] if library.resolve_href(m[2]) else m[1], protected
            )
        parts.append(protected)
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts)
