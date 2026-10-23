"""Python 解析器。

验收口径（AGENTS.md §7）：符号数量与行号正确；语法错误文件不炸整次索引。
"""

from __future__ import annotations

import pytest

from codeinsight.cognitive.parsing.base import ParseContext
from codeinsight.cognitive.parsing.python_parser import PythonParser
from codeinsight.models import EdgeKind, SymbolKind

CTX = ParseContext(project_id=1, repo_root="D:/demo")


@pytest.fixture
def parser() -> PythonParser:
    return PythonParser()


def _parse(parser: PythonParser, source: str, path: str = "backend/core/mod.py"):
    return parser.parse(path, source, CTX)


def test_supports_only_python(parser: PythonParser) -> None:
    assert parser.supports("a/b.py")
    assert not parser.supports("a/b.ts")


def test_syntax_error_degrades_to_empty(parser: PythonParser) -> None:
    """坏文件不能抛异常——降级成空符号集（ADR 0012）。"""
    result = _parse(parser, "def broken(:\n    pass\n")
    assert result.symbols == ()
    assert result.edges == ()
    assert result.path == "backend/core/mod.py"


def test_module_symbol_is_created(parser: PythonParser) -> None:
    result = _parse(parser, '"""模块说明。"""\n')
    module = result.symbols[0]
    assert module.kind == SymbolKind.MODULE
    assert module.qualname == "backend.core.mod"
    assert module.docstring == "模块说明。"


def test_qualname_is_fully_qualified(parser: PythonParser) -> None:
    result = _parse(parser, "def helper():\n    pass\n")
    fn = next(s for s in result.symbols if s.name == "helper")
    assert fn.qualname == "backend.core.mod.helper"
    assert fn.kind == SymbolKind.FUNCTION


def test_class_method_and_nested_qualnames(parser: PythonParser) -> None:
    source = (
        "class Service:\n"
        "    def method(self):\n"
        "        def inner():\n"
        "            pass\n"
        "        return inner\n"
        "\n"
        "def outer():\n"
        "    def nested():\n"
        "        pass\n"
        "    return nested\n"
    )
    result = _parse(parser, source)
    quals = {s.qualname for s in result.symbols}
    assert "backend.core.mod.Service" in quals
    assert "backend.core.mod.Service.method" in quals
    assert "backend.core.mod.Service.method.inner" in quals
    assert "backend.core.mod.outer" in quals
    assert "backend.core.mod.outer.nested" in quals

    method = next(s for s in result.symbols if s.name == "method")
    assert method.kind == SymbolKind.METHOD
    assert method.parent_qualname == "backend.core.mod.Service"


def test_property_decorator_becomes_property_kind(parser: PythonParser) -> None:
    source = "class S:\n    @property\n    def value(self):\n        return 1\n"
    result = _parse(parser, source)
    prop = next(s for s in result.symbols if s.name == "value")
    assert prop.kind == SymbolKind.PROPERTY


def test_module_level_constant_is_detected(parser: PythonParser) -> None:
    source = "MAX_CHUNK_LINES = 120\n_PRIVATE_CONST = 1\nnot_const = 2\n"
    result = _parse(parser, source)
    consts = {s.name for s in result.symbols if s.kind == SymbolKind.CONSTANT}
    assert "MAX_CHUNK_LINES" in consts
    assert "_PRIVATE_CONST" in consts
    assert "not_const" not in consts


def test_line_numbers_are_accurate(parser: PythonParser) -> None:
    source = "x = 1\n\n\ndef target():\n    pass\n"
    result = _parse(parser, source)
    fn = next(s for s in result.symbols if s.name == "target")
    assert fn.lineno == 4
    assert fn.end_lineno == 5
    assert fn.n_lines == 2


def test_call_edge_uses_full_dotted_path(parser: PythonParser) -> None:
    """`jwt.decode(...)` 的 dst_name 要是 `jwt.decode`——本体里按全路径匹配。"""
    source = "import jwt\n\ndef go():\n    return jwt.decode('x')\n"
    result = _parse(parser, source)
    calls = [e for e in result.edges if e.kind == EdgeKind.CALL]
    assert any(e.dst_name == "jwt.decode" for e in calls)


