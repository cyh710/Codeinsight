"""关键业务流程检测（规格 §1.2 A5）。

验收口径：**流程 = 从入口到有外部副作用的符号的一条路径**。
只讲调用关系是调用图，只讲副作用是清单，两头都定下来才是流程。
"""

from __future__ import annotations

from codeinsight.cognitive.indexing.flows import (
    FlowEdge,
    FlowEntry,
    FlowSymbol,
    detect_flows,
)


def _sym(sid: int, qualname: str, module: str, kind: str = "function") -> FlowSymbol:
    return FlowSymbol(
        id=sid,
        qualname=qualname,
        name=qualname.rsplit(".", 1)[-1],
        kind=kind,
        path=f"{module.replace('.', '/')}.py",
        lineno=1,
        module_qualname=module,
    )


def test_flow_is_a_path_from_entry_to_side_effect() -> None:
    symbols = [
        _sym(1, "app.main", "app", kind="module"),
        _sym(2, "app.main.handler", "app.main"),
        _sym(3, "app.main.store", "app.main"),
    ]
    edges = [
        FlowEdge(src_id=1, dst_id=2, kind="call", dst_name="handler"),
        FlowEdge(src_id=2, dst_id=3, kind="call", dst_name="store"),
        FlowEdge(src_id=3, dst_id=None, kind="call", dst_name="session.execute"),
    ]
    entries = [FlowEntry(kind="file", target="app.main", module_qualname="app.main")]

    flows = detect_flows(symbols, edges, entries)
    assert len(flows) == 1
    assert flows[0].steps[0].qualname == "app.main"
    assert flows[0].steps[-1].qualname == "app.main.store"
    assert "session.execute" in flows[0].description


def test_no_flow_without_side_effect() -> None:
    """纯计算的调用链不是流程——没有副作用就没有「流程」可言。"""
    symbols = [
        _sym(1, "app.main", "app", kind="module"),
        _sym(2, "app.main.pure", "app.main"),
    ]
    edges = [FlowEdge(src_id=2, dst_id=None, kind="call", dst_name="len")]
    entries = [FlowEntry(kind="file", target="app.main", module_qualname="app.main")]

    assert detect_flows(symbols, edges, entries) == []


def test_known_side_effect_module_is_detected() -> None:
    symbols = [
        _sym(1, "app.main", "app", kind="module"),
        _sym(2, "app.main.fetcher", "app.main"),
    ]
    edges = [
        FlowEdge(src_id=1, dst_id=2, kind="call", dst_name="fetcher"),
        FlowEdge(src_id=2, dst_id=None, kind="call", dst_name="requests.post"),
    ]
    entries = [FlowEntry(kind="file", target="app.main", module_qualname="app.main")]

    flows = detect_flows(symbols, edges, entries)
    assert len(flows) == 1


def test_weak_verbs_are_not_side_effects() -> None:
    """`x.run()` 满地都是——不能因为它就叫「执行」就算副作用。"""
    symbols = [
        _sym(1, "app.main", "app", kind="module"),
        _sym(2, "app.main.worker", "app.main"),
    ]
    edges = [FlowEdge(src_id=2, dst_id=None, kind="call", dst_name="worker.run")]
    entries = [FlowEntry(kind="file", target="app.main", module_qualname="app.main")]

    assert detect_flows(symbols, edges, entries) == []


def test_module_membership_is_not_a_call():
    symbols = [_sym(1, "app.main", "app", kind="module"), _sym(2, "app.main.unused", "app.main")]
    edges = [FlowEdge(src_id=2, dst_id=None, kind="call", dst_name="os.makedirs")]
    entries = [FlowEntry(kind="file", target="app.main", module_qualname="app.main")]
    assert detect_flows(symbols, edges, entries) == []


def test_nested_function_is_not_a_module_level_seed() -> None:
    """嵌套函数的 qualname 多一层，不该被当成入口的模块级函数。"""
    symbols = [
        _sym(1, "app.main", "app", kind="module"),
        _sym(2, "app.main.outer", "app.main"),
        _sym(3, "app.main.outer.inner", "app.main"),
    ]
    edges = [FlowEdge(src_id=3, dst_id=None, kind="call", dst_name="os.makedirs")]
    entries = [FlowEntry(kind="file", target="app.main", module_qualname="app.main")]

    # inner 不是模块级函数，不作为种子 → 走不到它 → 没有流程
    assert detect_flows(symbols, edges, entries) == []


def test_console_script_entry_resolves_to_the_function() -> None:
    symbols = [
        _sym(1, "app.main", "app", kind="module"),
        _sym(2, "app.main.run", "app.main"),
    ]
    edges = [FlowEdge(src_id=2, dst_id=None, kind="call", dst_name="os.makedirs")]
    entries = [
        FlowEntry(
            kind="console_script",
            target="app.main:run",
            module_qualname="app.main",
            symbol_qualname="app.main.run",
        )
    ]

    flows = detect_flows(symbols, edges, entries)
    assert len(flows) == 1
    assert flows[0].steps[-1].qualname == "app.main.run"


def test_one_flow_per_side_effect_symbol() -> None:
    """同一个副作用符号只记一条流——多条路径是同一件事。"""
    symbols = [
        _sym(1, "app.main", "app", kind="module"),
        _sym(2, "app.main.a", "app.main"),
        _sym(3, "app.main.b", "app.main"),
        _sym(4, "app.main.writer", "app.main"),
    ]
    edges = [
        FlowEdge(src_id=1, dst_id=2, kind="call", dst_name="a"),
        FlowEdge(src_id=1, dst_id=3, kind="call", dst_name="b"),
        FlowEdge(src_id=2, dst_id=4, kind="call", dst_name="writer"),
        FlowEdge(src_id=3, dst_id=4, kind="call", dst_name="writer"),
        FlowEdge(src_id=4, dst_id=None, kind="call", dst_name="os.remove"),
    ]
    entries = [FlowEntry(kind="file", target="app.main", module_qualname="app.main")]

    flows = detect_flows(symbols, edges, entries)
    assert len(flows) == 1
