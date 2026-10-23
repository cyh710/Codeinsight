"""项目与符号端点（契约 §3 / §4）。

读写都走冻结的 `storage/schema.sql`——API 层不定义自己的表结构，
列名即契约。所有响应字段名与 `frontend/src/api/types.ts` 一一对应
（snake_case，不做 camelCase 转换，契约 §0.6）。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from codeinsight.api.errors import (
    bad_request,
    not_found_project,
    not_found_symbol,
)
from codeinsight.api.indexing import start_indexing, validate_root_path
from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path, ensure_schema, open_sqlite

router = APIRouter(tags=["projects"])


def connect_db(project_id: int) -> sqlite3.Connection:
    """打开索引库；库不存在视作项目不存在（没有项目就没有库）。"""
    path = db_path(settings.data_dir)
    if not path.exists():
        raise not_found_project(project_id)
    conn = open_sqlite(path, row_factory=True)
    return conn


def require_project(conn: sqlite3.Connection, project_id: int) -> None:
    row = conn.execute("SELECT 1 FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise not_found_project(project_id)


# ─── POST /projects ───────────────────────────────────────────


class CreateProjectBody(BaseModel):
    root_path: str
    ref: str | None = None
    name: str | None = None


@router.post("/projects", status_code=202)
def create_project(body: CreateProjectBody, background: BackgroundTasks) -> dict[str, Any]:
    validate_root_path(body.root_path)
    path = db_path(settings.data_dir)
    name = body.name or body.root_path.replace("\\", "/").rstrip("/").split("/")[-1]

    # 首次导入时自举：建目录、建库、上 schema（幂等）。
    ensure_schema(path)
    conn = open_sqlite(path, row_factory=True)
    try:
        # 同名项目重复导入：契约定义为 index_running（409），引导用户换名或等完成。
        dup = conn.execute("SELECT id FROM project WHERE name = ?", (name,)).fetchone()
        if dup is not None:
            raise bad_request(
                f"项目名 {name} 已存在（id={dup['id']}）",
                hint="换个 name，或直接使用已有项目的 id",
            )
        cur = conn.execute(
            "INSERT INTO project (name, root_path) VALUES (?, ?)", (name, body.root_path)
        )
        project_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    # 建索引是异步的（契约 §3.3）：响应 202 后由后台任务推进，
    # 前端轮询 GET /projects/{id} 直到 status !== "indexing"。
    background.add_task(start_indexing, project_id, body.root_path, body.ref)

    return {
        "id": project_id,
        "name": name,
        "root_path": body.root_path,
        "status": "indexing",
        "head_commit": None,
        "head_branch": body.ref,
    }


# ─── GET /projects/{id} ───────────────────────────────────────


@router.get("/projects/{project_id}")
def get_project(project_id: int) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        row = conn.execute(
            """
            SELECT p.id, p.name, p.root_path,
                   rs.head_commit, rs.head_branch, rs.indexed_at, rs.index_epoch
            FROM project p
            LEFT JOIN repo_state rs ON rs.project_id = p.id
            WHERE p.id = ?
            """,
            (project_id,),
        ).fetchone()
        counts = project_counts(conn, project_id)
        return {
            **dict(row),
            "status": _project_status(conn, project_id, dict(row)),
            **counts,
        }
    finally:
        conn.close()


def project_counts(conn: sqlite3.Connection, project_id: int) -> dict[str, int]:
    def one(sql: str) -> int:
        return int(conn.execute(sql, (project_id,)).fetchone()[0])

    return {
        "files": one("SELECT COUNT(*) FROM file WHERE project_id = ?"),
        "symbols": one("SELECT COUNT(*) FROM symbol WHERE project_id = ?"),
        "chunks": one("SELECT COUNT(*) FROM chunk WHERE project_id = ?"),
        "edges": one("SELECT COUNT(*) FROM edge WHERE project_id = ?"),
        "concepts": one(
            "SELECT COUNT(DISTINCT concept_id) FROM concept_instance WHERE project_id = ?"
        ),
        "concept_instances": one("SELECT COUNT(*) FROM concept_instance WHERE project_id = ?"),
    }


def _project_status(conn: sqlite3.Connection, project_id: int, repo: dict[str, Any]) -> str:
    """契约 §3.4 的状态推导：indexing / ready / failed / stale。"""
    run = conn.execute(
        "SELECT ok, finished_at, head_commit FROM index_run "
        "WHERE project_id = ? ORDER BY id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if run is None or run["finished_at"] is None:
        return "indexing"
    if not run["ok"]:
        return "failed"
    # ready 之上还有 stale：索引停在的 commit 与当前 HEAD 不一致。
    head = _current_head(repo["root_path"])
    if head and repo["head_commit"] and head != repo["head_commit"]:
        return "stale"
    return "ready"


def _current_head(root_path: str) -> str | None:
    """尽力取仓库当前 HEAD；取不到（目录被移动/非 git）不影响状态推导。"""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", root_path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


# ─── GET /projects/{id}/files ─────────────────────────────────


@router.get("/projects/{project_id}/files")
def list_files(project_id: int) -> list[dict[str, Any]]:
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT f.path, f.language, f.role, f.content_sha256,
                   COALESCE(f.size_bytes, 0) AS size_bytes,
                   COALESCE(f.line_count, 0) AS line_count,
                   (SELECT COUNT(*) FROM symbol s WHERE s.file_id = f.id) AS symbol_count
            FROM file f
            WHERE f.project_id = ?
            ORDER BY f.path
            """,
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── GET /projects/{id}/symbols ─────────────────────────────────


