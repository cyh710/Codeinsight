"""稠密向量索引（规格 §1.2 A8 / ADR 0002）。"""

from __future__ import annotations

import numpy as np
import pytest

from codeinsight.cognitive.retrieval.dense import (
    SqliteVectorStore,
    register_model,
    reusable_vector_ids,
)
from codeinsight.storage.sqlite import apply_schema, open_sqlite


@pytest.fixture
def conn():
    connection = open_sqlite(":memory:")
    apply_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def store(conn) -> SqliteVectorStore:
    register_model(conn, model_id="test@4", dim=4)
    # embedding 外键指向 chunk，chunk 又指向 symbol/file/project——
    # 外键是开着的，所以这条链得完整建出来。
    conn.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'p', 'p')")
    conn.execute(
        "INSERT INTO file (id, project_id, path, language, content_sha256)"
        " VALUES (1, 1, 'a.py', 'python', 'h')"
    )
    conn.execute(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno,"
        " end_lineno, source_sha256) VALUES (1, 1, 1, 'a.f', 'f', 'function', 1, 2, 'h')"
    )
    for chunk_id in (1, 2, 3):
        conn.execute(
            "INSERT INTO chunk (id, project_id, symbol_id, file_id, ordinal, lineno, end_lineno,"
            " body, token_text, source_sha256, file_content_sha256)"
            " VALUES (?, 1, 1, 1, ?, 1, 2, 'x', 'x', 'h', 'h')",
            (chunk_id, chunk_id - 1),
        )
    conn.commit()
    return SqliteVectorStore(conn, model_id="test@4", db_path=":memory:", index_epoch=1)


def test_upsert_and_query_returns_similar_first(store) -> None:
    store.upsert(
        [1, 2, 3],
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0, 0.0],
        ],
    )
    assert store.count() == 3

    results = store.query([1.0, 0.0, 0.0, 0.0], k=3)
    assert [chunk_id for chunk_id, _ in results] == [1, 3, 2]
    assert results[0][1] == pytest.approx(1.0)
    # 余弦相似度落在 [-1, 1]
    assert all(-1.0 <= score <= 1.0 for _, score in results)


def test_query_respects_k(store) -> None:
    store.upsert([1, 2, 3], [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0]])
    assert len(store.query([1.0, 0, 0, 0], k=2)) == 2


def test_empty_store_returns_nothing(store) -> None:
    assert store.query([1.0, 0, 0, 0], k=5) == []


def test_dimension_mismatch_is_an_error(store) -> None:
    store.upsert([1], [[1.0, 0.0, 0.0, 0.0]])
    with pytest.raises(ValueError):
        store.query([1.0, 0.0], k=1)


def test_upsert_overwrites(store) -> None:
    store.upsert([1], [[1.0, 0.0, 0.0, 0.0]])
    store.upsert([1], [[0.0, 1.0, 0.0, 0.0]])
    assert store.count() == 1
    results = store.query([0.0, 1.0, 0.0, 0.0], k=1)
    assert results[0][0] == 1
    assert results[0][1] == pytest.approx(1.0)


def test_delete_removes_vectors(store) -> None:
    store.upsert([1, 2], [[1.0, 0, 0, 0], [0, 1.0, 0, 0]])
    store.delete([1])
    assert store.count() == 1
    assert [cid for cid, _ in store.query([1.0, 0, 0, 0], k=5)] == [2]


def test_cosine_is_normalized_not_dot_product(store) -> None:
    """长度不同的同向向量，余弦都该是 1——不能因为没归一化就分出高低。"""
    store.upsert([1, 2], [[1.0, 0, 0, 0], [10.0, 0, 0, 0]])
    results = store.query([1.0, 0, 0, 0], k=2)
    for _, score in results:
        assert score == pytest.approx(1.0)


def test_cache_is_invalidated_on_write(store) -> None:
    """写完之后要能立刻查到新向量——缓存不能把新数据挡住。"""
    assert store.query([1.0, 0, 0, 0], k=1) == []
    store.upsert([1], [[1.0, 0, 0, 0]])
    assert store.query([1.0, 0, 0, 0], k=1)[0][0] == 1


def test_zero_vector_does_not_produce_nan(store) -> None:
    store.upsert([1], [[0.0, 0.0, 0.0, 0.0]])
    results = store.query([1.0, 0, 0, 0], k=1)
    assert not any(np.isnan(score) for _, score in results)


def test_reusable_vector_ids(conn, store) -> None:
    """内容没变的块可以复用旧向量——增量索引时省掉 embed。"""
    store.upsert([1], [[1.0, 0, 0, 0]], text_sha256s=["hash-a"])
    reusable = reusable_vector_ids(conn, model_id="test@4", text_sha256s={1: "hash-a", 2: "hash-b"})
    assert reusable == {1}
