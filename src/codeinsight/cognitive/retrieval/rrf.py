"""Reciprocal Rank Fusion（规格 §1.2 A10）。

移植自织忆 `backend/core/chunk_bm25.py::reciprocal_rank_fusion`
（`ai-companion-agent` @ `agent-v1`，Apache-2.0），
见 `docs/ported-from-tapestry.md`。

**为什么用 RRF 而不是加权求和**：

三路的分数根本不可比——BM25 是负数无下界、余弦相似度在 [-1, 1]、
关系距离是任意刻度。要合并它们，就得先把分数归一化，
而归一化的方式（min-max？z-score？按各路最大值除？）都是**要拍脑袋的权重**——
拍脑袋的权重会直接污染 §5 的对照实验结论。

RRF 只用**排名**不用分数：

    score(d) = Σ_lanes 1 / (k + rank_lane(d))

于是「哪一路更重要」这个问题不存在了——每一路的权重都是 1，
差别只体现在「排第几」。这正是规格里那句
「**不手工加检索策略**——评测的对照组就是这个检索器的可配置版本」。

`k=60` 是文献里的标准值：它让第 1 名和第 2 名的差距很小
（1/61 vs 1/62），排名靠前的少数名次不会因为一路独大而碾压其他路。
"""

from __future__ import annotations

from collections.abc import Iterable

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Iterable[Iterable[tuple[int, float]]],
    *,
    k: int = DEFAULT_RRF_K,
) -> list[tuple[int, float]]:
    """把多路排名合并成一路。

    参数
    ----
    rankings
        每路一个有序的 `(id, score)` 列表，**分数大的在前**。
        分数本身不参与计算——只用排名。
    k
        RRF 常数。默认 60（文献标准值）。

    返回
    ----
    `(id, 融合分数)` 列表，按融合分数降序。
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, (item_id, _score) in enumerate(ranking, start=1):
            fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda kv: -kv[1])