@router.get("/projects/{project_id}/symbols")
def list_symbols(
    project_id: int,
    q: str | None = None,
    kind: str | None = None,
    path: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 500))  # 契约 §0.4：limit 上限 500
    offset = max(0, offset)
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        where = ["s.project_id = ?"]
        params: list[Any] = [project_id]
        if kind:
            where.append("s.kind = ?")
            params.append(kind)
        if path:
            where.append("f.path LIKE ?")
            params.append(path + "%")  # 目录前缀（契约 §4.1：目录前缀匹配）
        if q:
            where.append("(s.qualname LIKE ? OR s.name LIKE ? OR COALESCE(s.docstring, '') LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        clause = " AND ".join(where)

        total = int(
            conn.execute(
                f"SELECT COUNT(*) FROM symbol s JOIN file f ON f.id = s.file_id WHERE {clause}",
                params,
            ).fetchone()[0]
        )
        rows = conn.execute(
            f"""
            SELECT s.id, s.qualname, s.name, s.kind, f.path AS path, s.lineno, s.end_lineno,
                   s.header, s.docstring, s.n_lines, s.is_async, s.is_private, s.is_dunder,
                   (SELECT COUNT(*) FROM edge e WHERE e.dst_symbol_id = s.id AND e.kind = 'call') AS in_degree,
                   (SELECT COUNT(*) FROM edge e WHERE e.src_symbol_id = s.id AND e.kind = 'call') AS out_degree
            FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE {clause}
            ORDER BY f.path, s.lineno
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        items = [{**dict(r), "concept_ids": _symbol_concepts(conn, r["id"])} for r in rows]
        return {"items": items, "total": total}
    finally:
        conn.close()


def _symbol_concepts(conn: sqlite3.Connection, symbol_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT concept_id FROM concept_instance WHERE symbol_id = ?", (symbol_id,)
    ).fetchall()
    return sorted({r["concept_id"] for r in rows})


# ─── GET /projects/{id}/symbols/{qualname} ─────────────────────


@router.get("/projects/{project_id}/symbols/{qualname}")
def get_symbol(project_id: int, qualname: str) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT s.*, f.path AS path
            FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE s.project_id = ? AND s.qualname = ?
            ORDER BY f.path, s.lineno
            """,
            (project_id, qualname),
        ).fetchall()
        if not rows:
            raise not_found_symbol(qualname)

        row = dict(rows[0])
        detail = {
            "id": row["id"],
            "qualname": row["qualname"],
            "name": row["name"],
            "kind": row["kind"],
            "path": row["path"],
            "lineno": row["lineno"],
            "end_lineno": row["end_lineno"],
            "header": row["header"],
            "docstring": row["docstring"],
            "n_lines": row["n_lines"],
            "is_async": bool(row["is_async"]),
            "is_private": bool(row["is_private"]),
            "is_dunder": bool(row["is_dunder"]),
            "in_degree": _degree(conn, row["id"], "dst"),
            "out_degree": _degree(conn, row["id"], "src"),
            "concept_ids": _symbol_concepts(conn, row["id"]),
            "callers": _relations(conn, row["id"], "callers"),
            "callees": _relations(conn, row["id"], "callees"),
            "references": _relations(conn, row["id"], "references"),
            "source": _symbol_source(conn, row),
        }
        # 同名多义（契约 §4.2）：返回第一处并附 alternatives，由前端提示。
        if len(rows) > 1:
            detail["ambiguous"] = True
            detail["alternatives"] = [
                {"qualname": r["qualname"], "path": r["path"], "lineno": r["lineno"]}
                for r in rows[1:8]
            ]
        return detail
    finally:
        conn.close()


def _degree(conn: sqlite3.Connection, symbol_id: int, side: str) -> int:
    col = "dst_symbol_id" if side == "dst" else "src_symbol_id"
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM edge WHERE {col} = ? AND kind = 'call'", (symbol_id,)
        ).fetchone()[0]
    )


