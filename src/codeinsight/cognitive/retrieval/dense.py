"""稠密向量索引（规格 §1.2 A8 / ADR 0002）。

**SQLite BLOB + numpy 暴力余弦**，不引入向量数据库。

理由：块量级 1e3–1e5，暴力余弦在这个量级是**毫秒级**（numpy 一次矩阵乘）。
换 ChromaDB / Qdrant 要多一个原生依赖、多一套部署，
换来的性能提升在单机场景里用不上——而这个项目的重点不是检索引擎，
是「结构化代码检索 + 关系增强」这件事本身。

几个实现要点：

- 向量写入前**归一化**，于是点积就是余弦（省掉每次查询的除法）。
- 查询把该 `model_id` 的全部向量拉成 ndarray 算一次矩阵乘——
  缓存按 `(db, model_id, index_epoch)` 键，`index_epoch` 一变缓存自然失效，
  不用手动清。
- `text_sha256` 存在向量行上：内容没变就能**复用旧向量**，增量索引时
  只有真正变了的块要重新 embed。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import numpy as np

# (db_key, model_id, index_epoch) → (chunk_ids, matrix)
_CACHE: dict[tuple[str, str, int], tuple[np.ndarray, np.ndarray]] = {}

_CACHE_LIMIT = 8
"""缓存最多留几份。epoch 一变就多一份，不设上限会一直涨。"""


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """按行归一化（L2）。零向量保持为零，不产生 NaN。"""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class SqliteVectorStore:
    """向量存储。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        model_id: str,
        db_path: str | Path = ":memory:",
        index_epoch: int = 0,
    ) -> None:
        self._conn = conn
        self._model_id = model_id
        self._db_path = str(db_path)
        self._epoch = index_epoch
        # 内存库的每个连接都是**不同的库**，不能用路径做缓存键——
        # 否则两个 `:memory:` 库会共用一份缓存，查到别人的向量
        # （而且 CPython 会复用已回收对象的 id，这个坑很隐蔽）。
        # 内存库就用实例私有的缓存；文件库用进程级共享缓存。
        self._shared = self._db_path != ":memory:"
        self._cache = _CACHE if self._shared else {}

    @property
    def _cache_key(self) -> tuple[str, str, int]:
        """缓存键。

        文件库用解析后的绝对路径（同一个文件的不同写法要命中同一份缓存）；
        `index_epoch` 一变键就变，缓存自然失效——不用手动清。
        """
        if self._shared:
            db_key = str(Path(self._db_path).resolve())
        else:
            db_key = ":memory:"
        return (db_key, self._model_id, self._epoch)

    # ── 写入 ────────────────────────────────────────────────

    def upsert(
        self,
        ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
        text_sha256s: Sequence[str] | None = None,
    ) -> int:
        """写入或覆盖向量，返回写入条数。

        `text_sha256s` 是被 embed 文本的哈希——内容没变时可以据此判断
        「这个块已经有向量了」，增量索引时省掉一次 embed。
        """
        if not ids:
            return 0
        if len(ids) != len(vectors):
            raise ValueError("ids 与 vectors 长度不一致")

        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2:
            raise ValueError("向量必须是二维数组")
        matrix = _normalize(matrix)

        hashes = list(text_sha256s) if text_sha256s else [""] * len(ids)
        for chunk_id, vec, digest in zip(ids, matrix, hashes, strict=True):
            self._conn.execute(
                """
                INSERT INTO embedding (chunk_id, model_id, vec, text_sha256)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chunk_id, model_id) DO UPDATE SET
                    vec = excluded.vec,
                    text_sha256 = excluded.text_sha256
                """,
                (int(chunk_id), self._model_id, vec.astype("<f4").tobytes(), digest),
            )
        self._conn.commit()
        self._invalidate()
        return len(ids)

    def delete(self, ids: Sequence[int]) -> None:
        """删除向量。"""
        if not ids:
            return
        self._conn.executemany(
            "DELETE FROM embedding WHERE chunk_id = ? AND model_id = ?",
            [(int(i), self._model_id) for i in ids],
        )
        self._conn.commit()
        self._invalidate()

    # ── 查询 ────────────────────────────────────────────────

    def query(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        """返回 `(chunk_id, cosine_similarity)`，按相似度降序，最多 k 条。"""
        if k <= 0:
            return []
        chunk_ids, matrix = self._load()
        if matrix.size == 0:
            return []

        query = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if query.shape[1] != matrix.shape[1]:
            raise ValueError(f"查询向量维度 {query.shape[1]} 与索引维度 {matrix.shape[1]} 不一致")
        query = _normalize(query)

        scores = (matrix @ query.T).ravel()
        top = np.argsort(-scores)[:k]
        return [(int(chunk_ids[i]), float(scores[i])) for i in top]

    def count(self) -> int:
        """这个 model_id 下有多少条向量。"""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM embedding WHERE model_id = ?",
            (self._model_id,),
        ).fetchone()
        return int(row[0])

    # ── 内部 ────────────────────────────────────────────────

    def _invalidate(self) -> None:
        """当前 model_id / epoch 的缓存作废。"""
        self._cache.pop(self._cache_key, None)

    def _load(self) -> tuple[np.ndarray, np.ndarray]:
        """加载全部向量（带缓存）。"""
        key = self._cache_key
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        rows = self._conn.execute(
            "SELECT chunk_id, vec FROM embedding WHERE model_id = ? ORDER BY chunk_id",
            (self._model_id,),
        ).fetchall()
        if not rows:
            empty = (np.empty(0, dtype=np.int64), np.empty((0, 0), dtype=np.float32))
            self._cache[key] = empty
            return empty

        ids = np.asarray([row[0] for row in rows], dtype=np.int64)
        matrix = np.vstack([np.frombuffer(row[1], dtype="<f4") for row in rows]).astype(np.float32)
        if len(self._cache) >= _CACHE_LIMIT:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = (ids, matrix)
        return ids, matrix


def register_model(
    conn: sqlite3.Connection,
    *,
    model_id: str,
    dim: int,
    provider: str = "",
) -> None:
    """登记一个 embedding 模型（换模型插新 model_id，不迁移旧数据）。"""
    conn.execute(
        """
        INSERT INTO embedding_model (model_id, provider, dim, space)
        VALUES (?, ?, ?, 'cosine')
        ON CONFLICT(model_id) DO UPDATE SET
            provider = excluded.provider,
            dim = excluded.dim
        """,
        (model_id, provider, dim),
    )
    conn.commit()


def reusable_vector_ids(
    conn: sqlite3.Connection,
    *,
    model_id: str,
    text_sha256s: dict[int, str],
) -> set[int]:
    """哪些块已经有向量、且内容没变。

    增量索引时用它跳过 embed——「只有变了的块要重新算」。
    """
    if not text_sha256s:
        return set()
    reusable: set[int] = set()
    for chunk_id, digest in text_sha256s.items():
        row = conn.execute(
            "SELECT text_sha256 FROM embedding WHERE chunk_id = ? AND model_id = ?",
            (chunk_id, model_id),
        ).fetchone()
        if row and row[0] == digest:
            reusable.add(chunk_id)
    return reusable
