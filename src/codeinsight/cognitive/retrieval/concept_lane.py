"""概念通道（规格 §1.2 A10 第四路 / B5）。

源文档 §5-4 是个**独立的技术特色**：「项目与技术知识双向关联」。
要证明它有用，就得一臂「关掉概念关联」做对照——
所以概念必须是**一路可开关的检索通道**，而不是回答时临时加的一段话。

分工（B5 写明的）：

- **B 线**提供「概念 → 实例」的查询能力：
  本体的概念存在 `concept` 表，实例存在 `concept_instance` 表。
- **A 线**实现这一路的检索：查询文本 → 匹配出相关概念 → 取实例 → 落到块。

概念匹配用**词重叠**而不是 LLM：
- 确定、可测、可复现；
- 评测时不能引入随机性（否则同一臂跑两次结果不同，CI 和 n 都没意义）。
"""

from __future__ import annotations

import sqlite3

from codeinsight.cognitive.retrieval.bm25 import STOPWORDS
from codeinsight.cognitive.retrieval.tokenizer import split_identifiers

MAX_CONCEPT_CANDIDATES = 8
"""一次查询最多带进几个概念——再多就把「概念」稀释成噪声了。"""


class ConceptLane:
    """概念通道。"""

    def __init__(self, conn: sqlite3.Connection, *, project_id: int) -> None:
        self._conn = conn
        self._project_id = project_id

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        """返回 `(chunk_id, score)`，最多 k 条。"""
        if k <= 0:
            return []
        concepts = self.match_concepts(query)
        if not concepts:
            return []
        return self.instances_of([cid for cid, _ in concepts], k=k)

    def match_concepts(self, query: str) -> list[tuple[str, float]]:
        """查询文本 → 相关概念，按重叠度排序。

        匹配的是概念的 **名字 + 摘要 + 分类**——
        这些是给人看的说法，正好是用户提问里会出现的词。
        """
        query_tokens = {
            token.lower() for token in split_identifiers(query) if token.lower() not in STOPWORDS
        }
        if not query_tokens:
            return []

        rows = self._conn.execute("SELECT id, name, summary, category FROM concept").fetchall()

        scored: list[tuple[str, float]] = []
        for concept_id, name, summary, category in rows:
            text = " ".join(part for part in (name, summary, category) if part)
            concept_tokens = {t.lower() for t in split_identifiers(text)}
            overlap = query_tokens & concept_tokens
            if not overlap:
                continue
            # 用比例而不是绝对值：摘要很长的概念不该仅凭词多就赢。
            score = len(overlap) / max(len(query_tokens), 1)
            scored.append((concept_id, score))

        scored.sort(key=lambda item: -item[1])
        return scored[:MAX_CONCEPT_CANDIDATES]

    def instances_of(self, concept_ids: list[str], *, k: int) -> list[tuple[int, float]]:
        """概念 → 实例 → 块。

        实例带 `confidence`（检测规则的可信度），乘进分数——
        「靠 `import jwt` 认出来的」比「靠模糊匹配认出来的」该更靠前。
        """
        if not concept_ids:
            return []
        placeholders = ",".join("?" for _ in concept_ids)
        rows = self._conn.execute(
            f"""
            SELECT ci.symbol_id, ci.concept_id, ci.confidence
            FROM concept_instance ci
            WHERE ci.project_id = ? AND ci.concept_id IN ({placeholders})
              AND ci.symbol_id IS NOT NULL
            """,
            (self._project_id, *concept_ids),
        ).fetchall()
        if not rows:
            return []

        symbol_ids = sorted({int(r[0]) for r in rows})
        symbol_placeholders = ",".join("?" for _ in symbol_ids)
        chunk_rows = self._conn.execute(
            f"""
            SELECT symbol_id, MIN(id) FROM chunk
            WHERE project_id = ? AND symbol_id IN ({symbol_placeholders}) AND ordinal = 0
            GROUP BY symbol_id
            """,
            (self._project_id, *symbol_ids),
        ).fetchall()
        chunk_of = {int(r[0]): int(r[1]) for r in chunk_rows}

        best: dict[int, float] = {}
        for symbol_id, _concept_id, confidence in rows:
            chunk_id = chunk_of.get(int(symbol_id))
            if chunk_id is None:
                continue
            score = float(confidence)
            if score > best.get(chunk_id, 0.0):
                best[chunk_id] = score

        return sorted(best.items(), key=lambda kv: -kv[1])[:k]
