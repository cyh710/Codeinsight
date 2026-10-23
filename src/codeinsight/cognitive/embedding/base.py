"""嵌入层接口。

源文档 §3.2「语义检索：Embedding + BM25」。这一层只负责**文本 → 向量**，
不关心向量存哪儿（那是 `VectorStore` 的事），也不关心怎么检索。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """把文本编码成向量。"""

    model_id: str
    """模型标识，含维度，形如 `bge-m3@1024`。换模型即换 model_id。"""

    dim: int
    """向量维度。"""

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """批量编码。

        必须保证**同一模型下顺序与输入一致**、维度恒为 `self.dim`。
        实现方应自行做批量分批，避免一次几千条被上游拒绝。
        """
        ...
