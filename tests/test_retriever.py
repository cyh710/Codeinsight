"""检索器（规格 §1.2 A10 / A11）。

验收口径：
- 三路各自能跑；
- RRF **只用排名**（分数不可比也不怕）；
- 邻域扩展来的证据排在来源块之后，但不垫底；
- **通道开关 = 评测的不同臂**。
"""

from __future__ import annotations

import sqlite3

import pytest

from codeinsight.cognitive.retrieval.retriever import (
    LANE_BM25,
    LANE_SYMBOL,
    RetrievalConfig,
    Retriever,
)
from codeinsight.cognitive.retrieval.rrf import reciprocal_rank_fusion
from codeinsight.cognitive.retrieval.symbol_lane import SymbolRelationLane
from codeinsight.storage.sqlite import apply_schema, open_sqlite


# 一个迷你「项目」：
#   a.py:  def authenticate_user(token)  ← 被 b.py 调用
#   b.py:  def login() -> authenticate_user()
#   c.py:  def helper()
@pytest.fixture
def conn() -> sqlite3.Connection:
    c = open_sqlite(":memory:")
    apply_schema(c)
    c.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'demo', 'demo')")
    c.executemany(
        "INSERT INTO file (id, project_id, path, language, content_sha256)"
        " VALUES (?, 1, ?, 'python', 'h')",
        [(1, "a.py"), (2, "b.py"), (3, "c.py"), (4, "d.py")],
    )
    c.executemany(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " source_sha256) VALUES (?, 1, ?, ?, ?, 'function', 1, 3, 'h')",
        [
            (1, 1, "a.authenticate_user", "authenticate_user"),
            (2, 2, "b.login", "login"),
            (3, 3, "c.helper", "helper"),
            (4, 4, "d.validate_token", "validate_token"),
        ],
    )
    # b.login → a.authenticate_user
    c.execute(
        "INSERT INTO edge (project_id, src_symbol_id, dst_symbol_id, src_qualname, dst_name,"
        " dst_qualname, kind, lineno, confidence)"
        " VALUES (1, 2, 1, 'b.login', 'authenticate_user', 'a.authenticate_user', 'call', 2, 1.0)"
    )
    # a.authenticate_user -> d.validate_token
    c.execute(
        "INSERT INTO edge (project_id, src_symbol_id, dst_symbol_id, src_qualname, dst_name,"
        " dst_qualname, kind, lineno, confidence)"
        " VALUES (1, 1, 4, 'a.authenticate_user', 'validate_token', 'd.validate_token',"
        " 'call', 2, 1.0)"
    )
    c.commit()
    return c


