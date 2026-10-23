"""切块（ADR 0005）。

验收口径：**符号是原子**；超大符号按语句边界二次切分；
切出来的块**不重不漏**地盖住原符号；`symbol_id` 不变。
"""

from __future__ import annotations

from codeinsight.cognitive.indexing.chunker import chunk_symbol
from codeinsight.cognitive.parsing.base import ParseContext
from codeinsight.cognitive.parsing.python_parser import PythonParser
from codeinsight.models import SymbolKind

CTX = ParseContext(project_id=1, repo_root="D:/demo")
PARSER = PythonParser()


def _symbols(source: str, path: str = "pkg/mod.py"):
    parsed = PARSER.parse(path, source, CTX)
    return parsed, source.splitlines()


def _find(parsed, name: str):
    return next(s for s in parsed.symbols if s.name == name)


def test_small_function_is_one_chunk() -> None:
    source = "def f():\n    return 1\n"
    parsed, lines = _symbols(source)
    specs = chunk_symbol(_find(parsed, "f"), lines)
    assert len(specs) == 1
    assert specs[0].ordinal == 0
    assert specs[0].part_count == 1
    assert specs[0].lineno == 1
    assert specs[0].end_lineno == 2
    assert specs[0].content_kind == "code"


def test_large_function_is_split_at_statement_boundaries() -> None:
    body = "\n".join(f"    x{i} = {i}" for i in range(1, 61))
    source = f"def big():\n{body}\n"
    parsed, lines = _symbols(source)
    specs = chunk_symbol(_find(parsed, "big"), lines, max_lines=20)

    assert len(specs) > 1
    assert all(spec.part_count == len(specs) for spec in specs)
    assert [s.ordinal for s in specs] == list(range(len(specs)))
    # 每块不超过上限（除了切不开的单条语句）
    assert max(s.end_lineno - s.lineno + 1 for s in specs) <= 20


def test_split_chunks_cover_the_symbol_exactly() -> None:
    """切出来的块必须**不重不漏**地盖住原符号——漏一行就是丢了代码。"""
    body = "\n".join(f"    x{i} = {i}" for i in range(1, 41))
    source = f"def big():\n{body}\n"
    parsed, lines = _symbols(source)
    symbol = _find(parsed, "big")
    specs = chunk_symbol(symbol, lines, max_lines=10)

    covered: list[int] = []
    for spec in specs:
        covered.extend(range(spec.lineno, spec.end_lineno + 1))
    assert covered == list(range(symbol.lineno, symbol.end_lineno + 1))


def test_class_chunk_is_header_and_docstring_only() -> None:
    """类不切方法体——方法有自己的块，重复入库会把 BM25 权重算两遍。"""
    source = 'class S:\n    """说明。"""\n\n    def method(self):\n        return 1\n'
    parsed, lines = _symbols(source)
    specs = chunk_symbol(_find(parsed, "S"), lines)

    assert len(specs) == 1
    assert specs[0].content_kind == "doc"
    assert "method" not in specs[0].body
    assert "说明" in specs[0].body


def test_module_chunk_is_docstring_and_imports() -> None:
    source = '"""模块说明。"""\n\nimport os\nfrom .core import helper\n\n\ndef f():\n    pass\n'
    parsed, lines = _symbols(source)
    module = next(s for s in parsed.symbols if s.kind is SymbolKind.MODULE)
    specs = chunk_symbol(module, lines, import_lines=[i.lineno for i in parsed.imports])

    assert len(specs) == 1
    assert specs[0].content_kind == "init"
    assert "模块说明" in specs[0].body
    assert "import os" in specs[0].body


def test_nested_if_is_split_without_losing_the_header() -> None:
    """递归下降切分时，`if cond:` 那一行要并进第一块。"""
    inner = "\n".join(f"        y{i} = {i}" for i in range(1, 31))
    source = f"def f():\n    if cond:\n{inner}\n"
    parsed, lines = _symbols(source)
    specs = chunk_symbol(_find(parsed, "f"), lines, max_lines=15)

    assert len(specs) > 1
    assert "if cond:" in specs[0].body


def test_try_except_body_is_not_lost() -> None:
    """`except` 处理块不是 `ast.stmt`——不 specially 处理就会整段丢代码。"""
    source = (
        "def f():\n"
        "    try:\n"
        "        a = 1\n"
        "    except ValueError:\n"
        "        b = 2\n"
        "    return a\n"
    )
    parsed, lines = _symbols(source)
    symbol = _find(parsed, "f")
    specs = chunk_symbol(symbol, lines, max_lines=3)

    covered = []
    for spec in specs:
        covered.extend(range(spec.lineno, spec.end_lineno + 1))
    assert covered == list(range(symbol.lineno, symbol.end_lineno + 1))
    assert "except ValueError:" in "\n".join(spec.body for spec in specs)
    assert "b = 2" in "\n".join(spec.body for spec in specs)


def test_chunk_token_text_is_pretokenized() -> None:
    source = "def get_user_name():\n    return 'x'\n"
    parsed, lines = _symbols(source)
    specs = chunk_symbol(_find(parsed, "get_user_name"), lines)
    assert "get_user_name" in specs[0].token_text
    assert "get user name" in specs[0].token_text