def _relations(conn: sqlite3.Connection, symbol_id: int, which: str) -> list[dict[str, Any]]:
    """调用者/被调者/引用处（契约 §4.2）。confidence < 1 → uncertain。"""
    if which == "callers":
        sql = """
        SELECT e.src_symbol_id AS other_id, e.lineno, e.confidence, e.dst_name
        FROM edge e WHERE e.dst_symbol_id = ? AND e.kind = 'call'
        """
    elif which == "callees":
        sql = """
        SELECT e.dst_symbol_id AS other_id, e.lineno, e.confidence, e.dst_name,
               e.dst_qualname AS other_qualname
        FROM edge e WHERE e.src_symbol_id = ? AND e.kind = 'call'
        """
    else:
        sql = """
        SELECT e.src_symbol_id AS other_id, e.lineno, e.confidence, e.dst_name
        FROM edge e WHERE e.dst_symbol_id = ? AND e.kind = 'references'
        """
    rows = conn.execute(sql, (symbol_id,)).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        r = dict(r)
        other_id = r.pop("other_id")
        other_qualname = r.pop("other_qualname", None)
        if other_id is not None:
            other = conn.execute(
                "SELECT s.qualname, f.path AS path FROM symbol s "
                "JOIN file f ON f.id = s.file_id WHERE s.id = ?",
                (other_id,),
            ).fetchone()
            if other is None:
                continue
            qualname, path = other["qualname"], other["path"]
        elif other_qualname:
            # 目标在仓库外或未解析到符号：用边上的 qualname 保留线索（A3 约定）。
            qualname, path = other_qualname, r.get("dst_name", "")
        else:
            qualname, path = r.get("dst_name", ""), ""
        confidence = float(r["confidence"])
        out.append(
            {
                "qualname": qualname,
                "path": path,
                "lineno": r["lineno"] or 0,
                "confidence": confidence,
                "uncertain": confidence < 1.0,
                "note": "动态调用，静态分析不确定" if confidence < 1.0 else None,
            }
        )
    return out


def _symbol_source(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    """符号源码（带行号前缀，契约 §4.2）：按 ordinal 拼回该符号的全部 chunk。"""
    chunks = conn.execute(
        "SELECT lineno, body FROM chunk WHERE symbol_id = ? ORDER BY ordinal",
        (row["id"],),
    ).fetchall()
    if not chunks:
        # 没有切块数据（切块器未跑或该符号未入块索引）——如实返回空串，
        # 前端的查看器会显示空态，不编造代码。
        return ""
    lines: list[str] = []
    for chunk in chunks:
        for i, line in enumerate(chunk["body"].splitlines()):
            lines.append(f"{chunk['lineno'] + i} | {line}")
    return "\n".join(lines)


# ─── callers / callees（契约 §4.3/§4.4） ───────────────────────


@router.get("/projects/{project_id}/symbols/{qualname}/callers")
def get_callers(project_id: int, qualname: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    return _relation_list(project_id, qualname, "callers", limit, offset)


@router.get("/projects/{project_id}/symbols/{qualname}/callees")
def get_callees(project_id: int, qualname: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    return _relation_list(project_id, qualname, "callees", limit, offset)


def _relation_list(
    project_id: int, qualname: str, which: str, limit: int, offset: int
) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        sym = conn.execute(
            "SELECT s.id FROM symbol s JOIN file f ON f.id = s.file_id "
            "WHERE s.project_id = ? AND s.qualname = ? ORDER BY f.path, s.lineno LIMIT 1",
            (project_id, qualname),
        ).fetchone()
        if sym is None:
            raise not_found_symbol(qualname)
        items = _relations(conn, sym["id"], which)
        total = len(items)
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        return {"items": items[offset : offset + limit], "total": total}
    finally:
        conn.close()