def test_import_edge_uses_full_module_path(parser: PythonParser) -> None:
    """导入边用**完整模块路径**——`backend.config` 而不是 `backend`。

    否则项目内部上百条导入全变成同一个名字，既没法做模块依赖分析（§2.2-3），
    也没法做概念检测。
    """
    source = "import redis.asyncio\nfrom fastapi import FastAPI\n"
    result = _parse(parser, source)
    imports = [e for e in result.edges if e.kind == EdgeKind.IMPORTS]
    assert {e.dst_name for e in imports} == {"redis.asyncio", "fastapi"}
    modules = {i.module for i in result.imports}
    assert "redis.asyncio" in modules
    assert "fastapi" in modules


def test_relative_import_is_resolved_to_absolute_module(parser: PythonParser) -> None:
    """相对导入要解析成绝对模块路径。

    `backend/api/pet.py` 里 `from .core import x` → `backend.api.core`
    （当前包是 `backend.api`）；`from ..services import y` → `backend.services`。
    """
    source = "from .core import helper\nfrom ..services import store\n"
    result = parser.parse("backend/api/pet.py", source, CTX)
    imports = [e for e in result.edges if e.kind == EdgeKind.IMPORTS]
    names = {e.dst_name for e in imports}
    assert names == {"backend.api.core", "backend.services"}
    # 相对导入能确定是仓库内部的模块 → 直接给 dst_qualname
    assert all(e.dst_qualname == e.dst_name for e in imports)


def test_inherits_and_decorator_edges(parser: PythonParser) -> None:
    source = "import functools\n\n@functools.lru_cache\nclass Service(Base):\n    pass\n"
    result = _parse(parser, source)
    assert any(e.kind == EdgeKind.INHERITS and e.dst_name == "Base" for e in result.edges)
    assert any(
        e.kind == EdgeKind.DECORATOR and e.dst_name == "functools.lru_cache" for e in result.edges
    )


def test_dynamic_call_is_kept_but_uncertain(parser: PythonParser) -> None:
    """`getattr(...)` 这类动态调用：保留边 + confidence<1，不能丢也不能装作确定。"""
    source = "def go(obj):\n    return getattr(obj, 'run')()\n"
    result = _parse(parser, source)
    dynamic = [e for e in result.edges if e.dst_name.startswith("getattr")]
    assert dynamic, "动态调用被丢掉了"
    assert all(e.confidence < 1 for e in dynamic)
    assert all(e.dst_qualname is None for e in dynamic)


def test_local_call_resolves_to_qualname(parser: PythonParser) -> None:
    source = "def helper():\n    pass\n\ndef caller():\n    helper()\n"
    result = _parse(parser, source)
    resolved = [e for e in result.edges if e.kind == EdgeKind.CALL and e.dst_name == "helper"]
    assert resolved
    assert resolved[0].dst_qualname == "backend.core.mod.helper"


def test_self_method_call_resolves(parser: PythonParser) -> None:
    source = "class S:\n    def method(self):\n        pass\n\n    def caller(self):\n        self.method()\n"
    result = _parse(parser, source)
    resolved = [e for e in result.edges if e.dst_name == "self.method"]
    assert resolved
    assert resolved[0].dst_qualname == "backend.core.mod.S.method"


def test_attribute_read_becomes_reference_not_duplicate_call(parser: PythonParser) -> None:
    """`x = obj.attr` 是引用；`obj.attr()` 是调用——不能把后者又记成引用。"""
    source = "def go(obj):\n    a = obj.attr\n    obj.attr()\n    return a\n"
    result = _parse(parser, source)
    refs = [e for e in result.edges if e.kind == EdgeKind.REFERENCES]
    calls = [e for e in result.edges if e.kind == EdgeKind.CALL]
    assert len(refs) == 1
    assert refs[0].dst_name == "obj.attr"
    assert len(calls) == 1
    assert calls[0].dst_name == "obj.attr"


def test_init_file_module_qualname(parser: PythonParser) -> None:
    result = parser.parse("backend/__init__.py", "", CTX)
    assert result.symbols[0].qualname == "backend"


def test_async_function_flag(parser: PythonParser) -> None:
    source = "async def go():\n    pass\n"
    result = _parse(parser, source)
    fn = next(s for s in result.symbols if s.name == "go")
    assert fn.is_async is True
