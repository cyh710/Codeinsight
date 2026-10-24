"""概念同步（概念检索通道的供数）。

分工：B 线拥有本体与检测规则，A 线负责把索引投影成检测器要的视图、
跑检测、把结果写进 `concept` / `concept_instance` 两张表。

验收口径：同步后**概念表里有本体、实例表里有真实位置**，
而且实例指向的符号确实存在（不能挂到不存在的符号上）。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codeinsight.cognitive.indexing.concepts_sync import sync_concepts
from codeinsight.storage.sqlite import apply_schema, open_sqlite

ONTOLOGY = """\
id: jwt
name: JWT 身份认证
category: auth
summary: 用签名令牌承载身份声明的无状态认证机制。
principles: |
  载荷编码后用对称或非对称密钥签名，验证方只需验签不需查库。
tradeoffs: |
  换取无状态与可水平扩展，代价是签发前无法即时吊销。
alternatives: |
  会话 ID + 服务端存储；不透明令牌 + 撤销表。
detection:
  import_names: [jwt]
  call_names: [jwt.decode]
  attribute_names: [Authorization]
  decorator_names: [requires_auth]
references: []
"""

SOURCE = """\
import jwt


def decode_token(blob):
    return jwt.decode(blob, "secret")


def auth_header(request):
    return request.headers.get("Authorization")
"""


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = open_sqlite(":memory:")
    apply_schema(c)
    c.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'demo', 'demo')")
    c.execute(
        "INSERT INTO file (id, project_id, path, language, content_sha256)"
        " VALUES (1, 1, 'auth.py', 'python', 'h')"
    )
    c.executemany(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " header, docstring, source_sha256)"
        " VALUES (?, 1, 1, ?, ?, 'function', ?, ?, 'def f():', '', 'h')",
        [
            (1, "auth.decode_token", "decode_token", 4, 5),
            (2, "auth.auth_header", "auth_header", 8, 9),
        ],
    )
    # 检测器在**边**上匹配规则，所以得有 import / call 边。
    c.executemany(
        "INSERT INTO edge (project_id, src_symbol_id, dst_symbol_id, src_qualname, dst_name,"
        " dst_qualname, kind, lineno, confidence)"
        " VALUES (1, 1, NULL, 'auth.decode_token', ?, NULL, ?, ?, 1.0)",
        [
            ("jwt", "imports", 1),
            ("jwt.decode", "call", 5),
        ],
    )
    c.commit()
    return c


@pytest.fixture
def ontology_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "concepts"
    directory.mkdir()
    (directory / "jwt.yaml").write_text(ONTOLOGY, encoding="utf-8")
    return directory


def test_sync_writes_concepts_and_instances(conn, ontology_dir) -> None:
    result = sync_concepts(
        conn,
        project_id=1,
        knowledge_dir=ontology_dir,
        sources={"auth.py": SOURCE},
    )
    assert result.concepts == 1
    assert result.instances >= 1

    concepts = conn.execute("SELECT id, name, category FROM concept").fetchall()
    assert concepts == [("jwt", "JWT 身份认证", "auth")]

    instances = conn.execute(
        "SELECT concept_id, path, lineno, symbol_id FROM concept_instance"
    ).fetchall()
    assert instances
    for concept_id, path, _lineno, symbol_id in instances:
        assert concept_id == "jwt"
        assert path == "auth.py"
        assert symbol_id in (1, 2)


def test_instance_points_at_a_real_symbol(conn, ontology_dir) -> None:
    """实例不能挂在不存在的符号上——不然检索到它也定位不了。"""
    sync_concepts(conn, project_id=1, knowledge_dir=ontology_dir, sources={"auth.py": SOURCE})
    rows = conn.execute(
        "SELECT ci.symbol_id, s.id FROM concept_instance ci LEFT JOIN symbol s ON s.id = ci.symbol_id"
    ).fetchall()
    assert rows
    for symbol_id, joined in rows:
        assert symbol_id is not None
        assert joined == symbol_id


def test_missing_ontology_is_not_an_error(conn, tmp_path) -> None:
    result = sync_concepts(conn, project_id=1, knowledge_dir=tmp_path / "nope")
    assert result.concepts == 0
    assert result.instances == 0


def test_sync_is_idempotent(conn, ontology_dir) -> None:
    """重跑同步不该堆出重复行。"""
    for _ in range(2):
        sync_concepts(conn, project_id=1, knowledge_dir=ontology_dir, sources={"auth.py": SOURCE})
    count = conn.execute("SELECT COUNT(*) FROM concept_instance").fetchone()[0]
    assert (
        count
        == conn.execute(
            "SELECT COUNT(DISTINCT concept_id || path || lineno) FROM concept_instance"
        ).fetchone()[0]
    )


def test_concept_lane_uses_the_synced_data(conn, ontology_dir) -> None:
    """同步完，概念通道就能查到实例。"""
    from codeinsight.cognitive.retrieval.concept_lane import ConceptLane

    sync_concepts(conn, project_id=1, knowledge_dir=ontology_dir, sources={"auth.py": SOURCE})
    conn.execute(
        "INSERT INTO chunk (id, project_id, symbol_id, file_id, ordinal, part_count, qualname,"
        " lineno, end_lineno, body, token_text, source_sha256, file_content_sha256)"
        " VALUES (1, 1, 1, 1, 0, 1, 'auth.decode_token', 4, 5, 'x', 'x', 'h', 'h')"
    )
    conn.commit()

    lane = ConceptLane(conn, project_id=1)
    matched = lane.match_concepts("JWT 认证怎么做的")
    assert matched
    assert matched[0][0] == "jwt"

    results = lane.search("JWT 认证怎么做的", k=5)
    assert results
    assert results[0][0] == 1
