"""符号落库（规格 §1.2 A3）。

一条硬规则贯穿本文件：**`edge.dst_symbol_id` 能唯一解析才填**。

同名多义（两个文件里都有 `foo`）时必须留 NULL，靠 `dst_name` + `dst_qualname`
保留线索。随便挑一个会让「谁调用了谁」变成假数据——而这类假数据会一路流进
调用图、影响范围分析和答案里的引用，比留空糟糕得多（源文档 §2.2 要求
「动态调用等静态分析定不了的边要标 uncertain，不丢弃也不假装」）。

`SymbolIndex` 是落库的副产品，也是边解析的唯一依据：它记录了
「qualname → 符号 id 列表」「模块 → 名字 → 符号 id 列表」两张表，
供 `edges.py` 做唯一性判定。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field

from codeinsight.models import ParsedFile, ParsedSymbol, SymbolKind


def sha256_text(text: str) -> str:
    """文本的 sha256（十六进制）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def symbol_source(source_lines: list[str], lineno: int, end_lineno: int) -> str:
    """取符号的源码文本（1-based 闭区间）。"""
    if lineno < 1 or end_lineno < lineno:
        return ""
    return "\n".join(source_lines[lineno - 1 : end_lineno])


@dataclass
class SymbolIndex:
    """一次索引里所有符号的查找表。

    列表而非单值：**同名多义是常态**（`utils.parse` 在 5 个文件里都有定义），
    单值会诱导下游随便挑一个。
    """

    by_qualname: dict[str, list[int]] = field(default_factory=dict)
    by_name: dict[str, list[int]] = field(default_factory=dict)
    module_symbols: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    """模块 qualname → {符号名: [symbol_id]}，只收**模块级**的函数/类/常量。"""

    qualname_to_module: dict[str, str] = field(default_factory=dict)
    """符号 qualname → 所属模块 qualname。"""

    qualname_by_id: dict[int, str] = field(default_factory=dict)
    """符号 id → qualname（反查用）。"""

    imports_by_module: dict[str, list[str]] = field(default_factory=dict)
    """模块 qualname → 它 import 到的模块 qualname 列表。"""

    def add(self, qualname: str, name: str, symbol_id: int, module_qualname: str) -> None:
        self.by_qualname.setdefault(qualname, []).append(symbol_id)
        self.by_name.setdefault(name, []).append(symbol_id)
        self.qualname_to_module[qualname] = module_qualname
        self.qualname_by_id[symbol_id] = qualname

    def unique(self, qualname: str) -> int | None:
        """唯一命中才返回 id，多义或未命中返回 None。"""
        ids = self.by_qualname.get(qualname)
        if not ids or len(ids) != 1:
            return None
        return ids[0]

    def module_level(self, module_qualname: str, name: str) -> int | None:
        """模块级符号的唯一命中（同名多义返回 None）。"""
        bucket = self.module_symbols.get(module_qualname)
        if not bucket:
            return None
        ids = bucket.get(name)
        if not ids or len(ids) != 1:
            return None
        return ids[0]


def _is_module_level(symbol: ParsedSymbol, module_qualname: str) -> bool:
    """模块级 = 不属于任何类或嵌套函数。

    判据用 qualname 前缀而不是 `parent_qualname`：解析器对模块级函数的
    `parent_qualname` 可能是 None 也可能是模块名，两者都不该算成"有父级"。
    """
    return symbol.qualname.startswith(f"{module_qualname}.") and symbol.qualname.count(".") == (
        module_qualname.count(".") + 1
    )


def write_symbols(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    file_id: int,
    module_id: int | None,
    module_qualname: str,
    parsed: ParsedFile,
    source_lines: list[str],
    index: SymbolIndex,
) -> list[int]:
    """把一个文件的符号写进 `symbol` 表。

    返回写入的 symbol id 列表（顺序与 `parsed.symbols` 一致）。

    `parent_symbol_id` 用**两趟**写：先把所有符号插进去（parent 留 NULL），
    再按 `parent_qualname` 回填。这样不依赖解析器的输出顺序，
    也不会因为父符号在子符号之后出现而丢关系。
    """
    inserted: list[int] = []
    local_by_qualname: dict[str, int] = {}

    for symbol in parsed.symbols:
        text = symbol_source(source_lines, symbol.lineno, symbol.end_lineno)
        cur = conn.execute(
            """
            INSERT INTO symbol (
                project_id, file_id, module_id, qualname, name, kind,
                lineno, end_lineno, header, docstring,
                is_async, is_private, is_dunder, n_lines, source_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                file_id,
                module_id,
                symbol.qualname,
                symbol.name,
                str(symbol.kind),
                symbol.lineno,
                symbol.end_lineno,
                symbol.header,
                symbol.docstring,
                int(symbol.is_async),
                int(symbol.is_private),
                int(symbol.is_dunder),
                symbol.n_lines,
                sha256_text(text),
            ),
        )
        symbol_id = int(cur.lastrowid or 0)
        inserted.append(symbol_id)
        local_by_qualname[symbol.qualname] = symbol_id
        index.add(symbol.qualname, symbol.name, symbol_id, module_qualname)
        if _is_module_level(symbol, module_qualname):
            bucket = index.module_symbols.setdefault(module_qualname, {})
            bucket.setdefault(symbol.name, []).append(symbol_id)

    # 第二趟：回填 parent_symbol_id。
    for symbol, symbol_id in zip(parsed.symbols, inserted, strict=True):
        if not symbol.parent_qualname:
            continue
        parent_id = local_by_qualname.get(symbol.parent_qualname)
        if parent_id is not None and parent_id != symbol_id:
            conn.execute(
                "UPDATE symbol SET parent_symbol_id = ? WHERE id = ?",
                (parent_id, symbol_id),
            )

    # 本文件 import 到的模块（供跨文件解析调用边用）。
    modules = {imp.module for imp in parsed.imports if imp.module}
    if modules:
        index.imports_by_module.setdefault(module_qualname, []).extend(sorted(modules))

    return inserted


def write_module(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    file_id: int,
    qualname: str,
    docstring: str | None,
) -> int:
    """写一行 `module` 表，返回 module_id。

    **不能信 `lastrowid`**：走 ON CONFLICT DO UPDATE 时它可能还是上一条
    INSERT 留下的值——增量索引里模块行经常已存在，拿错 id 会写出一堆
    指向不存在模块的符号（外键当场报错，或者更糟：悄悄指向别的模块）。
    统一回查一次，代价是一次主键查询。
    """
    conn.execute(
        """
        INSERT INTO module (project_id, file_id, qualname, docstring)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(project_id, qualname) DO UPDATE SET
            file_id = excluded.file_id,
            docstring = excluded.docstring
        """,
        (project_id, file_id, qualname, docstring),
    )
    row = conn.execute(
        "SELECT id FROM module WHERE project_id = ? AND qualname = ?",
        (project_id, qualname),
    ).fetchone()
    return int(row[0])


__all__ = [
    "SymbolIndex",
    "sha256_text",
    "symbol_source",
    "write_module",
    "write_symbols",
    "SymbolKind",
]
