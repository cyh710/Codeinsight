"""切块（规格 §1.2 A7 / ADR 0005）。

**符号是检索的原子**——用户问「X 在哪实现」，期望的答案边界就是符号边界。
固定字符窗口切出的「半个函数」既不满足检索，也不满足展示。

三种符号，三种切法：

| 符号 | 切法 | `content_kind` |
|---|---|---|
| 函数 / 方法 / 属性 | 整个符号；超过 `max_lines` 按**语句边界**二次切分 | `code` |
| 类 | 只切**类头 + docstring**——方法体归方法自己的块 | `doc` |
| 模块 | 只切**模块 docstring + import 行**——整个文件当一块会重复整个索引 | `init` |

类不切方法体，是因为方法已经有自己的块：重复入库会让 BM25 把方法文本
数两遍（权重被悄悄放大），向量索引里也多一份一模一样的内容。
这不是省事，是避免把同一个信号算两遍。

二次切分的关键约束（ADR 0005）：**`symbol_id` 仍指向原符号**。
于是「这个符号在哪」永远只有一个答案，而检索粒度可以比符号细。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from codeinsight.cognitive.retrieval.tokenizer import split_identifiers
from codeinsight.models import ParsedSymbol, SymbolKind

DEFAULT_MAX_CHUNK_LINES = 120


@dataclass(frozen=True)
class ChunkSpec:
    """一个待入库的块。"""

    ordinal: int
    part_count: int
    lineno: int
    end_lineno: int
    body: str
    token_text: str
    source_sha256: str
    header: str | None = None
    content_kind: str = "code"
    qualname: str | None = None
    name: str | None = None
    kind: str | None = None


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _leading_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _strip_indent(line: str, indent: str) -> str:
    """去掉固定缩进前缀。

    不用 `textwrap.dedent`——它要求**所有**行共享前缀，
    函数体里有一段顶格的多行字符串就会让它一个字符都退不掉，
    于是 `ast.parse` 失败、切分退回按行切。
    """
    if not indent:
        return line
    if line.startswith(indent):
        return line[len(indent) :]
    return line.lstrip() if not line.strip() else line


def _statement_units(
    source_lines: list[str],
    start: int,
    end: int,
    max_lines: int,
) -> list[tuple[int, int]]:
    """把符号切成「不可再分的语句单元」，返回 [(文件行号, 文件行号)]。

    用 `ast` 找真实的语句边界，而不是按行硬切——
    硬切会把 `if x:` 和它的 body 分到两块里，读起来是碎的。

    两个坑：
    1. 切出来的片段要单独 parse（方法体带缩进），行号是**相对片段**的，
       得加回偏移才是文件行号。
    2. parse 不了（语法错误）时退回按缩进找语句起点——
       宁可切得糙一点，也不要退化成「整个函数一块」。
    """
    block = source_lines[start - 1 : end]
    if not block:
        return []

    indent = _leading_indent(block[0])
    snippet = "\n".join(_strip_indent(line, indent) for line in block)
    offset = start - 1

    try:
        tree = ast.parse(snippet)
    except SyntaxError:
        return _indent_units(block, start, end)

    body = tree.body
    if len(body) == 1 and isinstance(
        body[0], ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ):
        body = body[0].body

    units: list[tuple[int, int]] = []
    for stmt in body:
        stmt_end = getattr(stmt, "end_lineno", stmt.lineno) or stmt.lineno
        if stmt_end + offset < start or stmt.lineno + offset > end:
            continue
        # `_expand_statement` 里的行号是**相对片段**的，统一在这里加回偏移。
        for unit_start, unit_end in _expand_statement(stmt, max_lines):
            units.append((unit_start + offset, unit_end + offset))
    return units


_STATEMENT_LIST_FIELDS = ("body", "orelse", "finalbody")
"""含语句列表的字段。`if` 的 `orelse` 是 elif/else，`try` 的 `handlers` 单独处理。"""


def _child_statements(stmt: ast.stmt) -> list[ast.stmt]:
    """取出语句的**直接子语句**，按源码顺序排好。

    `except` 处理块（`ast.excepthandler`）和 `match` 的 case 不是 `ast.stmt`，
    但它们里面的语句是——不取的话，`try/except` 的 except 体就整段丢了。
    """
    children: list[ast.stmt] = []
    for field in _STATEMENT_LIST_FIELDS:
        value = getattr(stmt, field, None)
        if isinstance(value, list):
            children.extend(item for item in value if isinstance(item, ast.stmt))

    for handler in getattr(stmt, "handlers", None) or []:
        children.extend(item for item in handler.body if isinstance(item, ast.stmt))

    for case in getattr(stmt, "cases", None) or []:
        children.extend(item for item in case.body if isinstance(item, ast.stmt))

    children.sort(key=lambda s: s.lineno)
    return children


def _expand_statement(stmt: ast.stmt, max_lines: int, depth: int = 0) -> list[tuple[int, int]]:
    """把一条语句展开成不超过 `max_lines` 的单元序列。

    一条语句本身太长（比如一个 900 行的 `if` 分支树）时，
    **递归下降**到它的子语句——这正是 ADR 0005 说的「AST 子节点递归切块」。

    不变量：返回的单元**连续覆盖** `[stmt.lineno, stmt.end_lineno]`，
    既不重叠也不丢行。父语句的头（`if cond:`、`except E:`）并入第一个子单元，
    所以每一块读起来都带着自己的上下文。
    """
    stmt_end = getattr(stmt, "end_lineno", stmt.lineno) or stmt.lineno
    if stmt_end - stmt.lineno + 1 <= max_lines or depth > 8:
        return [(stmt.lineno, stmt_end)]

    children = _child_statements(stmt)
    if not children:
        # 没有子语句可切（表达式语句、return 之类）——只能整条留着。
        return [(stmt.lineno, stmt_end)]

    units: list[tuple[int, int]] = []
    prev_end = stmt.lineno - 1
    for child in children:
        child_units = _expand_statement(child, max_lines, depth + 1)
        # 父语句头行 + 上一个子语句之后的残留行，并入这个子单元的第一块
        child_units[0] = (prev_end + 1, child_units[0][1])
        units.extend(child_units)
        prev_end = child_units[-1][1]

    # 兜底：万一子语句没覆盖到最后一行（罕见），补上尾巴，别把代码丢了。
    if prev_end < stmt_end:
        units.append((prev_end + 1, stmt_end))
    return units


def _indent_units(block: list[str], start: int, end: int) -> list[tuple[int, int]]:
    """parse 不了时的兜底：按缩进层级找语句起点。

    「与函数体第一层同缩进的非空行」= 一个新语句的开头。
    比按固定行数硬切好——至少不会把 `if` 和它的 body 分到两块。
    """
    if len(block) < 2:
        return [(start, end)]

    body_indent: str | None = None
    for line in block[1:]:
        if line.strip():
            body_indent = _leading_indent(line)
            break
    if body_indent is None:
        return [(start, end)]

    units: list[tuple[int, int]] = []
    unit_start: int | None = None
    for offset, line in enumerate(block):
        lineno = start + offset
        if not line.strip():
            continue
        indent = _leading_indent(line)
        if indent == body_indent:
            if unit_start is not None:
                units.append((unit_start, lineno - 1))
            unit_start = lineno
    if unit_start is not None:
        units.append((unit_start, end))
    return units or [(start, end)]


def _pack(units: list[tuple[int, int]], max_lines: int) -> list[tuple[int, int]]:
    """把单元贪心打包成不超过 `max_lines` 行的块。

    单个单元本身就超长时，只能让它超——宁可这一块大一点，
    也不要把一个逻辑单元劈开（劈开的块读起来是坏的）。
    """
    chunks: list[tuple[int, int]] = []
    cur: list[tuple[int, int]] = []
    cur_len = 0

    for start, end in units:
        unit_len = end - start + 1
        if cur and cur_len + unit_len > max_lines:
            chunks.append((cur[0][0], cur[-1][1]))
            cur = []
            cur_len = 0
        cur.append((start, end))
        cur_len += unit_len

    if cur:
        chunks.append((cur[0][0], cur[-1][1]))
    return chunks


def chunk_symbol(
    symbol: ParsedSymbol,
    source_lines: list[str],
    *,
    max_lines: int = DEFAULT_MAX_CHUNK_LINES,
    import_lines: list[int] | None = None,
) -> list[ChunkSpec]:
    """把一个符号切成块。

    参数
    ----
    symbol
        解析出的符号。
    source_lines
        **整个文件**的源码行（0-based 列表）。
    import_lines
        模块的 import 所在行号（1-based）。只有模块符号用得上。

    返回
    ----
    块列表。普通符号一块；超大符号多块，`ordinal` 递增、`part_count` 是总数。
    """
    start = max(symbol.lineno, 1)
    end = min(symbol.end_lineno, len(source_lines))
    if end < start:
        return []

    if symbol.kind is SymbolKind.MODULE:
        return _chunk_module(symbol, source_lines, start, end, import_lines or [])
    if symbol.kind is SymbolKind.CLASS:
        return _chunk_class(symbol, source_lines, start, end)

    # 函数 / 方法 / 属性
    units = _statement_units(source_lines, start, end, max_lines)
    if not units:
        units = [(start, end)]
    else:
        # 头一行（def / async def / @decorator）单独算一个单元，
        # 它是符号的身份，不能被切到第二块去。
        units = [(start, start), *units]

    ranges = _pack(units, max_lines)
    part_count = len(ranges)

    specs: list[ChunkSpec] = []
    for ordinal, (chunk_start, chunk_end) in enumerate(ranges):
        body = "\n".join(source_lines[chunk_start - 1 : chunk_end])
        specs.append(
            ChunkSpec(
                ordinal=ordinal,
                part_count=part_count,
                lineno=chunk_start,
                end_lineno=chunk_end,
                body=body,
                token_text=" ".join(split_identifiers(body)),
                source_sha256=_sha256(body),
                header=symbol.header,
                content_kind="code",
                qualname=symbol.qualname,
                name=symbol.name,
                kind=str(symbol.kind),
            )
        )
    return specs


def _chunk_class(
    symbol: ParsedSymbol,
    source_lines: list[str],
    start: int,
    end: int,
) -> list[ChunkSpec]:
    """类 → 只切类头 + docstring。"""
    header = symbol.header or ""
    doc = symbol.docstring or ""
    body = f"{header}\n{doc}".strip() if doc else header
    if not body:
        return []
    return [
        ChunkSpec(
            ordinal=0,
            part_count=1,
            lineno=start,
            end_lineno=start,
            body=body,
            token_text=" ".join(split_identifiers(body)),
            source_sha256=_sha256(body),
            header=header,
            content_kind="doc",
            qualname=symbol.qualname,
            name=symbol.name,
            kind=str(symbol.kind),
        )
    ]


def _chunk_module(
    symbol: ParsedSymbol,
    source_lines: list[str],
    start: int,
    end: int,
    import_lines: list[int],
) -> list[ChunkSpec]:
    """模块 → 模块 docstring + **模块头部的** import 行。

    整个文件当一块会把全文件内容重复一遍（每个符号都已经在库里），
    而且必然超长。模块块的价值在于「这个文件是干什么的、依赖了什么」。

    只取模块头部的 import：函数体里的 `import` 是实现细节，
    混进来会让模块块的范围一直延伸到文件末尾。
    """
    parts: list[str] = []
    if symbol.docstring:
        parts.append(symbol.docstring)

    header_imports = [lineno for lineno in import_lines if start <= lineno <= end]
    for lineno in header_imports:
        if lineno - 1 < len(source_lines):
            parts.append(source_lines[lineno - 1].strip())

    body = "\n".join(part for part in parts if part)
    if not body:
        return []

    return [
        ChunkSpec(
            ordinal=0,
            part_count=1,
            lineno=start,
            end_lineno=max(header_imports) if header_imports else start,
            body=body,
            token_text=" ".join(split_identifiers(body)),
            source_sha256=_sha256(body),
            header=None,
            content_kind="init",
            qualname=symbol.qualname,
            name=symbol.name,
            kind=str(symbol.kind),
        )
    ]
