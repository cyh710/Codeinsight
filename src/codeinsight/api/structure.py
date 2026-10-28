"""结构探索端点：关系图（契约 §4.5）与演进时间线（契约 §7.2）。

两条端点都**只读库**，不重新分析代码：

- 关系图是 `edge` 表的一次 BFS。深度、边类型、节点上限都是显式参数；
  一旦因为上限截断，`truncated` 必须为 true——图看起来完整、
  实际缺了一半，比明确说「截断了」更糟。
- 时间线把 `index_run` / `change_record` / `staleness_report` 拼成一条时间轴。
  每一格都是索引当时写下的数字，读侧不重算（重算必然与写侧漂移）。

节点带上 `concept_ids`：源文档 §2.2 的例子是「选中登录接口 → 展示它涉及的
身份验证 / 数据库访问 / Token 处理」，那三个词是**概念**，不是符号。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

from fastapi import APIRouter

from codeinsight.api.errors import bad_request, not_found_symbol
from codeinsight.api.projects import connect_db, require_project
from codeinsight.cognitive.source_targets import attach_targets, begin_read

router = APIRouter(tags=["structure"])

#: 关系图默认展示的边。`imports` 是模块级边，会把图变成一团线，默认关掉；
#: 需要时前端可以显式请求。
GRAPH_EDGE_KINDS: tuple[str, ...] = ("call", "inherits", "decorator", "references")

MAX_DEPTH = 3
MAX_NODES = 200
DEFAULT_NODES = 80
_SQL_CHUNK = 400


# ─── GET /projects/{id}/graph ─────────────────────────────────


@router.get("/projects/{project_id}/graph")
def get_graph(
    project_id: int,
    qualname: str | None = None,
    depth: int = 2,
    max_nodes: int = DEFAULT_NODES,
    kinds: str | None = None,
) -> dict[str, Any]:
    """以某个符号为中心的邻域图；不给 `qualname` 时返回高连接度的概览图。"""
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        edge_kinds = _parse_kinds(kinds)
        if not edge_kinds:
            raise bad_request("至少要保留一种边类型", hint=f"可选：{', '.join(GRAPH_EDGE_KINDS)}")
        if not 1 <= depth <= MAX_DEPTH:
            raise bad_request(f"depth 必须在 1..{MAX_DEPTH}", hint="更大范围请分次探索")
        max_nodes = max(1, min(max_nodes, MAX_NODES))
        return build_graph(
            conn,
            project_id,
            qualname=qualname,
            depth=depth,
            max_nodes=max_nodes,
            kinds=edge_kinds,
        )
    finally:
        conn.close()


def build_graph(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    qualname: str | None = None,
    depth: int = 2,
    max_nodes: int = DEFAULT_NODES,
    kinds: Sequence[str] = GRAPH_EDGE_KINDS,
) -> dict[str, Any]:
    begin_read(conn)
    kinds = tuple(kinds)
    kind_sql = _placeholders(len(kinds))
    edge_params = [project_id, *kinds]

    center: dict[str, Any] | None = None
    if qualname:
        row = conn.execute(
            """
            SELECT s.id, s.qualname, f.path AS path, s.lineno
            FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE s.project_id = ? AND s.qualname = ?
            ORDER BY f.path, s.lineno LIMIT 1
            """,
            (project_id, qualname),
        ).fetchone()
        if row is None:
            raise not_found_symbol(qualname)
        center = {"qualname": row[1], "path": row[2], "lineno": row[3]}
        selected, distances, candidates, truncated = _bfs(
            conn, project_id, row[0], depth, max_nodes, kinds, kind_sql, edge_params
        )
    else:
        selected, distances, candidates, truncated = _overview(
            conn, project_id, max_nodes, kinds, kind_sql, edge_params
        )

    nodes = _load_nodes(conn, selected, distances)
    edges = _filter_edges(candidates, set(selected))
    return attach_targets(
        conn,
        project_id,
        {
            "mode": "focus" if center else "overview",
            "center": center,
            "depth": depth if center else None,
            "kinds": list(kinds),
            "nodes": nodes,
            "edges": edges,
            "truncated": truncated,
        },
    )


def _bfs(
    conn: sqlite3.Connection,
    project_id: int,
    center_id: int,
    depth: int,
    max_nodes: int,
    kinds: Sequence[str],
    kind_sql: str,
    edge_params: list[Any],
) -> tuple[list[int], dict[int, int], dict[tuple[int, int, str, int], dict[str, Any]], bool]:
    distances: dict[int, int] = {center_id: 0}
    selected = [center_id]
    frontier = [center_id]
    candidates: dict[tuple[int, int, str, int], dict[str, Any]] = {}
    truncated = False

    for _level in range(depth):
        next_frontier: list[int] = []
        for ids in _chunks(frontier):
            ph = _placeholders(len(ids))
            rows = conn.execute(
                f"""
                SELECT e.src_symbol_id, e.dst_symbol_id, e.kind, e.lineno, e.confidence
                FROM edge e
                WHERE e.project_id = ? AND e.kind IN ({kind_sql})
                  AND e.dst_symbol_id IS NOT NULL
                  AND (e.src_symbol_id IN ({ph}) OR e.dst_symbol_id IN ({ph}))
                ORDER BY e.id
                """,
                [*edge_params, *ids, *ids],
            ).fetchall()
            for src, dst, kind, lineno, confidence in rows:
                candidates.setdefault(
                    (src, dst, kind, lineno or 0),
                    {
                        "src": src,
                        "dst": dst,
                        "kind": kind,
                        "lineno": lineno,
                        "confidence": float(confidence),
                    },
                )
                new, known = _unvisited_endpoint(src, dst, distances)
                if new is None:
                    continue
                if len(selected) >= max_nodes:
                    truncated = True
                    continue
                distances[new] = distances[known] + 1
                selected.append(new)
                next_frontier.append(new)
        frontier = next_frontier
        if not frontier:
            break
    return selected, distances, candidates, truncated


def _unvisited_endpoint(src: int, dst: int, distances: dict[int, int]) -> tuple[int | None, int]:
    """一条边里「尚未访问的那一端」；两端都访问过或是同一个节点则没有。"""
    if src == dst:
        return None, src
    if src in distances and dst not in distances:
        return dst, src
    if dst in distances and src not in distances:
        return src, dst
    return None, src


def _overview(
    conn: sqlite3.Connection,
    project_id: int,
    max_nodes: int,
    kinds: Sequence[str],
    kind_sql: str,
    edge_params: list[Any],
) -> tuple[list[int], dict[int, int | None], dict[tuple[int, int, str, int], dict[str, Any]], bool]:
    """没有中心符号时的概览：取调用度数最高的公开函数/类，再连出它们之间的边。"""
    where = "s.project_id = ? AND s.kind IN ('function', 'method', 'class') AND s.is_private = 0"
    total = int(
        conn.execute(f"SELECT COUNT(*) FROM symbol s WHERE {where}", (project_id,)).fetchone()[0]
    )
    rows = conn.execute(
        f"""
        SELECT s.id
        FROM symbol s
        WHERE {where}
        ORDER BY (
            (SELECT COUNT(*) FROM edge e WHERE e.src_symbol_id = s.id AND e.kind = 'call') +
            (SELECT COUNT(*) FROM edge e WHERE e.dst_symbol_id = s.id AND e.kind = 'call')
        ) DESC, s.qualname
        LIMIT ?
        """,
        (project_id, max_nodes),
    ).fetchall()
    selected = [int(r[0]) for r in rows]
    distances: dict[int, int | None] = {sid: None for sid in selected}
    candidates: dict[tuple[int, int, str, int], dict[str, Any]] = {}
    if not selected:
        return selected, distances, candidates, False
    selected_set = set(selected)
    for ids in _chunks(selected):
        ph = _placeholders(len(ids))
        rows = conn.execute(
            f"""
            SELECT e.src_symbol_id, e.dst_symbol_id, e.kind, e.lineno, e.confidence
            FROM edge e
            WHERE e.project_id = ? AND e.kind IN ({kind_sql})
              AND e.dst_symbol_id IS NOT NULL AND e.src_symbol_id IN ({ph})
            ORDER BY e.id
            """,
            [*edge_params, *ids],
        ).fetchall()
        for src, dst, kind, lineno, confidence in rows:
            if dst not in selected_set:
                continue
            candidates.setdefault(
                (src, dst, kind, lineno or 0),
                {
                    "src": src,
                    "dst": dst,
                    "kind": kind,
                    "lineno": lineno,
                    "confidence": float(confidence),
                },
            )
    return selected, distances, candidates, total > len(selected)


def _load_nodes(
    conn: sqlite3.Connection, selected: Iterable[int], distances: dict[int, int | None]
) -> list[dict[str, Any]]:
    ids = list(selected)
    order = {sid: i for i, sid in enumerate(ids)}
    by_id: dict[int, dict[str, Any]] = {}
    for chunk in _chunks(ids):
        ph = _placeholders(len(chunk))
        for row in conn.execute(
            f"""
            SELECT s.id, s.qualname, s.name, s.kind, f.path AS path, s.lineno,
                   s.end_lineno, s.is_async, s.is_private
            FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE s.id IN ({ph})
            """,
            chunk,
        ).fetchall():
            by_id[int(row[0])] = {
                "id": int(row[0]),
                "qualname": row[1],
                "name": row[2],
                "kind": row[3],
                "path": row[4],
                "lineno": row[5],
                "end_lineno": row[6],
                "is_async": bool(row[7]),
                "is_private": bool(row[8]),
                "in_degree": 0,
                "out_degree": 0,
                "concept_ids": [],
                "depth": distances.get(int(row[0])),
            }

    concepts = _concepts_of(conn, ids)
    in_degree = _degree_map(conn, ids, "dst_symbol_id")
    out_degree = _degree_map(conn, ids, "src_symbol_id")
    nodes: list[dict[str, Any]] = []
    for sid in ids:
        node = by_id.get(sid)
        if node is None:  # 符号在两次查询之间被删了（增量索引并发）
            continue
        node["concept_ids"] = concepts.get(sid, [])
        node["in_degree"] = in_degree.get(sid, 0)
        node["out_degree"] = out_degree.get(sid, 0)
        nodes.append(node)
    # `order` 让「中心节点恒在第一位」，前端可以据此选初始视口；
    # dict 插入顺序本身已是发现顺序，这里保留显式排序以防查询实现变化。
    nodes.sort(key=lambda n: order.get(n["id"], len(order)))
    return nodes


def _concepts_of(conn: sqlite3.Connection, ids: Sequence[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for chunk in _chunks(ids):
        ph = _placeholders(len(chunk))
        for symbol_id, concept_id in conn.execute(
            f"SELECT DISTINCT symbol_id, concept_id FROM concept_instance"
            f" WHERE symbol_id IN ({ph}) ORDER BY concept_id",
            chunk,
        ).fetchall():
            out.setdefault(int(symbol_id), []).append(concept_id)
    return out


def _degree_map(conn: sqlite3.Connection, ids: Sequence[int], column: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for chunk in _chunks(ids):
        ph = _placeholders(len(chunk))
        for symbol_id, count in conn.execute(
            f"SELECT {column}, COUNT(*) FROM edge WHERE kind = 'call'"
            f" AND {column} IN ({ph}) GROUP BY {column}",
            chunk,
        ).fetchall():
            out[int(symbol_id)] = int(count)
    return out


def _filter_edges(
    candidates: dict[tuple[int, int, str, int], dict[str, Any]], selected: set[int]
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for item in candidates.values():
        if item["src"] not in selected or item["dst"] not in selected:
            continue
        key = (item["src"], item["dst"], item["kind"])
        if key in seen:  # 同一个调用点只留一条
            continue
        seen.add(key)
        edges.append(
            {
                **item,
                "uncertain": item["confidence"] < 1.0,
            }
        )
    edges.sort(key=lambda e: (e["src"], e["dst"], e["kind"]))
    return edges


def _parse_kinds(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return GRAPH_EDGE_KINDS
    requested = tuple(part.strip() for part in raw.split(",") if part.strip())
    unknown = [k for k in requested if k not in GRAPH_EDGE_KINDS]
    if unknown:
        raise bad_request(
            f"未知的边类型：{', '.join(unknown)}",
            hint=f"可选：{', '.join(GRAPH_EDGE_KINDS)}",
        )
    return requested


# ─── GET /projects/{id}/timeline ──────────────────────────────


@router.get("/projects/{project_id}/timeline")
def get_timeline(project_id: int, limit: int = 30) -> dict[str, Any]:
    """索引与变更的时间轴，从新到旧。"""
    limit = max(1, min(limit, 100))
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        return build_timeline(conn, project_id, limit=limit)
    finally:
        conn.close()


def build_timeline(conn: sqlite3.Connection, project_id: int, *, limit: int = 30) -> dict[str, Any]:
    head_row = conn.execute(
        "SELECT head_commit FROM repo_state WHERE project_id = ?", (project_id,)
    ).fetchone()
    head = head_row[0] if head_row else None

    items: list[tuple[tuple[str, int, int], dict[str, Any]]] = []
    used_change_ids: set[int] = set()
    runs = conn.execute(
        """
        SELECT id, base_commit, head_commit, mode, started_at, finished_at, ok,
               files_total, files_changed, symbols_added, symbols_removed, stats_json
        FROM index_run WHERE project_id = ? ORDER BY id DESC LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    for run in runs:
        run_id, base, commit, mode, started_at, finished_at, ok, files_total, files_changed = run[
            :9
        ]
        symbols_added, symbols_removed, stats_raw = run[9], run[10], run[11]
        change = conn.execute(
            """
            SELECT id, summary, occurred_at, source, added_json, removed_json, modified_json
            FROM change_record WHERE project_id = ? AND commit_sha = ?
            ORDER BY id DESC LIMIT 1
            """,
            (project_id, commit),
        ).fetchone()
        summary = ""
        added = modified = deleted = None
        symbols_changed = None
        source = None
        at = finished_at or started_at
        if change is not None:
            change_id, summary, occurred_at, source, added_raw, removed_raw, modified_raw = change
            used_change_ids.add(int(change_id))
            at = occurred_at or at
            added = _record_count(added_raw, files=True)
            modified = _record_count(modified_raw, files=True)
            deleted = _record_count(removed_raw, files=True)
            symbols_changed = (
                _record_count(added_raw) + _record_count(removed_raw) + _record_count(modified_raw)
            )
        stats = _json(stats_raw, {})
        if symbols_changed is None and isinstance(stats, dict):
            value = stats.get("changed_symbols")
            symbols_changed = int(value) if isinstance(value, int) else None
        total = (
            (added or 0) + (modified or 0) + (deleted or 0)
            if added is not None
            else (files_changed if files_changed is not None else files_total)
        )
        if not summary:
            if mode == "incremental":
                summary = f"增量索引：{total if total is not None else 0} 个文件变化"
            else:
                summary = (
                    f"全量索引：{files_total if files_total is not None else 0} 个文件、"
                    f"{symbols_added if symbols_added is not None else 0} 个符号"
                )
        item = {
            "id": f"run-{run_id}",
            "kind": "index",
            "mode": mode,
            "ok": bool(ok),
            "at": _iso(at),
            "base_commit": base,
            "head_commit": commit,
            "summary": summary,
            "files": {
                "added": added,
                "modified": modified,
                "deleted": deleted,
                "total": total if total is not None else 0,
            },
            "symbols_changed": symbols_changed,
            "symbols_added": symbols_added,
            "symbols_removed": symbols_removed,
            "files_total": files_total,
            "source": source,
            "stale_design_decisions": _stale_decisions(conn, project_id, commit),
        }
        items.append(((item["at"] or "", 1, int(run_id)), item))

    # 没有对应 index_run 的变更记录（例如 MCP 侧外部 agent 记账）也要出现在时间线上。
    for row in conn.execute(
        """
        SELECT id, commit_sha, source, summary, occurred_at,
               added_json, removed_json, modified_json
        FROM change_record WHERE project_id = ? ORDER BY id DESC LIMIT ?
        """,
        (project_id, limit),
    ).fetchall():
        record_id, commit, source, summary, occurred_at = row[:5]
        if int(record_id) in used_change_ids:
            continue
        added_raw, removed_raw, modified_raw = row[5], row[6], row[7]
        added = _record_count(added_raw, files=True)
        modified = _record_count(modified_raw, files=True)
        deleted = _record_count(removed_raw, files=True)
        item = {
            "id": f"change-{record_id}",
            "kind": "change",
            "mode": None,
            "ok": True,
            "at": _iso(occurred_at),
            "base_commit": None,
            "head_commit": commit,
            "summary": summary or "外部变更记录",
            "files": {
                "added": added,
                "modified": modified,
                "deleted": deleted,
                "total": (added or 0) + (modified or 0) + (deleted or 0),
            },
            "symbols_changed": (
                _record_count(added_raw) + _record_count(removed_raw) + _record_count(modified_raw)
            ),
            "symbols_added": None,
            "symbols_removed": None,
            "files_total": None,
            "source": source,
            "stale_design_decisions": _stale_decisions(conn, project_id, commit),
        }
        items.append(((item["at"] or "", 0, int(record_id)), item))

    items.sort(key=lambda pair: pair[0], reverse=True)
    return {"items": [item for _, item in items[:limit]], "total": len(items), "head": head}


