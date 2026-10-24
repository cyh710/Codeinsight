"""BM25 关键词通道（规格 §1.2 A10）。

两个最容易踩的坑各有测试守着：
1. **FTS5 裸词是 AND 语义**——不显式 OR 就是空集。
2. **分词器的去重范围**——跨出现去重会把 BM25 的 tf 分量抹平。
"""

from __future__ import annotations

import sqlite3

import pytest

from codeinsight.cognitive.retrieval.bm25 import Fts5KeywordIndex, plan_query
from codeinsight.cognitive.retrieval.tokenizer import split_identifiers
from codeinsight.storage.sqlite import apply_schema, open_sqlite


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = open_sqlite(":memory:")
    apply_schema(connection)
    connection.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'p', 'p')")
    connection.execute(
        "INSERT INTO file (id, project_id, path, language, content_sha256)"
        " VALUES (1, 1, 'a.py', 'python', 'h')"
    )
    # 每个块挂各自的符号——chunk 的唯一键是 (project_id, symbol_id, ordinal)。
    connection.executemany(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " source_sha256) VALUES (?, 1, 1, ?, ?, 'function', 1, 2, 'h')",
        [(1, "a.f", "f"), (2, "a.g", "g"), (3, "a.h", "h")],
    )
    connection.commit()
    return connection


def _add_chunk(
    conn: sqlite3.Connection,
    chunk_id: int,
    qualname: str,
    body: str,
    *,
    project_id: int = 1,
    symbol_id: int = 1,
    file_id: int = 1,
    ordinal: int = 0,
) -> None:
    from codeinsight.cognitive.retrieval.tokenizer import token_text

    conn.execute(
        "INSERT INTO chunk (id, project_id, symbol_id, file_id, ordinal, part_count, qualname,"
        " lineno, end_lineno, body, token_text, source_sha256, file_content_sha256)"
        " VALUES (?, ?, ?, ?, ?, 1, ?, 1, 2, ?, ?, 'h', 'h')",
        (chunk_id, project_id, symbol_id, file_id, ordinal, qualname, body, token_text(body)),
    )
    conn.commit()


@pytest.fixture
def index(conn: sqlite3.Connection) -> Fts5KeywordIndex:
    _add_chunk(conn, 1, "a.auth", "def authenticate_user(token):\n    return token", symbol_id=1)
    _add_chunk(
        conn,
        2,
        "a.jwt",
        "import jwt\n\ndef decode_jwt(blob):\n    return jwt.decode(blob)",
        symbol_id=2,
    )
    _add_chunk(conn, 3, "a.other", "def helper():\n    return 1", symbol_id=3)
    return Fts5KeywordIndex(conn, project_id=1)


# ── 查询构造 ──────────────────────────────────────────────


def test_bare_tokens_are_anded_by_fts5_so_we_must_or_them() -> None:
    """裸词是 AND 语义——这个坑必须用测试钉住。"""
    plan = plan_query("jwt decode")
    assert " OR " in plan.match
    # 直接把分词结果丢给 FTS5 会要求同时命中 → 几乎必然空集
    assert plan.match != "jwt decode"


def test_match_expression_quotes_every_term() -> None:
    """不加引号的词会被 FTS5 当成语法。"""
    plan = plan_query("prepare_chat_stream")
    assert '"prepare_chat_stream"' in plan.match


def test_identifier_gets_a_phrase_clause() -> None:
    plan = plan_query("prepare_chat_stream 在哪")
    assert '"prepare chat stream"' in plan.match


def test_stopwords_are_dropped() -> None:
    plan = plan_query("how is the auth implemented")
    assert "the" not in plan.tokens
    assert "is" not in plan.tokens
    assert "auth" in plan.tokens


def test_empty_query_yields_empty_plan() -> None:
    assert plan_query("").is_empty
    assert plan_query("   ").is_empty


def test_only_stopwords_yields_empty_plan() -> None:
    assert plan_query("the is a").is_empty


# ── 检索行为 ──────────────────────────────────────────────


def test_search_finds_the_right_chunk(index: Fts5KeywordIndex) -> None:
    results = index.search("jwt decode", k=5)
    assert results
    assert results[0][0] == 2


def test_search_scores_are_descending(index: Fts5KeywordIndex) -> None:
    results = index.search("jwt decode helper", k=5)
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)


def test_search_returns_nothing_for_unmatched(index: Fts5KeywordIndex) -> None:
    assert index.search("kubernetes_operator_reconciler", k=5) == []


def test_empty_query_returns_nothing(index: Fts5KeywordIndex) -> None:
    assert index.search("", k=5) == []


def test_k_is_respected(index: Fts5KeywordIndex) -> None:
    assert len(index.search("jwt decode helper function", k=1)) == 1


def test_project_scope_is_enforced(conn: sqlite3.Connection) -> None:
    """别的项目的块不能被检索到。"""
    conn.execute("INSERT INTO project (id, name, root_path) VALUES (2, 'q', 'q')")
    conn.execute(
        "INSERT INTO file (id, project_id, path, language, content_sha256)"
        " VALUES (2, 2, 'b.py', 'python', 'h')"
    )
    conn.execute(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " source_sha256) VALUES (9, 2, 2, 'b.g', 'g', 'function', 1, 2, 'h')"
    )
    _add_chunk(conn, 9, "b.g", "def jwt_thing(): pass", project_id=2, symbol_id=9, file_id=2)

    index = Fts5KeywordIndex(conn, project_id=1)
    results = index.search("jwt_thing", k=5)
    assert all(chunk_id != 9 for chunk_id, _ in results)


# ── 分词器的词频（BM25 的 tf 分量） ─────────────────────────


def test_token_frequency_is_preserved() -> None:
    """同一个标识符出现多次，token 也要出现多次。

    早先的实现用全局 `seen` 去重，等于把 tf 恒定成 1，
    BM25 退化成纯 IDF 排序——词频那一半彻底失效。
    """
    tokens = split_identifiers("helper() helper() helper()")
    assert tokens.count("helper") == 3


def test_identifier_forms_are_not_duplicated_within_one_occurrence() -> None:
    """一次出现里，全名与小写形式相同就不该出两遍。"""
    tokens = split_identifiers("helper")
    assert tokens == ["helper"]
