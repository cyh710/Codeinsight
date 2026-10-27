"""保留连贯正文，核对可定位引用；旧 facts 字段不提供语义认证（ADR 0040）。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from codeinsight.models import Citation, ConceptInstance, Evidence

_CITATION = re.compile(r"\[([\w./\\-]+\.(?:py|pyi|tsx?|jsx?|sql|md|toml|ya?ml)):(\d+)(?:-(\d+))?\]")

_SENTENCE_END = re.compile(r"[。！？!?]+|\n+")

# markdown 块级结构：这些行不能按句子切——切了代码块和列表就废了。
# 前端是 markdown 渲染器，块的完整性直接决定界面长什么样。
_FENCE = "```"
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def _markdown_blocks(text: str) -> list[tuple[str, str]]:
    """把文本切成 (块类型, 块内容) —— 保住 markdown 的块结构。

    块类型：`prose`（普通段落）、`code`（``` 围起来的代码块）、
    `list`（列表项）、`heading`（标题行）、`blank`（空行，段落分隔）。

    事实/推断的判定要在块**内部**做（一句带引用就是事实），
    但块的边界必须原样保留——否则代码块被逐句切开、列表项被拆散，
    前端渲染出来就是一段糊在一起的文字。

    空行单独成块：markdown 靠空行分段，空行没了，段落就连成一片。
    """
    blocks: list[tuple[str, str]] = []
    in_code = False
    buffer: list[str] = []
    kind = "prose"

    def flush() -> None:
        nonlocal buffer, kind
        if buffer:
            blocks.append((kind, "".join(buffer)))
            buffer = []
        kind = "prose"

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(_FENCE):
            if in_code:
                buffer.append(line)
                flush()
                in_code = False
            else:
                flush()
                in_code = True
                kind = "code"
                buffer.append(line)
            continue
        if in_code:
            buffer.append(line)
            continue
        if not stripped:
            flush()
            # 空行是段落分隔，保留下来（连续空行合并成一个）。
            if not blocks or blocks[-1][0] != "blank":
                blocks.append(("blank", "\n\n"))
            continue
        if line.startswith("#"):
            flush()
            kind = "heading"
            buffer.append(line)
            flush()
            continue
        if _LIST_ITEM.match(line):
            if kind != "list":
                flush()
                kind = "list"
            buffer.append(line)
            continue
        flush()
        kind = "prose"
        buffer.append(line)

    if in_code and buffer:
        # 没闭合的围栏：当作代码块收尾，别把内容当散文。
        blocks.append(("code", "".join(buffer)))
    else:
        flush()
    return blocks


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
            self.add(
                GroundedFile(instance.path, instance.lineno, instance.lineno, instance.qualname)
            )

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

    def covers_range(self, path: str, start: int, end: int) -> bool:
        """范围内每行都须可定位；不按模型提供的巨大行号逐行遍历。"""
        if start < 1 or end < start:
            return False
        cursor = start
        for item in sorted(self._by_path.get(path, ()), key=lambda item: item.lineno):
            if item.lineno > cursor:
                break
            if item.end_lineno >= cursor:
                cursor = item.end_lineno + 1
            if cursor > end:
                return True
        return False

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


def split_answer(text: str, grounding: Grounding, *, preserve_invalid: bool = False) -> SplitAnswer:
    """仅提取对应有效位置的原文片段，无引用解释不作自动分类。

    preserve_invalid 是旧调用兼容参数；无效位置统一进入详情，不插入正文告警。
    """
    result = SplitAnswer(text="")
    seen_citations: set[tuple[str, int]] = set()
    paragraphs: list[str] = []

    for kind, block in _markdown_blocks(text):
        if kind in ("code", "heading", "blank"):
            # 代码块、标题与空行不是主张：整体保留，不参与事实/推断判定。
            paragraphs.append(block)
            continue
        if kind == "list":
            # 列表项各占一行：逐项判定，但行尾换行要留住。
            for item in block.splitlines(keepends=True):
                if not item.strip():
                    continue
                before = len(result.dropped_citations)
                cleaned, cited = _verify(
                    item, grounding, result.dropped_citations, preserve_invalid
                )
                paragraphs.append(cleaned)
                _record(
                    cleaned,
                    cited,
                    grounding,
                    result,
                    seen_citations,
                    invalid=len(result.dropped_citations) > before,
                )
            continue
        for sentence in _sentences(block):
            if not sentence.strip():
                paragraphs.append(sentence)
                continue
            before = len(result.dropped_citations)
            cleaned, cited = _verify(
                sentence, grounding, result.dropped_citations, preserve_invalid
            )
            paragraphs.append(cleaned)
            _record(
                cleaned,
                cited,
                grounding,
                result,
                seen_citations,
                invalid=len(result.dropped_citations) > before,
            )

    result.text = _join_paragraphs(paragraphs)
    return result


def _record(
    cleaned: str,
    cited: list[tuple[str, int]],
    grounding: Grounding,
    result: SplitAnswer,
    seen_citations: set[tuple[str, int]],
    *,
    invalid: bool = False,
) -> None:
    """旧 facts 仅保存对应位置的原文，不把无引用解释自动判为推断。"""
    if not cleaned.strip():
        return
    if cited:
        path, lineno = cited[0]
        anchor = grounding.nearest(path, lineno)
        if anchor is None:  # pragma: no cover —— _verify 只放行 grounded 位置
            return
        statement = {
            "text": _plain_text(_strip_markers(cleaned)),
            "citation": {
                "path": path,
                "lineno": lineno,
                "end_lineno": lineno,
                "qualname": anchor.qualname,
                "snippet": anchor.snippet,
            },
        }
        result.facts.append(statement)
        for path, lineno in cited:
            key = (path, lineno)
            if key in seen_citations:
                continue
            seen_citations.add(key)
            match = grounding.nearest(path, lineno)
            if match is not None:
                result.citations.append(
                    Citation(path, lineno, lineno, match.qualname, match.snippet)
                )


def _sentences(text: str) -> list[str]:
    """按句末标点与换行切句；**分隔符保留在原位**。

    早先的实现用 `re.split` 丢掉分隔符，正文里的换行因此全没了——
    markdown 的段落、列表、代码块糊成一段，界面上像一坨。

    切分结果里：句号等标点跟在句子后面；换行单独成一段。
    """
    pieces: list[str] = []
    for line in text.splitlines(keepends=True):
        if not line.strip():
            pieces.append(line)
            continue
        start = 0
        for match in _SENTENCE_END.finditer(line):
            if match.start() < start:
                continue
            piece = match.group(0)
            if piece in {"。", "！", "？", "!", "?"}:
                # 句末标点：连同它前面的正文一起成一段。
                end = match.end()
                # 中文答案常把引用放在句号后，不能把它拆成没有主张的独立“事实”。
                suffix = re.match(r"(?:[ \t]*" + _CITATION.pattern + r")+", line[end:])
                if suffix:
                    end += suffix.end()
                pieces.append(line[start:end])
                start = end
            else:
                # 换行：先落地正文，换行自己成一段。
                if match.start() > start:
                    pieces.append(line[start : match.start()])
                pieces.append(piece)
                start = match.end()
        if start < len(line):
            pieces.append(line[start:])
    return pieces


def _verify(
    sentence: str, grounding: Grounding, dropped: list[str], preserve_invalid: bool = False
) -> tuple[str, list[tuple[str, int]]]:
    """核对正文位置；无效引用移入详情，句子与示例原样保留。"""
    accepted: list[tuple[str, int]] = []
    protected = [
        (m.start(), m.end())
        for m in re.finditer(r"(`+)[\s\S]*?\1|\[[^\]\n]*\]\([^\)\n]*\)", sentence)
    ]

    def replace(match: re.Match[str]) -> str:
        path, start = match.group(1), int(match.group(2))
        if any(lo <= match.start() < hi for lo, hi in protected):
            return match.group(0)
        end = int(match.group(3) or start)
        if grounding.covers_range(path, start, end):
            accepted.append((path, start))
            return match.group(0)
        dropped.append(f"{path}:{start}" + (f"-{end}" if end != start else ""))
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


