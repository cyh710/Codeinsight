"""检索层接口。

源文档 §5-2「结构化代码检索与关系增强」：把语义检索与 AST、符号定位、代码关系分析结合。

本文件只放**两种可替换的索引后端**的接口：
- `KeywordIndex` —— 关键词通道（当前实现 = SQLite FTS5 内置 bm25()）
- `VectorStore`  —— 稠密通道（当前实现 = SQLite BLOB + numpy 暴力余弦）

两者都只返回 `(id, score)`，**融合与排序不在这里做**——那是 `retriever` 的职责，
这样换后端时融合逻辑完全不受影响。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class KeywordIndex(Protocol):
    """关键词索引。"""

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        """返回 `(chunk_id, score)`，按分数降序，最多 k 条。无命中返回空列表。"""
        ...

    def delete(self, ids: Sequence[int]) -> None:
        """删除若干条目（增量索引时用）。"""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """稠密向量索引。"""

    def upsert(self, ids: Sequence[int], vectors: Sequence[Sequence[float]]) -> None:
        """写入或覆盖若干向量。"""
        ...

    def query(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        """返回 `(chunk_id, cosine_similarity)`，按相似度降序，最多 k 条。"""
        ...

    def delete(self, ids: Sequence[int]) -> None:
        """删除若干向量。"""
        ...