def _add_chunk(conn: sqlite3.Connection, chunk_id: int, symbol_id: int, qualname: str, body: str):
    from codeinsight.cognitive.retrieval.tokenizer import token_text

    file_id = conn.execute("SELECT file_id FROM symbol WHERE id = ?", (symbol_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO chunk (id, project_id, symbol_id, file_id, ordinal, part_count, qualname,"
        " name, kind, lineno, end_lineno, body, token_text, source_sha256, file_content_sha256)"
        " VALUES (?, 1, ?, ?, 0, 1, ?, ?, 'function', 1, 3, ?, ?, 'h', 'h')",
        (
            chunk_id,
            symbol_id,
            file_id,
            qualname,
            qualname.split(".")[-1],
            body,
            token_text(body),
        ),
    )
    conn.commit()


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> sqlite3.Connection:
    _add_chunk(conn, 1, 1, "a.authenticate_user", "def authenticate_user(token):\n    return token")
    _add_chunk(conn, 2, 2, "b.login", "def login():\n    return authenticate_user('x')")
    _add_chunk(conn, 3, 3, "c.helper", "def helper():\n    return 1")
    # 这一块**不含**查询词——它只能靠邻域扩展进来
    _add_chunk(conn, 4, 4, "d.validate_token", "def validate_token(x): return True")
    return conn


# ── RRF ────────────────────────────────────────────────────


def test_rrf_uses_rank_not_score() -> None:
    """分数完全不可比的两路，RRF 照样能合。"""
    fused = reciprocal_rank_fusion(
        [
            [(1, -99.0), (2, -50.0)],  # bm25：负数
            [(3, 0.9), (1, 0.8)],  # 余弦
        ],
        k=60,
    )
    # 1 在两路都排第 1 → 排第一
    assert fused[0][0] == 1
    assert len(fused) == 3


def test_rrf_rewards_appearing_in_multiple_lanes() -> None:
    fused = reciprocal_rank_fusion(
        [
            [(10, 1.0), (20, 0.9)],
            [(20, 1.0), (30, 0.9)],
        ],
        k=60,
    )
    assert fused[0][0] == 20


def test_rrf_single_lane_preserves_order() -> None:
    fused = reciprocal_rank_fusion([[(5, 1.0), (6, 0.9), (7, 0.8)]], k=60)
    assert [item[0] for item in fused] == [5, 6, 7]


# ── 符号关系通道 ────────────────────────────────────────────


def test_symbol_lane_finds_the_definition(seeded: sqlite3.Connection) -> None:
    lane = SymbolRelationLane(seeded, project_id=1)
    hits = lane.collect("authenticate_user")
    assert hits
    assert hits[0].relation == "definition"
    assert hits[0].qualname == "a.authenticate_user"


def test_symbol_lane_expands_to_callers(seeded: sqlite3.Connection) -> None:
    lane = SymbolRelationLane(seeded, project_id=1)
    hits = lane.collect("authenticate_user")
    relations = {h.qualname: h.relation for h in hits}
    assert relations["b.login"] == "caller"


def test_symbol_lane_expands_to_callees(seeded: sqlite3.Connection) -> None:
    lane = SymbolRelationLane(seeded, project_id=1)
    hits = lane.collect("login")
    relations = {h.qualname: h.relation for h in hits}
    assert relations["a.authenticate_user"] == "callee"


def test_symbol_lane_matches_fully_qualified_name(seeded: sqlite3.Connection) -> None:
    lane = SymbolRelationLane(seeded, project_id=1)
    hits = lane.collect("a.authenticate_user")
    assert hits[0].qualname == "a.authenticate_user"


def test_symbol_lane_ignores_chinese_only_query(seeded: sqlite3.Connection) -> None:
    """纯中文提问没有标识符可匹配——这一路就该空着。"""
    lane = SymbolRelationLane(seeded, project_id=1)
    assert lane.collect("这个功能在哪实现") == []


def test_symbol_lane_maps_to_chunks(seeded: sqlite3.Connection) -> None:
    lane = SymbolRelationLane(seeded, project_id=1)
    results = lane.search("authenticate_user", k=5)
    assert results
    assert results[0][0] == 1


# ── 检索器 ──────────────────────────────────────────────────


def test_retriever_returns_evidence_with_file_line(seeded: sqlite3.Connection) -> None:
    retriever = Retriever(seeded)
    results = retriever.retrieve("authenticate_user", k=5, project_id=1)
    assert results
    top = results[0]
    assert top.path == "a.py"
    assert top.lineno == 1
    assert top.qualname == "a.authenticate_user"
    assert top.snippet


def test_retriever_records_which_lane_found_it(seeded: sqlite3.Connection) -> None:
    retriever = Retriever(seeded)
    results = retriever.retrieve("authenticate_user", k=5, project_id=1)
    lanes = {lane for item in results for lane in item.lanes}
    assert LANE_BM25 in lanes
    assert LANE_SYMBOL in lanes


def test_lane_switch_changes_results(seeded: sqlite3.Connection) -> None:
    """**同一套代码，不同的通道开关 = 评测的不同臂。**

    只开 BM25 时，中文提问捞不到东西；开了符号通道也捞不到
    （没有标识符可匹配）——这正说明两路看到的不是同一批东西。
    """
    bm25_only = Retriever(seeded, config=RetrievalConfig(lanes=frozenset({LANE_BM25}))).retrieve(
        "这个功能在哪实现", k=5, project_id=1
    )
    with_symbol = Retriever(
        seeded, config=RetrievalConfig(lanes=frozenset({LANE_BM25, LANE_SYMBOL}))
    ).retrieve("这个功能在哪实现", k=5, project_id=1)
    assert len(with_symbol) >= len(bm25_only)


def test_neighbor_expansion_adds_callers_with_discount(seeded: sqlite3.Connection) -> None:
    """命中 `authenticate_user` 后，它的调用者 `login` 也该进证据。"""
    retriever = Retriever(
        seeded,
        config=RetrievalConfig(lanes=frozenset({LANE_SYMBOL}), neighbor_depth=1),
    )
    results = retriever.retrieve("authenticate_user", k=5, project_id=1)
    quals = {item.qualname for item in results}
    assert "a.authenticate_user" in quals
    assert "b.login" in quals
    # 扩展来的排在来源后面
    scores = {item.qualname: item.score for item in results}
    assert scores["a.authenticate_user"] > scores["b.login"]


def test_neighbor_expansion_adds_callers_of_a_bm25_hit(seeded: sqlite3.Connection) -> None:
    """邻域扩展是**叠在融合结果之上**的一层，与通道本身无关。

    只开 BM25 时，命中的是 `authenticate_user` 那个块；
    扩展把它��调用者 `b.login` 带进来；关掉扩展就没有了。

    （符号通道本身就会展开调用者，所以要用只开 BM25 的配置来单独验证扩展。）
    """
    with_expansion = Retriever(
        seeded,
        config=RetrievalConfig(lanes=frozenset({LANE_BM25}), neighbor_depth=1),
    ).retrieve("authenticate_user", k=5, project_id=1)
    assert "d.validate_token" in {item.qualname for item in with_expansion}

    without = Retriever(
        seeded,
        config=RetrievalConfig(lanes=frozenset({LANE_BM25}), neighbor_depth=0),
    ).retrieve("authenticate_user", k=5, project_id=1)
    assert "d.validate_token" not in {item.qualname for item in without}


def test_empty_query_returns_nothing(seeded: sqlite3.Connection) -> None:
    assert Retriever(seeded).retrieve("", k=5, project_id=1) == []
    assert Retriever(seeded).retrieve("   ", k=5, project_id=1) == []


def test_k_limits_results(seeded: sqlite3.Connection) -> None:
    results = Retriever(seeded).retrieve("authenticate_user login helper", k=2, project_id=1)
    assert len(results) <= 2


def test_other_project_is_not_searched(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO project (id, name, root_path) VALUES (2, 'other', 'other')")
    conn.commit()
    retriever = Retriever(conn)
    assert retriever.retrieve("authenticate_user", k=5, project_id=2) == []


# ── 概念通道 ────────────────────────────────────────────────


def test_concept_lane_returns_instances(seeded: sqlite3.Connection) -> None:
    from codeinsight.cognitive.retrieval.concept_lane import ConceptLane

    seeded.execute(
        "INSERT INTO concept (id, name, category, summary, detection_json)"
        " VALUES ('jwt', 'JWT 令牌认证', 'auth', '用签名令牌承载身份声明。', '{}')"
    )
    seeded.execute(
        "INSERT INTO concept_instance (project_id, concept_id, symbol_id, file_id, path,"
        " lineno, qualname, evidence, confidence)"
        " VALUES (1, 'jwt', 1, 1, 'a.py', 1, 'a.authenticate_user', 'import jwt', 1.0)"
    )
    seeded.commit()

    lane = ConceptLane(seeded, project_id=1)
    matched = lane.match_concepts("JWT 认证怎么做的")
    assert matched
    assert matched[0][0] == "jwt"

    results = lane.search("JWT 认证怎么做的", k=5)
    assert results
    assert results[0][0] == 1