def _plain_text(text: str) -> str:
    """去掉 Markdown 标记，留纯文本。

    事实栏与推断栏是结构化卡片，不是 Markdown 渲染区——
    正文里的 `**编排层**`、行内代码反引号、列表编号留在卡片里只是噪声。
    聊天正文（`Answer.text`）保持原样，那里本来就按 Markdown 渲染。
    """
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    # 模型常把加粗标记跨句写（`**结论：……。**`），按句切开后两边各剩一半，
    # 上面的成对替换就匹配不到了——残留的 `**` 直接去掉。
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("`", "")
    cleaned = re.sub(r"^\s*\d+[.、]\s*", "", cleaned)
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned)
    return cleaned.strip()


def _looks_like_heading(text: str) -> bool:
    """标题行不是结论。

    模型爱用 `**核心实现**` 当小标题；如果把它也收进推断栏，用户会看到
    一堆「**核心实现**」「**HTTP 入口**」这样的条目——它们不是主张，
    只是排版。`#` 标题、纯列表符号、整行加粗都按标题处理。
    """
    stripped = text.strip()
    if re.fullmatch(r"#{1,6}\s+.*", stripped) or re.fullmatch(r"[*\-]\s*", stripped):
        return True
    if re.fullmatch(r"\*\*[^*]+\*\*[:：]?", stripped):
        return True
    # 「1. **小标题**」这种编号标题同理。
    return bool(re.fullmatch(r"\d+[.、]\s*\*\*[^*]+\*\*[:：]?", stripped))


def _join_paragraphs(paragraphs: list[str]) -> str:
    """把段落接回正文。

    连接规则：**空行是段落分隔**——段落之间要留空行（markdown 靠空行分段），
    段落内部的句子直接相连。空行由 `_markdown_blocks` 以 "\\n\\n" 的形式给出。
    """
    out = "".join(paragraphs)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def cited_locations(text: str) -> list[tuple[str, int]]:
    """抽出正文里声称的所有 `file:line`（不做校验）。测试与审计用。"""
    return [(m.group(1), int(m.group(2))) for m in _CITATION.finditer(text)]