def _stale_decisions(
    conn: sqlite3.Connection, project_id: int, commit_sha: str | None
) -> list[dict[str, Any]]:
    if not commit_sha:
        return []
    row = conn.execute(
        "SELECT by_reason FROM staleness_report WHERE project_id = ? AND commit_sha = ?"
        " ORDER BY id DESC LIMIT 1",
        (project_id, commit_sha),
    ).fetchone()
    if row is None:
        return []
    payload = _json(row[0], {})
    decisions = payload.get("design_decisions") if isinstance(payload, dict) else None
    if not isinstance(decisions, list):
        return []
    return [
        {"doc_id": str(d.get("doc_id", "")), "title": str(d.get("title", ""))}
        for d in decisions
        if isinstance(d, dict)
    ]


def _record_count(raw: str | None, *, files: bool = False) -> int:
    """change_record 的 *_json 存的是 `{"files": [...], "symbols": [...]}`。

    早期写法是裸路径列表（见 `changes/service.py`），两种都认。
    """
    payload = _json(raw, [])
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        key = "files" if files else "symbols"
        value = payload.get(key, [])
        return len(value) if isinstance(value, list) else 0
    return 0


def _json(raw: Any, fallback: Any) -> Any:
    if raw in (None, ""):
        return fallback
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _iso(raw: Any) -> str | None:
    """统一成 ISO-8601 UTC；SQLite 的 `datetime('now')` 用空格分隔，补上 T/Z。"""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # 早期版本误把 time.monotonic() 写进 started_at；这类数字不是时间，
    # 宁可这条时间线没有时间戳，也不能显示一个假日期。
    try:
        float(text)
    except ValueError:
        pass
    else:
        return None
    if "T" in text:
        return text if text.endswith("Z") or "+" in text[10:] else f"{text}Z"
    return text.replace(" ", "T") + "Z"


def _chunks(items: Sequence[int], size: int = _SQL_CHUNK) -> list[list[int]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _placeholders(n: int) -> str:
    return ",".join("?" * n)
