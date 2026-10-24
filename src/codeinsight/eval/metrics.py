"""评测指标与置信区间（源文档 §6）。

只有一个原则：**报数字必须带样本量和区间**。
10 道题上 MRR 差 0.1 只相当于名次挪一格，不写 CI 就等于把噪声当结论。

区间用 bootstrap（有放回重采样）：检索题是「每道题的排名」这种
不服从正态分布的小样本，t 区间不合适；bootstrap 不假设分布。
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

DEFAULT_RESAMPLES = 2000
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Estimate:
    """一个点估计 + 区间。"""

    value: float
    low: float
    high: float
    n: int

    def format(self, *, digits: int = 3, as_percent: bool = False) -> str:
        if as_percent:
            return (
                f"{self.value:.0%} [{self.low:.0%}, {self.high:.0%}]"
                f"（n={self.n}）"
            )
        return f"{self.value:.{digits}f} [{self.low:.{digits}f}, {self.high:.{digits}f}]（n={self.n}）"


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def bootstrap_ci(
    values: Sequence[float],
    *,
    statistic: Callable[[Sequence[float]], float] = mean,
    resamples: int = DEFAULT_RESAMPLES,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = 7,
) -> Estimate:
    """百分位 bootstrap 区间。

    样本少于 2 个时区间退化成点估计——**明确承认**这一点，
    而不是给出一个看起来精确的假区间。
    """
    n = len(values)
    if n == 0:
        return Estimate(0.0, 0.0, 0.0, 0)
    point = statistic(values)
    if n < 2:
        return Estimate(point, point, point, n)

    rng = random.Random(seed)
    samples = sorted(
        statistic([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)
    )
    tail = (1.0 - confidence) / 2.0
    low = samples[int(tail * (resamples - 1))]
    high = samples[int((1.0 - tail) * (resamples - 1))]
    return Estimate(point, low, high, n)


def hit_rate(ranks: Sequence[int | None], *, k: int) -> float:
    """前 k 名里命中过没有。"""
    if not ranks:
        return 0.0
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


def mrr(ranks: Sequence[int | None]) -> float:
    """Mean Reciprocal Rank。没命中记 0。"""
    if not ranks:
        return 0.0
    return sum(1.0 / rank for rank in ranks if rank) / len(ranks)


def top1_rate(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1 for rank in ranks if rank == 1) / len(ranks)


def summarize_ranks(ranks: Sequence[int | None], *, k: int, seed: int = 7) -> dict[str, Estimate]:
    """一套指标 + 区间。三种指标的统计对象不同，各自 bootstrap。"""
    return {
        "hit_rate": bootstrap_ci(
            [1.0 if rank is not None and rank <= k else 0.0 for rank in ranks], seed=seed
        ),
        "mrr": bootstrap_ci(
            [1.0 / rank if rank else 0.0 for rank in ranks], seed=seed
        ),
        "top1_rate": bootstrap_ci([1.0 if rank == 1 else 0.0 for rank in ranks], seed=seed),
    }
