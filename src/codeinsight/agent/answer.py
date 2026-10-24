"""答案的追溯化：把模型正文拆成**事实**与**推断**（ADR 0007）。

规则只有一条，但它是硬的：

    一句话里带**校验通过**的 `file:line` → 事实
    否则 → 推断

「校验通过」的意思是：这个位置在本回合**真的被工具读过或检索到过**。
模型很会编行号——`backend/api/pet.py:1209` 看起来和真的没区别。
所以不是「格式对就算」，而是拿本回合的 grounded 集合去对：

- 工具返回的检索证据（`Evidence` 的 lineno..end_lineno）；
- `read_file` 读过的行窗口；
- 概念实例的位置；
- 流程步骤、调用点、设计说明证据的位置。

对不上的 `file:line` 会**从正文里删掉**——宁可让用户看到一句没有出处的
推断，也不能让他看到一个编出来的「证据」。删掉之后那句话自然落到推断栏。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from codeinsight.models import Citation, ConceptInstance, Evidence

_CITATION = re.compile(r"\[([\w./\\-]+\.(?:py|pyi|tsx?|jsx?|sql|md|toml|ya?ml)):(\d+)(?:-(\d+))?\]")

DEFAULT_INFERENCE_CONFIDENCE = 0.5
"""模型没给置信度时的默认值：明确低于 1，提醒这是推断。"""

_SENTENCE_END = re.compile(r"(?<=[。！？!?])|\n+")


@dataclass(frozen=True)
class GroundedFile:
    """本回合真实出现过的代码位置。"""

    path: str
    lineno: int
    end_lineno: int
    qualname: str | None = None
    snippet: str = ""

    def covers(self, path: str, lineno: int) -> bool:
        return path == self.path and self.lineno <= lineno <= max(self.end_lineno, self.lineno)


class Grounding:
    """本回合的 grounded 集合。工具每返回一条证据就登记一次。"""

    def __init__(self) -> None:
        self._files: dict[tuple[str, int, int], GroundedFile] = {}
        self._by_path: dict[str, list[GroundedFile]] = {}

    def add(self, item: GroundedFile) -> None:
        key = (item.path, item.lineno, item.end_lineno)
        if key in self._files:
            return
        self._files[key] = item
        self._by_path.setdefault(item.path, []).append(item)

    def extend(self, items: Iterable[GroundedFile]) -> None:
        for item in items:
            self.add(item)

    def add_evidence(self, evidence: Iterable[Evidence]) -> None:
        for item in evidence:
            self.add(
                GroundedFile(
                    item.path,
                    item.lineno,
                    item.end_lineno or item.lineno,
                    item.qualname,
                    item.snippet,
                )
            )

    def add_instances(self, instances: Iterable[ConceptInstance]) -> None:
        for instance in instances:
            self.add(GroundedFile(instance.path, instance.lineno, instance.lineno, instance.qualname))

    def add_citations(self, citations: Iterable[Citation]) -> None:
        for item in citations:
            self.add(
                GroundedFile(
                    item.path,
                    item.lineno,
                    item.end_lineno or item.lineno,
                    item.qualname,
                    item.snippet,
                )
            )

    def covers(self, path: str, lineno: int) -> bool:
        return any(item.covers(path, lineno) for item in self._by_path.get(path, ()))

    def nearest(self, path: str, lineno: int) -> GroundedFile | None:
        """给一句事实挑引用：覆盖该行的那条；否则同文件里最近的一条。"""
        candidates = self._by_path.get(path)
        if not candidates:
            return None
        for item in candidates:
            if item.covers(path, lineno):
                return item
        return min(candidates, key=lambda item: abs(item.lineno - lineno))

    def __len__(self) -> int:
        return len(self._files)

    def citations(self) -> list[Citation]:
        return [
            Citation(item.path, item.lineno, item.end_lineno, item.qualname, item.snippet)
            for item in self._files.values()
        ]


@dataclass
class SplitAnswer:
    """拆分结果。"""

    text: str
    facts: list[dict[str, Any]] = field(default_factory=list)
    inferences: list[dict[str, Any]] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    dropped_citations: list[str] = field(default_factory=list)
    """本回合里出现、但 grounded 集合对不上的位置——审计用，不给用户看。"""


def split_answer(text: str, grounding: Grounding) -> SplitAnswer:
    """按句子拆事实/推断，并清掉校验不过的 `file:line`。"""
    result = SplitAnswer(text="")
    seen_citations: set[tuple[str, int]] = set()
    paragraphs: list[str] = []

    for sentence in _sentences(text):
        cleaned, cited = _verify(sentence, grounding, result.dropped_citations)
        paragraphs.append(cleaned)
        if not cleaned.strip():
            continue
        if cited:
            anchor = grounding.nearest(cited[0][0], cited[0][1])
            if anchor is None:  # pragma: no cover —— _verify 只放行 grounded 位置
                continue
            result.facts.append(
                {
                    "text": _strip_markers(cleaned).strip(),
                    "citation": {
                        "path": anchor.path,
                        "lineno": anchor.lineno,
                        "end_lineno": anchor.end_lineno,
                        "qualname": anchor.qualname,
                        "snippet": anchor.snippet,
                    },
                }
            )
            for path, lineno in cited:
                key = (path, lineno)
                if key in seen_citations:
                    continue
                seen_citations.add(key)
                match = grounding.nearest(path, lineno)
                if match is not None:
                    result.citations.append(
                        Citation(match.path, match.lineno, match.end_lineno, match.qualname, match.snippet)
                    )
        elif not _looks_like_heading(cleaned):
            result.inferences.append(
                {"text": _strip_markers(cleaned).strip(), "confidence": DEFAULT_INFERENCE_CONFIDENCE}
            )

    result.text = _join_paragraphs(paragraphs)
    return result


def _sentences(text: str) -> list[str]:
    """按句末标点与换行切句；保留标点。"""
    pieces: list[str] = []
    for line in text.splitlines(keepends=True):
        if not line.strip():
            pieces.append(line)
            continue
        buffer = ""
        for piece in _SENTENCE_END.split(line):
            if not piece:
                continue
            if piece in {"。", "！", "？", "!", "?"}:
                buffer += piece
                pieces.append(buffer)
                buffer = ""
            else:
                if buffer:
                    pieces.append(buffer)
                buffer = piece
        if buffer:
            pieces.append(buffer)
    return pieces


def _verify(
    sentence: str, grounding: Grounding, dropped: list[str]
) -> tuple[str, list[tuple[str, int]]]:
    """把句子里的引用分成「通过」与「编造」；编造的从文本里删掉。"""
    accepted: list[tuple[str, int]] = []

    def replace(match: re.Match[str]) -> str:
        path, start = match.group(1), int(match.group(2))
        if grounding.covers(path, start):
            accepted.append((path, start))
            return match.group(0)
        dropped.append(f"{path}:{start}")
        return ""

    cleaned = _CITATION.sub(replace, sentence)
    # 删掉引用后可能留下多余空格或空括号，收拾一下。
    cleaned = re.sub(r"（\s*）|\(\s*\)", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    if not cleaned.strip().strip("。！？!?，,、 "):
        cleaned = ""
    return cleaned, accepted


def _strip_markers(text: str) -> str:
    """去掉引用标记并把留下的空格收拾干净（`入口在 [a.py:3]。` → `入口在。`）。"""
    cleaned = _CITATION.sub("", text)
    cleaned = re.sub(r"[ \t]+([。，！？；：、）」』])", r"\1", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned)


def _looks_like_heading(text: str) -> bool:
    stripped = text.strip()
    return bool(re.fullmatch(r"#{1,6}\s+.*", stripped) or re.fullmatch(r"[*\-]\s*", stripped))


def _join_paragraphs(paragraphs: list[str]) -> str:
    out = "".join(paragraphs)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def cited_locations(text: str) -> list[tuple[str, int]]:
    """抽出正文里声称的所有 `file:line`（不做校验）。测试与审计用。"""
    return [(m.group(1), int(m.group(2))) for m in _CITATION.finditer(text)]
