"""符号关系通道（规格 §1.2 A10）。

这一路是「**AST 增强**」和「普通 RAG」的分水岭（源文档 §5-2）。

BM25 只能告诉你「哪些文本里有这些词」；符号关系通道告诉你
「**这个符号在哪、被谁调用、调用了谁、跟谁在同一个文件**」。

命中方式：**精确符号名匹配**，不是关键词匹配。
查询里打 `prepare_chat_stream`，就该拿这个**原样**去匹配符号，
而不是拿拆开的 `prepare` / `stream` 去匹配一串叫 prepare 的东西。

展开顺序（也就是排序顺序）：

| 关系 | 距离 | 含义 |
|---|---|---|
| `definition` | 0 | 命中的符号本身 |
| `caller` / `callee` | 1 | 直接调用它 / 它直接调用的 |
| `sibling` | 2 | 同一个文件里的其他符号 |

符号 → 块时只取 `ordinal = 0`（第一块）：一个 1000 行的函数有 10 块，
全塞进结果会把候选集淹掉；需要完整符号时按 `symbol_id` 拼回去。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from codeinsight.cognitive.retrieval.tokenizer import raw_identifiers

# 关系 → 距离（越小越相关）
RELATION_DISTANCE: dict[str, int] = {
    "definition": 0,
    "caller": 1,
    "callee": 1,
    "sibling": 2,
}

# 关系 → 分数（只是给人看的；融合用排名，不用分数）
RELATION_SCORE: dict[str, float] = {
    "definition": 1.0,
    "caller": 0.5,
    "callee": 0.5,
    "sibling": 0.2,
}

MAX_RELATIONS_PER_KIND = 24
"""每种关系最多展开多少个符号——不然一个 hub 函数能把候选集淹掉。"""

MAX_SIBLINGS = 24


@dataclass(frozen=True)
class SymbolHit:
    """一个命中的符号及其关系。"""

    symbol_id: int
    qualname: str
    name: str
    kind: str
    path: str
    lineno: int
    relation: str


class SymbolRelationLane:
    """符号关系通道。"""

    def __init__(self, conn: sqlite3.Connection, *, project_id: int) -> None:
        self._conn = conn
        self._project_id = project_id

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        """返回 `(chunk_id, score)`，按关系距离降序，最多 k 条。"""
        if k <= 0:
            return []
        hits = self.collect(query)
        return self.to_chunks(hits, k=k)

    def collect(self, query: str) -> list[SymbolHit]:
        """找出查询涉及的所有符号及其关系（按关系距离排好）。"""
        seeds = self._match_symbols(query)
        if not seeds:
            return []

        hits: list[SymbolHit] = []
        seen: set[tuple[int, str]] = set()

        def _add(symbol_id: int, relation: str) -> None:
            key = (symbol_id, relation)
            if key in seen:
                return
            seen.add(key)
            row = self._symbol_row(symbol_id)
            if row is None:
                return
            hits.append(
                SymbolHit(
                    symbol_id=symbol_id,
                    qualname=row[0],
                    name=row[1],
                    kind=row[2],
                    path=row[3],
                    lineno=row[4],
                    relation=relation,
                )
            )

        for seed in seeds:
            _add(seed, "definition")
            for caller in self._callers(seed):
                _add(caller, "caller")
            for callee in self._callees(seed):
                _add(callee, "callee")
            for sibling in self._siblings(seed):
                _add(sibling, "sibling")

        hits.sort(key=lambda h: (RELATION_DISTANCE[h.relation], h.qualname))
        return hits

    def to_chunks(self, hits: list[SymbolHit], *, k: int) -> list[tuple[int, float]]:
        """符号命中 → 块命中（只取每个符号的第一块）。"""
        if not hits:
            return []
        ids = [h.symbol_id for h in hits]
        placeholders = ",".join("?" for _ in ids)
        rows = self._conn.execute(
            f"""
            SELECT symbol_id, MIN(id) AS chunk_id
            FROM chunk
            WHERE project_id = ? AND symbol_id IN ({placeholders}) AND ordinal = 0
            GROUP BY symbol_id
            """,
            (self._project_id, *ids),
        ).fetchall()
        chunk_of = {int(r[0]): int(r[1]) for r in rows}

        out: list[tuple[int, float]] = []
        for hit in hits:
            chunk_id = chunk_of.get(hit.symbol_id)
            if chunk_id is None:
                continue
            out.append((chunk_id, RELATION_SCORE[hit.relation]))
            if len(out) >= k:
                break
        return out

    # ── 内部 ────────────────────────────────────────────────

    def _match_symbols(self, query: str) -> list[int]:
        """查询里的标识符 → 符号 id。

        三种匹配：
        - 全限定名精确匹配（`backend.core.x`）
        - 短名精确匹配（`x`）
        - 点号路径的后缀匹配（`core.x` → `backend.core.x`）
        """
        found: list[int] = []
        seen: set[int] = set()
        for identifier in raw_identifiers(query):
            rows = self._conn.execute(
                """
                SELECT id FROM symbol
                WHERE project_id = ? AND (qualname = ? OR name = ? OR qualname LIKE ?)
                ORDER BY LENGTH(qualname), id
                LIMIT 20
                """,
                (
                    self._project_id,
                    identifier,
                    identifier,
                    f"%.{identifier}",
                ),
            ).fetchall()
            for row in rows:
                symbol_id = int(row[0])
                if symbol_id in seen:
                    continue
                seen.add(symbol_id)
                found.append(symbol_id)
        return found

    def _symbol_row(self, symbol_id: int) -> tuple[str, str, str, str, int] | None:
        row = self._conn.execute(
            """
            SELECT s.qualname, s.name, s.kind, f.path, s.lineno
            FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE s.id = ? AND s.project_id = ?
            """,
            (symbol_id, self._project_id),
        ).fetchone()
        return tuple(row) if row else None

    def _callers(self, symbol_id: int) -> list[int]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT src_symbol_id FROM edge
            WHERE project_id = ? AND dst_symbol_id = ? AND kind = 'call'
            LIMIT ?
            """,
            (self._project_id, symbol_id, MAX_RELATIONS_PER_KIND),
        ).fetchall()
        return [int(r[0]) for r in rows]

    def _callees(self, symbol_id: int) -> list[int]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT dst_symbol_id FROM edge
            WHERE project_id = ? AND src_symbol_id = ? AND kind = 'call' AND dst_symbol_id IS NOT NULL
            LIMIT ?
            """,
            (self._project_id, symbol_id, MAX_RELATIONS_PER_KIND),
        ).fetchall()
        return [int(r[0]) for r in rows]

    def _siblings(self, symbol_id: int) -> list[int]:
        """同一个文件里的其他符号。"""
        row = self._conn.execute(
            "SELECT file_id FROM symbol WHERE id = ? AND project_id = ?",
            (symbol_id, self._project_id),
        ).fetchone()
        if not row:
            return []
        rows = self._conn.execute(
            """
            SELECT id FROM symbol
            WHERE project_id = ? AND file_id = ? AND id != ?
            ORDER BY lineno
            LIMIT ?
            """,
            (self._project_id, int(row[0]), symbol_id, MAX_SIBLINGS),
        ).fetchall()
        return [int(r[0]) for r in rows]
