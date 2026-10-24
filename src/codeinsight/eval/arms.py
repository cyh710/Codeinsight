"""对照臂（源文档 §5 / §6）。

**臂与臂之间唯一的差别是通道开关**——没有需要拍脑袋的权重，也没有
「调一调让结果更好看」的参数。这是本项目对 §5 那五个创新点的验证方式：
每个创新点对应一组开关，数字才说明问题。

| 臂 | 通道 | 验证什么 |
|---|---|---|
| `none` | — | 下限：不检索就不可能给出 `file:line` |
| `bm25` | 词面 | 最常见也最强的单路基线 |
| `hybrid` | 词面 + 语义 | 稠密通道到底带来多少增益 |
| `symbol` | 符号关系 | **结构化检索**（AST 索引）相对纯文本检索的增益 |
| `concept` | 概念实例 | 知识层（§2.6）对定位有没有帮助 |
| `full` | 四路全开 | 产品配置，不是对照臂——报告里单独标出来 |
"""

from __future__ import annotations

from dataclasses import dataclass

from codeinsight.cognitive.retrieval.retriever import (
    LANE_BM25,
    LANE_CONCEPT,
    LANE_DENSE,
    LANE_SYMBOL,
)


@dataclass(frozen=True)
class Arm:
    name: str
    lanes: frozenset[str]
    description: str
    control: bool = True
    """`False` = 产品配置，不参与「哪个通道有用」的对照解读。"""

    @property
    def needs_dense(self) -> bool:
        return LANE_DENSE in self.lanes


ARMS: dict[str, Arm] = {
    "none": Arm(
        "none",
        frozenset(),
        "不检索（下限）：普通 LLM 问答没有索引可查",
    ),
    "bm25": Arm(
        "bm25",
        frozenset({LANE_BM25}),
        "词面检索基线",
    ),
    "hybrid": Arm(
        "hybrid",
        frozenset({LANE_BM25, LANE_DENSE}),
        "词面 + 语义（BM25 + bge-m3）",
    ),
    "symbol": Arm(
        "symbol",
        frozenset({LANE_SYMBOL}),
        "符号关系通道（AST 索引）",
    ),
    "concept": Arm(
        "concept",
        frozenset({LANE_CONCEPT}),
        "概念实例通道（知识层）",
    ),
    "full": Arm(
        "full",
        frozenset({LANE_BM25, LANE_DENSE, LANE_SYMBOL, LANE_CONCEPT}),
        "产品配置：四路全开",
        control=False,
    ),
}

DEFAULT_ARMS = ("none", "bm25", "hybrid", "symbol", "concept", "full")


def resolve_arms(names: str | None) -> list[Arm]:
    """`"bm25,hybrid"` → Arm 列表。未知名字直接报错，不静默忽略。"""
    if not names:
        return [ARMS[name] for name in DEFAULT_ARMS]
    picked: list[Arm] = []
    for raw in names.split(","):
        key = raw.strip()
        if not key:
            continue
        if key not in ARMS:
            raise KeyError(f"未知对照臂：{key}（可用：{', '.join(ARMS)}）")
        picked.append(ARMS[key])
    return picked
