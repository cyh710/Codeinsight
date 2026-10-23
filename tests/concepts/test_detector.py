"""正反例验证证据边界，避免同名调用、字符串和动态边被升级成事实。"""

from codeinsight.cognitive.concepts.base import EdgeView, SymbolView
from codeinsight.cognitive.concepts.detector import RuleBasedDetector
from codeinsight.models import EdgeKind, SymbolKind


def edge(name, line=3, kind=EdgeKind.CALL, owner="demo.f"):
    return EdgeView(owner, name, kind, "demo.py", line)


def symbol(header="def f():", start=1, end=30):
    return SymbolView("demo.f", "f", SymbolKind.FUNCTION, "demo.py", start, end, header)


def test_alias_resolution_and_literal_same_name_rejection(concepts):
    detector = RuleBasedDetector(concepts)
    source = "import jwt as tokens\ndef f():\n    return tokens.decode('x', 'secret', algorithms=['HS256'])\n"
    match = edge("tokens.decode")
    results = detector.detect(
        [symbol()],
        [match],
        sources={"demo.py": source},
        edge_confidences={("demo.py", 3, "call", "tokens.decode"): 1.0},
    )
    assert any(
        i.concept_id == "jwt" and i.confidence == 1 and "→ jwt.decode" in i.evidence
        for i in results
    )
    other = "import codecs\ndef f():\n    return codecs.decode(b'x')\n"
    assert not any(
        i.concept_id == "jwt"
        for i in detector.detect([symbol()], [edge("codecs.decode")], sources={"demo.py": other})
    )


def test_parameter_shadowing_does_not_bypass_source_resolution(concepts):
    source = "import jwt\ndef f(jwt):\n    return jwt.decode('x')\n"
    detector = RuleBasedDetector(concepts)
    assert not any(
        i.concept_id == "jwt"
        for i in detector.detect([symbol()], [edge("jwt.decode")], sources={"demo.py": source})
    )


def test_uncertain_edges_and_missing_confidence_stay_uncertain(concepts):
    detector = RuleBasedDetector(concepts)
    results = detector.detect(
        [symbol()],
        [edge("jwt.decode")],
        edge_confidences={("demo.py", 3, "call", "jwt.decode"): 0.5},
    )
    assert next(i for i in results if i.concept_id == "jwt").confidence == 0.5
    results = detector.detect([symbol()], [edge("decode")])
    assert next(i for i in results if i.concept_id == "jwt").confidence < 0.8


def test_strings_and_commit_names_alone_do_not_prove_transactions(concepts):
    detector = RuleBasedDetector(concepts)
    source = 'def f():\n    message = "BEGIN IMMEDIATE"\n    conn.commit()\n'
    assert not any(
        i.concept_id == "db-transaction"
        for i in detector.detect([symbol()], [edge("conn.commit")], sources={"demo.py": source})
    )
    source = 'def f():\n    a.execute("BEGIN IMMEDIATE")\n    b.commit()\n'
    assert not any(
        i.concept_id == "db-transaction"
        for i in detector.detect([symbol()], [], sources={"demo.py": source})
    )


def test_transaction_is_grouped_by_connection_and_scope(concepts):
    detector = RuleBasedDetector(concepts)
    source = 'def f():\n    conn.execute("BEGIN IMMEDIATE")\n    conn.execute("INSERT INTO t VALUES(1)")\n    conn.commit()\n'
    results = detector.detect([symbol()], [], sources={"demo.py": source})
    transaction = next(i for i in results if i.concept_id == "db-transaction")
    assert transaction.lineno == 2 and "同作用域" in transaction.evidence
    assert transaction.confidence >= 0.8
    split = 'def f():\n    conn.execute("BEGIN IMMEDIATE")\ndef g():\n    conn.commit()\n'
    assert not any(
        i.concept_id == "db-transaction"
        for i in detector.detect([symbol()], [], sources={"demo.py": split})
    )


def test_nested_generator_and_async_owner_are_not_confused(concepts):
    source = "async def outer():\n    def inner():\n        yield 1\n    return inner\n"
    outer = symbol("async def outer():", 1, 4)
    outer.qualname = "demo.outer"
    inner = SymbolView(
        "demo.outer.inner", "inner", SymbolKind.FUNCTION, "demo.py", 2, 3, "def inner():"
    )
    results = RuleBasedDetector(concepts).detect([outer, inner], [], sources={"demo.py": source})
    assert next(i for i in results if i.concept_id == "generator").qualname == "demo.outer.inner"
    assert next(i for i in results if i.concept_id == "async").qualname == "demo.outer"


def test_bad_file_degrades_without_hiding_diagnostic(concepts):
    detector = RuleBasedDetector(concepts)
    results = detector.detect([], [], sources={"bad.py": "def broken("})
    assert results == [] and "bad.py" in detector.errors[0]


def test_repeated_rule_hits_have_unique_database_key(concepts):
    detector = RuleBasedDetector(concepts)
    source = "import jwt\ndef f():\n    return jwt.decode('x')\n"
    results = detector.detect(
        [symbol()], [edge("jwt.decode"), edge("jwt.decode")], sources={"demo.py": source}
    )
    keys = [(i.concept_id, i.path, i.lineno) for i in results]
    assert len(keys) == len(set(keys))


def test_cached_parameterized_function_is_not_certain_singleton(concepts):
    source = "from functools import lru_cache\n@lru_cache(maxsize=1)\ndef f(user):\n    return object()\n"
    results = RuleBasedDetector(concepts).detect(
        [symbol()], [edge("lru_cache", 2, EdgeKind.DECORATOR)], sources={"demo.py": source}
    )
    assert not any(i.concept_id == "singleton-lazy" and i.confidence >= 0.8 for i in results)


def test_logger_factory_does_not_prove_structured_logging(concepts):
    source = "import logging\ndef f():\n    return logging.getLogger('app')\n"
    results = RuleBasedDetector(concepts).detect(
        [symbol()],
        [edge("logging.getLogger")],
        sources={"demo.py": source},
        edge_confidences={("demo.py", 3, "call", "logging.getLogger"): 1.0},
    )
    assert next(i for i in results if i.concept_id == "structured-logging").confidence < 0.8


def test_similar_sql_word_is_not_a_transaction(concepts):
    source = 'def f():\n    conn.execute("BEGINNING OF DOCUMENT")\n    conn.commit()\n'
    results = RuleBasedDetector(concepts).detect([symbol()], [], sources={"demo.py": source})
    assert not any(i.concept_id == "db-transaction" for i in results)


def test_string_markers_only_augment_existing_evidence(concepts):
    source = 'def f():\n    conn.execute("BEGIN IMMEDIATE")\n    conn.commit()\n'
    results = RuleBasedDetector(concepts).detect([symbol()], [], sources={"demo.py": source})
    assert "辅助字符串 2: BEGIN IMMEDIATE" in next(
        i.evidence for i in results if i.concept_id == "db-transaction"
    )


def test_deep_expression_does_not_crash_whole_detection(concepts):
    source = "value = " + "+".join(["1"] * 1200)
    detector = RuleBasedDetector(concepts)
    assert detector.detect([], [], sources={"deep.py": source}) == []
