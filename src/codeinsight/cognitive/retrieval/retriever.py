"""检索器（规格 §1.2 A11）。

把多路检索合成一份证据列表。**同一套代码，不同的通道开关 = 评测的不同臂**：

| 臂 | 开的通道 |
|---|---|
| `none` | 全关（基线） |
| `bm25` | BM25 |
| `hybrid` | BM25 + 稠密 |
| `symbol` | BM25 + 符号关系 |
| `concept` | BM25 + 概念 |

这正是规格里那句「**不手工加检索策略**——评测的对照组就是这个检索器的
可配置版本」：臂与臂之间唯一的差别是开关，没有需要拍脑袋的权重。

输出 `Evidence`（`models.py`）：每条都能落到 `file:line`，
并且记着它是**哪几路**捞到的——报告里能说清「这条证据来自符号图，
不是关键词碰巧命中」。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from codeinsight.cognitive.retrieval.bm25 import Fts5KeywordIndex
from codeinsight.cognitive.retrieval.rrf import DEFAULT_RRF_K, reciprocal_rank_fusion
from codeinsight.cognitive.retrieval.symbol_lane import SymbolRelationLane
from codeinsight.models import Evidence

LANE_BM25 = "bm25"
LANE_DENSE = "dense"
LANE_SYMBOL = "symbol"
LANE_CONCEPT = "concept"
LANE_NEIGHBOR = "neighbor"

ALL_LANES = frozenset({LANE_BM25, LANE_DENSE, LANE_SYMBOL, LANE_CONCEPT})

SNIPPET_MAX_CHARS = 400


@dataclass
class RetrievalConfig:
    """检索器的可调项。

    每一个都是**评测的旋钮**——不是拍脑袋定的，是用来做对照的。
    """

    lanes: frozenset[str] = field(default_factory=lambda: frozenset({LANE_BM25, LANE_SYMBOL}))
    top_k: int = 8
    rrf_k: int = DEFAULT_RRF_K
    neighbor_depth: int = 1
    neighbor_discount: float = 0.5
    """邻域扩展的折扣：扩展来的证据分数乘这个系数。"""
    lane_k: int = 40
    """每路各自取多少条候选进融合（比 top_k 大，融合后再截断）。"""


class Retriever:
    """多路检索器。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        embedder=None,
        config: RetrievalConfig | None = None,
        db_path: str | Path = ":memory:",
    ) -> None:
        self._conn = conn
        self._embedder = embedder
        self._config = config or RetrievalConfig()
        self._db_path = str(db_path)

    def with_connection(self, conn: sqlite3.Connection) -> Retriever:
        """沿用检索配置，在调用者的读取事务内查询，不共享连接生命周期。"""
        return Retriever(conn, embedder=self._embedder, config=self._config, db_path=self._db_path)

    # ── 主入口 ──────────────────────────────────────────────

    def retrieve(self, query: str, k: int | None = None, *, project_id: int) -> list[Evidence]:
        """检索并返回证据列表。

        参数
        ----
        query
            用户查询。
        k
            返回多少条（缺省用 `config.top_k`）。
        project_id
            限定在哪个项目里检索。
        """
        top_k = k or self._config.top_k
        if top_k <= 0 or not query.strip():
            return []

        lane_results = self._run_lanes(query, project_id=project_id)
        if not lane_results:
            return []

        fused = reciprocal_rank_fusion(lane_results.values(), k=self._config.rrf_k)
        if not fused:
            return []

        lanes_of = self._lanes_by_chunk(lane_results)
        expanded = self._expand_neighbors(
            fused[:top_k],
            lanes_of=lanes_of,
            project_id=project_id,
        )

        merged: dict[int, float] = {}
        for chunk_id, score in fused:
            merged[chunk_id] = merged.get(chunk_id, 0.0) + score
        for chunk_id, score in expanded:
            merged[chunk_id] = merged.get(chunk_id, 0.0) + score

        ordered = sorted(merged.items(), key=lambda kv: -kv[1])[:top_k]
        return self._to_evidence(ordered, lanes_of=lanes_of, project_id=project_id)

    # ── 各路 ────────────────────────────────────────────────

    def _run_lanes(self, query: str, *, project_id: int) -> dict[str, list[tuple[int, float]]]:
        lanes = self._config.lanes
        results: dict[str, list[tuple[int, float]]] = {}

        if LANE_BM25 in lanes:
            index = Fts5KeywordIndex(self._conn, project_id=project_id)
            results[LANE_BM25] = index.search(query, k=self._config.lane_k)

        if LANE_SYMBOL in lanes:
            lane = SymbolRelationLane(self._conn, project_id=project_id)
            results[LANE_SYMBOL] = lane.search(query, k=self._config.lane_k)

        if LANE_DENSE in lanes and self._embedder is not None:
            results[LANE_DENSE] = self._dense_lane(query, project_id=project_id)

        if LANE_CONCEPT in lanes:
            from codeinsight.cognitive.retrieval.concept_lane import ConceptLane

            lane = ConceptLane(self._conn, project_id=project_id)
            results[LANE_CONCEPT] = lane.search(query, k=self._config.lane_k)

        return {name: hits for name, hits in results.items() if hits}

    def _dense_lane(self, query: str, *, project_id: int) -> list[tuple[int, float]]:
        """稠密通道。

        向量库是**全局**的（不按项目分），所以要多取一些再按项目过滤。
        """
        from codeinsight.cognitive.retrieval.dense import SqliteVectorStore

        vectors = self._embedder.encode([query])
        if not vectors:
            return []
        epoch_row = self._conn.execute(
            "SELECT index_epoch FROM repo_state WHERE project_id = ?", (project_id,)
        ).fetchone()
        store = SqliteVectorStore(
            self._conn,
            model_id=self._embedder.model_id,
            db_path=self._db_path,
            index_epoch=int(epoch_row[0]) if epoch_row else 0,
        )
        candidates = store.query(vectors[0], k=self._config.lane_k * 4)
        if not candidates:
            return []

        chunk_ids = [chunk_id for chunk_id, _ in candidates]
        placeholders = ",".join("?" for _ in chunk_ids)
        allowed = {
            int(row[0])
            for row in self._conn.execute(
                f"SELECT id FROM chunk WHERE project_id = ? AND id IN ({placeholders})",
                (project_id, *chunk_ids),
            )
        }
        return [(cid, score) for cid, score in candidates if cid in allowed][: self._config.lane_k]

    # ── 邻域扩展 ────────────────────────────────────────────

    def _expand_neighbors(
        self,
        top: list[tuple[int, float]],
        *,
        lanes_of: dict[int, set[str]],
        project_id: int,
    ) -> list[tuple[int, float]]:
        """沿调用边扩展邻居，分数打折。

        为什么默认只扩一层：扩两层会把「相关」稀释成「同一个模块里的东西」。
        深度是可调的（`neighbor_depth`），评测时拿它做旋钮。

        扩展来的证据分数 = **来源块分数 × 折扣**（每多跳一层再打一次折），
        所以它一定排在来源块后面，但不会掉到垫底。
        """
        if self._config.neighbor_depth <= 0 or not top:
            return []

        out: dict[int, float] = {}
        for chunk_id, score in top:
            symbol_id = self._symbol_id_of(chunk_id, project_id=project_id)
            if symbol_id is None:
                continue
            for neighbor_symbol, depth in self._neighbors(
                symbol_id, project_id=project_id, depth=self._config.neighbor_depth
            ):
                neighbor_chunk = self._chunk_of(neighbor_symbol, project_id=project_id)
                if neighbor_chunk is None or neighbor_chunk in lanes_of:
                    continue
                discounted = score * (self._config.neighbor_discount**depth)
                if discounted > out.get(neighbor_chunk, 0.0):
                    out[neighbor_chunk] = discounted
        return sorted(out.items(), key=lambda kv: -kv[1])

    def _symbol_id_of(self, chunk_id: int, *, project_id: int) -> int | None:
        row = self._conn.execute(
            "SELECT symbol_id FROM chunk WHERE id = ? AND project_id = ?",
            (chunk_id, project_id),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _chunk_of(self, symbol_id: int, *, project_id: int) -> int | None:
        """符号 → 它第一块的 id。"""
        row = self._conn.execute(
            """
            SELECT MIN(id) FROM chunk
            WHERE project_id = ? AND symbol_id = ? AND ordinal = 0
            """,
            (project_id, symbol_id),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _neighbors(self, symbol_id: int, *, project_id: int, depth: int) -> list[tuple[int, int]]:
        """BFS 找邻居符号，返回 [(symbol_id, 距离)]。

        走 `call` 边（调用关系最有信息量）；`imports`/`inherits` 覆盖太广，
        扩进来会把结果稀释成「同一个包里的东西」。
        """
        seen = {symbol_id}
        frontier = [symbol_id]
        out: list[tuple[int, int]] = []

        for level in range(1, depth + 1):
            if not frontier:
                break
            placeholders = ",".join("?" for _ in frontier)
            rows = self._conn.execute(
                f"""
                SELECT DISTINCT dst_symbol_id FROM edge
                WHERE project_id = ? AND src_symbol_id IN ({placeholders})
                  AND dst_symbol_id IS NOT NULL AND kind = 'call'
                """,
                (project_id, *frontier),
            ).fetchall()
            rows += self._conn.execute(
                f"""
                SELECT DISTINCT src_symbol_id FROM edge
                WHERE project_id = ? AND dst_symbol_id IN ({placeholders})
                  AND src_symbol_id IS NOT NULL AND kind = 'call'
                """,
                (project_id, *frontier),
            ).fetchall()

            next_frontier: list[int] = []
            for row in rows:
                neighbor = int(row[0])
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                next_frontier.append(neighbor)
                out.append((neighbor, level))
            frontier = next_frontier
        return out

    # ── 组装证据 ────────────────────────────────────────────

    def _lanes_by_chunk(
        self, lane_results: dict[str, list[tuple[int, float]]]
    ) -> dict[int, set[str]]:
        lanes_of: dict[int, set[str]] = {}
        for lane, hits in lane_results.items():
            for chunk_id, _ in hits:
                lanes_of.setdefault(chunk_id, set()).add(lane)
        return lanes_of

    def _to_evidence(
        self,
        ordered: list[tuple[int, float]],
        *,
        lanes_of: dict[int, set[str]],
        project_id: int,
    ) -> list[Evidence]:
        if not ordered:
            return []
        chunk_ids = [chunk_id for chunk_id, _ in ordered]
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = self._conn.execute(
            f"""
            SELECT c.id, f.path, c.lineno, c.end_lineno, c.qualname, c.body, c.symbol_id
            FROM chunk c JOIN file f ON f.id = c.file_id
            WHERE c.project_id = ? AND c.id IN ({placeholders})
            """,
            (project_id, *chunk_ids),
        ).fetchall()
        detail = {int(r[0]): r for r in rows}

        concepts = self._concepts_of(
            [int(r[6]) for r in rows if r[6] is not None], project_id=project_id
        )

        out: list[Evidence] = []
        for chunk_id, score in ordered:
            row = detail.get(chunk_id)
            if row is None:
                continue
            lanes = set(lanes_of.get(chunk_id, set()))
            if chunk_id not in lanes_of:
                lanes.add(LANE_NEIGHBOR)
            out.append(
                Evidence(
                    chunk_id=chunk_id,
                    path=row[1],
                    lineno=int(row[2]),
                    end_lineno=int(row[3]),
                    qualname=row[4],
                    snippet=_snippet(row[5]),
                    score=score,
                    lanes=tuple(sorted(lanes)),
                    concept_ids=concepts.get(int(row[6]) if row[6] is not None else -1, ()),
                )
            )
        return out

    def _concepts_of(self, symbol_ids: list[int], *, project_id: int) -> dict[int, tuple[str, ...]]:
        if not symbol_ids:
            return {}
        placeholders = ",".join("?" for _ in symbol_ids)
        rows = self._conn.execute(
            f"""
            SELECT DISTINCT symbol_id, concept_id FROM concept_instance
            WHERE project_id = ? AND symbol_id IN ({placeholders})
            """,
            (project_id, *symbol_ids),
        ).fetchall()
        # `DISTINCT` 是必须的：同一个符号可能在同一概念上被多条规则命中
        # （`import jwt` 与 `call jwt.decode` 各一条实例），不去重的话
        # 前端会渲染出重复的概念标签，React 还会报重复 key。
        out: dict[int, list[str]] = {}
        for symbol_id, concept_id in rows:
            out.setdefault(int(symbol_id), []).append(concept_id)
        return {k: tuple(sorted(v)) for k, v in out.items()}


def _snippet(body: str | None, *, limit: int = SNIPPET_MAX_CHARS) -> str:
    """块的摘录——给模型看的那一小段。"""
    if not body:
        return ""
    text = body.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …"
