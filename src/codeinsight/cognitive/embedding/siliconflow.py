"""硅基流动的嵌入实现（OpenAI 兼容接口）。

`BAAI/bge-m3`，1024 维。接口是 OpenAI 兼容的 `/v1/embeddings`，
所以任何 OpenAI 兼容服务都能换——只要改 base_url。

**密钥只从环境变量读**（`CI_EMBEDDING_API_KEY`），不落库、不进日志、
不进索引库。缺 key 时 `enabled` 为 False，稠密通道自动跳过——
而不是报错中断整次检索。
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import httpx

from codeinsight.config import settings

BATCH_SIZE = 32
"""一批多少条。太大上游会拒，太小往返多。"""


class SiliconFlowEmbedder:
    """把文本编码成向量。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.embedding_api_key
        self._base_url = (base_url or settings.embedding_base_url).rstrip("/")
        self._model = model or settings.embedding_model
        self._dim = dim or settings.embedding_dim
        self._timeout = timeout

    @property
    def model_id(self) -> str:
        """向量表的 model_id——含维度，换模型就是换 model_id，不迁移旧数据。"""
        return f"{self._model}@{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """批量编码。

        没有 key 时返回空列表（调用方据此跳过这一路）。
        """
        if not texts:
            return []
        if not self.enabled:
            return []

        out: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[start : start + BATCH_SIZE])
            out.extend(self._encode_batch(batch))
        return out

    def _encode_batch(self, batch: list[str]) -> list[list[float]]:
        payload = {"model": self._model, "input": batch, "encoding_format": "float"}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = httpx.post(
                f"{self._base_url}/embeddings",
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            # 嵌入失败不该让整次检索崩掉——稠密通道只是少一路。
            return []

        items = data.get("data") or []
        vectors: list[list[float]] = []
        for item in items:
            embedding = item.get("embedding")
            if isinstance(embedding, list):
                vectors.append([float(x) for x in embedding])
        return vectors
