"""BM25 关键词通道（规格 §1.2 A10）。

**FTS5 的查询构造是这个通道的全部难点。**

裸词查询是 **AND** 语义：`MATCH 'jwt 认证 实现'` 要求同时命中三个词，
几乎必然空集。所以查询必须显式写成 OR：

    "jwt" OR "认证" OR "实现"

排序交给 `bm25()`——它的 **IDF** 天然做区分度：代码库里到处都有的
「实现」权重自动低，稀有的 `jwt` 自动高。所以「OR 召回 + IDF 排序」
就是 Lucene/ES 的 `match` 查询语义。

另外给标识符加一条**短语子句**：用户打 `prepare_chat_stream`，
`token_text` 里这几个词是连续的，短语匹配能精确命中；
拆开匹配的 `prepare` + `stream` 会误伤别的符号。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from codeinsight.cognitive.retrieval.tokenizer import identifier_phrases, split_identifiers

STOPWORDS: frozenset[str] = frozenset(
    {
        # 英文
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "as",
        "by",
        "from",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "we",
        "you",
        "he",
        "she",
        "they",
        "do",
        "does",
        "did",
        "can",
        "could",
        "should",
        "would",
        "will",
        "shall",
        "may",
        "might",
        "how",
        "what",
        "which",
        "when",
        "where",
        "why",
        "who",
        "there",
        "here",
        # 中文提问词（jieba 装好之后按**词**给，bigram 残留一并留着）
        "在哪",
        "哪实",
        "哪里",
        "怎么",
        "如何",
        "什么",
        "哪些",
        "是否",
        "为什",
        "可以",
        "需要",
        "这个",
        "那个",
        "一个",
        # 中文泛用词：它们不携带「这个东西是什么」的信息。
        # 留着会让「X 在哪实现」里的「实现」去匹配每一个讲实现的摘要——
        # 概念通道尤其吃亏（实测会把毫不相关的概念拉进来）。
        "实现",
        "使用",
        "用的",
        "方式",
        "方法",
        "作用",
        "项目",
        "代码",
        "时候",
    }
)
"""停用词。

大部分区分度靠 IDF 就够了，但英文虚词在 docstring 里到处都是，
留着只会稀释候选集。中文那边因为是 bigram，词表只能给到提问词这一层。
"""


@dataclass
class QueryPlan:
    """一次查询的构造结果。"""

    match: str
    """FTS5 的 MATCH 表达式（OR 组合，可含短语子句）。"""

    tokens: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.match


def plan_query(
    query: str,
    *,
    use_stopwords: bool = True,
    use_phrases: bool = True,
) -> QueryPlan:
    """把自然语言查询构造成 FTS5 的 MATCH 表达式。

    参数
    ----
    use_stopwords
        去掉停用词。
    use_phrases
        给标识符加短语子句（`prepare_chat_stream` → `"prepare chat stream"`）。
    """
    tokens = split_identifiers(query)
    if use_stopwords:
        tokens = [t for t in tokens if t.lower() not in STOPWORDS]

    # 同一个 token 只出现一次（OR 语义下重复没有意义）。
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token.lower() in seen:
            continue
        seen.add(token.lower())
        unique.append(token)

    phrases: list[str] = []
    if use_phrases:
        for phrase in identifier_phrases(query):
            if phrase not in phrases:
                phrases.append(phrase)

    clauses = [f'"{token}"' for token in unique]
    clauses += [f'"{phrase}"' for phrase in phrases]
    return QueryPlan(match=" OR ".join(clauses), tokens=unique, phrases=phrases)


class Fts5KeywordIndex:
    """SQLite FTS5 的 BM25 关键词通道。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: int,
        use_stopwords: bool = True,
        use_phrases: bool = True,
    ) -> None:
        self._conn = conn
        self._project_id = project_id
        self._use_stopwords = use_stopwords
        self._use_phrases = use_phrases

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        """返回 `(chunk_id, score)`，分数降序，最多 k 条。

        `bm25()` 返回的是**负数**（越小越相关），这里取反转成「越大越好」，
        与 `KeywordIndex` Protocol 的约定一致。
        """
        if k <= 0:
            return []
        plan = plan_query(
            query,
            use_stopwords=self._use_stopwords,
            use_phrases=self._use_phrases,
        )
        if plan.is_empty:
            return []

        # **CROSS JOIN 是性能关键，不是风格选择。**
        # 写成普通 JOIN 时 SQLite 会把 `c` 放在外层（project_id 有索引），
        # 然后对 6400 行 chunk 逐行去探 FTS——查询计划里 `SCAN chunk_fts … =M1`
        # 就是那个逐行探针，实测 2–5 秒/次（评测跑 300 次直接卡住）。
        # CROSS JOIN 禁止规划器重排，强制 FTS 先出候选集，再按主键回表：
        # 计划变成 `SCAN chunk_fts … M1` + `SEARCH c USING INTEGER PRIMARY KEY`，约 5 毫秒。
        rows = self._conn.execute(
            """
            SELECT chunk_fts.rowid AS chunk_id, bm25(chunk_fts) AS score
            FROM chunk_fts
            CROSS JOIN chunk c ON c.id = chunk_fts.rowid
            WHERE chunk_fts MATCH ? AND c.project_id = ?
            ORDER BY score
            LIMIT ?
            """,
            (plan.match, self._project_id, k),
        ).fetchall()
        return [(int(row[0]), -float(row[1])) for row in rows]

    def delete(self, ids: list[int]) -> None:
        """删除若干条目（增量索引时用）。

        FTS5 是 external content 表，`chunk` 删掉时触发器会同步倒排——
        所以这里删的是 `chunk` 表，不是虚表。
        """
        if not ids:
            return
        self._conn.executemany(
            "DELETE FROM chunk WHERE id = ? AND project_id = ?",
            [(int(i), self._project_id) for i in ids],
        )
        self._conn.commit()

    def explain(self, query: str) -> QueryPlan:
        """看一眼查询是怎么被构造的（调试与测试用）。"""
        return plan_query(
            query,
            use_stopwords=self._use_stopwords,
            use_phrases=self._use_phrases,
        )
