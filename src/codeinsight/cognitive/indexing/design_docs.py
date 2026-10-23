"""设计说明索引（规格 §1.2 A6，对应源文档 §2.4-5 / §2.4-5 问）。

源文档 §2.4 问的第五个问题最硬：

> **哪些历史设计说明已不再适用？**

「代码位置会过期」大家都懂；「**设计声明**也会过期」是另一回事——
ADR 说「用 Redis 做会话缓存」，代码后来换成了内存字典，
文档还是那份文档，但它已经不再描述这个项目了。

所以设计说明要能**被检查**。做法是把文档里的「声称」抽成结构化的 claim：

- 文档提到 `` `chunk_bm25` `` → 声称「有个叫 chunk_bm25 的东西」；
- 文档提到 `` backend/core/chunk_bm25.py `` → 声称「这个文件存在」。

M6 拿这些 claim 去和当前索引比对：符号不在了、文件不在了 → 这条设计说明过期。
claim 里还留 `concept_id` 字段，等 B 线的本体就位后可以补上「这条 ADR 讲的是
哪个概念」，两个过期通道（代码位置 / 概念实现）就都通了。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 设计说明可能待的地方
DESIGN_DOC_DIRS: tuple[str, ...] = (
    "docs/decisions/",
    "docs/adr/",
    "docs/adr-decisions/",
    "docs/architecture/decisions/",
    "doc/decisions/",
    "adr/",
)

DESIGN_DOC_PATTERNS: tuple[str, ...] = (
    "ADR-*.md",
    "adr-*.md",
    "docs/adr-*.md",
)

# 反引号里的标识符或路径
_BACKTICK_RE = re.compile(r"`([^`\n]{1,120})`")

# 文档里的行内路径（带扩展名）
_PATH_RE = re.compile(r"\b([A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|md))\b")

# 标识符：点号路径或驼峰/下划线单词
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")

# 「状态：已接受」这类中文/英文标记
_STATUS_RE = re.compile(
    r"(?:\*\*)?(?:状态|Status)(?:\*\*)?\s*[:：]\s*(?:\*\*)?([^\n*|]+)",
    re.IGNORECASE,
)

# 日期
_DATE_RE = re.compile(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})")

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_STATUS_MAP = {
    "已接受": "accepted",
    "接受": "accepted",
    "accepted": "accepted",
    "提议": "proposed",
    "proposed": "proposed",
    "已弃用": "deprecated",
    "弃用": "deprecated",
    "deprecated": "deprecated",
    "已取代": "superseded",
    "取代": "superseded",
    "superseded": "superseded",
}


@dataclass
class DesignDoc:
    """一篇设计说明。"""

    doc_id: str
    title: str
    path: str
    status: str | None = None
    decided_at: str | None = None
    body: str = ""
    claims: list[dict] = field(default_factory=list)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """拆出 YAML frontmatter（只支持 `key: value` 这种简单形式）。"""
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip().strip("\"'")
    return meta, text[match.end() :]


def _extract_title(body: str, path: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    stem = path.rsplit("/", 1)[-1]
    return stem[:-3] if stem.endswith(".md") else stem


def _extract_status(body: str, meta: dict[str, str]) -> str | None:
    if "status" in meta:
        raw = meta["status"]
    else:
        match = _STATUS_RE.search(body)
        raw = match.group(1).strip() if match else None
    if not raw:
        return None

    key = raw.strip().lower()
    if key in _STATUS_MAP:
        return _STATUS_MAP[key]
    # 状态常常带解释：「已接受（截至 2026-09-07 文档刷新时已生效）」
    # ——取前缀认状态，解释部分丢掉。
    for prefix, normalized in _STATUS_MAP.items():
        if key.startswith(prefix):
            return normalized
    return key


def _extract_claims(body: str) -> list[dict]:
    """抽出文档「声称存在」的东西。

    两类：
    - `path`：文档提到的文件路径 → 声称这个文件存在。
    - `symbol`：文档提到的标识符 → 声称有个这样的符号。

    只抽能**被验证**的：能落到索引里的符号或文件才算 claim。
    「这个设计很好」不是 claim——没法检查的东西不该进过期检测。
    """
    claims: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for match in _PATH_RE.finditer(body):
        value = match.group(1)
        key = ("path", value)
        if key in seen:
            continue
        seen.add(key)
        claims.append({"kind": "path", "value": value, "concept_id": None})

    for match in _BACKTICK_RE.finditer(body):
        value = match.group(1).strip()
        if not value or " " in value:
            continue
        if _PATH_RE.fullmatch(value):
            key = ("path", value)
            if key in seen:
                continue
            seen.add(key)
            claims.append({"kind": "path", "value": value, "concept_id": None})
            continue
        if not _IDENT_RE.match(value):
            continue
        # 太短的多半是占位符或关键字
        if len(value) < 3 or value in {"def", "class", "return", "self", "None", "True", "False"}:
            continue
        key = ("symbol", value)
        if key in seen:
            continue
        seen.add(key)
        claims.append({"kind": "symbol", "value": value, "concept_id": None})

    return claims


def is_design_doc(path: str) -> bool:
    """这个路径是不是设计说明。"""
    if not path.endswith(".md"):
        return False
    if any(path.startswith(prefix) for prefix in DESIGN_DOC_DIRS):
        return True
    name = path.rsplit("/", 1)[-1]
    return any(
        name.startswith(pattern.split("/")[-1].split("*")[0])
        for pattern in DESIGN_DOC_PATTERNS
        if "/" not in pattern
    )


def parse_design_doc(path: str, text: str) -> DesignDoc:
    """解析一篇设计说明。"""
    meta, body = _parse_frontmatter(text)
    stem = path.rsplit("/", 1)[-1]
    doc_id = meta.get("id") or (stem[:-3] if stem.endswith(".md") else stem)

    date_match = _DATE_RE.search(body[:2000])
    decided_at = meta.get("date") or (date_match.group(1) if date_match else None)

    return DesignDoc(
        doc_id=doc_id,
        title=meta.get("title") or _extract_title(body, path),
        path=path,
        status=_extract_status(body, meta),
        decided_at=decided_at,
        body=body,
        claims=_extract_claims(body),
    )


def parse_design_docs(files: list[str], sources: dict[str, str]) -> list[DesignDoc]:
    """把仓库里的设计说明全解析出来。"""
    docs: list[DesignDoc] = []
    for path in files:
        if not is_design_doc(path):
            continue
        text = sources.get(path)
        if text is None:
            continue
        docs.append(parse_design_doc(path, text))
    return docs
