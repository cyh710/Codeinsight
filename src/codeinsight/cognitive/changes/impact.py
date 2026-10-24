"""影响范围：反向可达（源文档 §2.2-5 / §2.5-7）。

「改这个函数会影响谁」= 从被改的符号出发，沿**调用 / 引用 / 继承 / 装饰**
边走反向边。`imports` 不算：模块级的 import 边覆盖面太广，
扩进来会把「同一个包里的东西」全算成受影响。

两个必须处理的边界：

- **删掉的符号**：它的入边会随 CASCADE 一起消失，事后再查就查不到了。
  所以调用方要在删除**之前**把它的调用者快照下来，作为额外的种子传进来。
- **深度**：默认 3 跳。再远就不是「影响」，是「同一个项目」。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

IMPACT_KINDS = ("call", "references", "inherits", "decorator")
DEFAULT_DEPTH = 3
MAX_IMPACT = 200


@dataclass
class Impact:
    symbols: list[dict] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    concept_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "modules": self.modules,
            "symbols": self.symbols,
            "concept_ids": self.concept_ids,
        }


def reverse_impact(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    seed_symbol_ids: list[int],
    seed_qualnames: list[str] = (),
    max_depth: int = DEFAULT_DEPTH,
    limit: int = MAX_IMPACT,
) -> Impact:
    """从改动符号出发反向 BFS。

    `seed_qualnames` 用来接住「已经删掉的符号的调用者」——
    它们的边指向的 id 不在了，但调用者本身仍然存在、仍然受影响。
    """
    seen: set[int] = set(seed_symbol_ids)
    frontier = list(dict.fromkeys(seed_symbol_ids))
    impacted: list[int] = []

    for _ in range(max_depth):
        if not frontier or len(impacted) >= limit:
            break
        placeholders = ",".join("?" for _ in frontier)
        rows = conn.execute(
            f"""
            SELECT DISTINCT e.src_symbol_id
            FROM edge e
            WHERE e.project_id = ? AND e.dst_symbol_id IN ({placeholders})
              AND e.kind IN ({",".join("?" for _ in IMPACT_KINDS)})
            """,
            (project_id, *frontier, *IMPACT_KINDS),
        ).fetchall()
        next_frontier: list[int] = []
        for (src_id,) in rows:
            src_id = int(src_id)
            if src_id in seen:
                continue
            seen.add(src_id)
            impacted.append(src_id)
            next_frontier.append(src_id)
        frontier = next_frontier

    extra: list[int] = []
    if seed_qualnames:
        marks = ",".join("?" for _ in seed_qualnames)
        rows = conn.execute(
            f"SELECT id FROM symbol WHERE project_id = ? AND qualname IN ({marks})",
            (project_id, *seed_qualnames),
        ).fetchall()
        extra = [int(row[0]) for row in rows if int(row[0]) not in seen]
        impacted.extend(extra)

    all_ids = impacted + extra
    if not all_ids:
        return Impact()

    marks = ",".join("?" for _ in all_ids)
    rows = conn.execute(
        f"""
        SELECT s.qualname, f.path, s.lineno, s.id
        FROM symbol s JOIN file f ON f.id = s.file_id
        WHERE s.id IN ({marks})
        ORDER BY f.path, s.lineno LIMIT ?
        """,
        (*all_ids, limit),
    ).fetchall()
    symbols = [{"qualname": row[0], "path": row[1], "lineno": int(row[2])} for row in rows]
    modules = sorted(
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT m.qualname
            FROM module m JOIN symbol s ON s.file_id = m.file_id
            WHERE m.project_id = ? AND s.id IN ({marks})
            """,
            (project_id, *all_ids),
        ).fetchall()
    )
    concept_ids = sorted(
        row[0]
        for row in conn.execute(
            f"SELECT DISTINCT concept_id FROM concept_instance"
            f" WHERE project_id = ? AND symbol_id IN ({marks})",
            (project_id, *all_ids),
        ).fetchall()
    )
    return Impact(symbols=symbols, modules=modules, concept_ids=concept_ids)


def callers_of_qualnames(
    conn: sqlite3.Connection, *, project_id: int, qualnames: list[str]
) -> list[str]:
    """删除/改写**之前**快照这些符号的调用者（qualname），用于算影响范围。"""
    if not qualnames:
        return []
    marks = ",".join("?" for _ in qualnames)
    rows = conn.execute(
        f"""
        SELECT DISTINCT src.qualname
        FROM edge e JOIN symbol src ON src.id = e.src_symbol_id
        WHERE e.project_id = ? AND e.kind IN ('call', 'references')
          AND (e.dst_qualname IN ({marks}) OR e.dst_symbol_id IN
               (SELECT id FROM symbol WHERE project_id = ? AND qualname IN ({marks})))
        """,
        (project_id, *qualnames, project_id, *qualnames),
    ).fetchall()
    return [row[0] for row in rows if row[0]]
