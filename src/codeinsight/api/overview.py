"""项目概览端点（契约 §3.5）。

源文档 §2.1 收尾句「用户不需要逐个打开文件阅读，即可先了解整个项目的
基本构成」的 API 侧落点。**architecture_summary 是模板拼接，但每个数字
都来自索引库**——不调 LLM，不编造。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from codeinsight.api.projects import connect_db, project_counts, require_project

router = APIRouter(tags=["overview"])


@router.get("/projects/{project_id}/overview")
def get_overview(project_id: int) -> dict[str, Any]:
    conn = connect_db(project_id)
    try:
        require_project(conn, project_id)
        project = dict(
            conn.execute(
                "SELECT id, name, root_path FROM project WHERE id = ?", (project_id,)
            ).fetchone()
        )
        counts = project_counts(conn, project_id)

        languages = [
            dict(r)
            for r in conn.execute(
                """
                SELECT language, COUNT(*) AS files, COALESCE(SUM(line_count), 0) AS lines
                FROM file WHERE project_id = ?
                GROUP BY language ORDER BY files DESC
                """,
                (project_id,),
            ).fetchall()
        ]

        entry_points = [
            {
                "kind": r["kind"],
                "target": r["target"],
                "source_path": r["source_path"],
                "doc": r["doc"],
            }
            for r in conn.execute(
                "SELECT kind, target, source_path, doc FROM entry_point WHERE project_id = ? LIMIT 50",
                (project_id,),
            ).fetchall()
        ]

        # 核心模块（最多 20，契约 §3.5）：按模块内符号的调用出度排。
        core_modules = [
            {
                "qualname": r["qualname"],
                "path": r["path"],
                "responsibility": r["responsibility"] or "",
                "docstring": r["docstring"] or "",
                "is_core": bool(r["is_core"]),
                "out_degree": int(r["out_degree"]),
                "in_degree": int(r["in_degree"]),
            }
            for r in conn.execute(
                """
                SELECT m.qualname, m.responsibility, m.docstring, m.is_core, f.path,
                       (SELECT COUNT(*) FROM symbol s JOIN edge e ON e.src_symbol_id = s.id
                          WHERE s.module_id = m.id AND e.kind = 'call') AS out_degree,
                       (SELECT COUNT(*) FROM symbol s JOIN edge e ON e.dst_symbol_id = s.id
                          WHERE s.module_id = m.id AND e.kind = 'call') AS in_degree
                FROM module m JOIN file f ON f.id = m.file_id
                WHERE m.project_id = ?
                ORDER BY out_degree DESC, in_degree DESC
                LIMIT 20
                """,
                (project_id,),
            ).fetchall()
        ]

        dependencies = [
            {
                "name": r["name"],
                "version": r["version"] or "",
                "source": r["source"],
                "declared": bool(r["declared"]),
            }
            for r in conn.execute(
                "SELECT name, version, source, declared FROM dependency "
                "WHERE project_id = ? ORDER BY declared DESC, name LIMIT 200",
                (project_id,),
            ).fetchall()
        ]

        python_files = next(
            (lang["files"] for lang in languages if lang["language"] == "python"), 0
        )
        summary = (
            f"{project['name']}：{counts['files']} 个文件（其中 Python {python_files} 个）、"
            f"{counts['symbols']} 个符号、{counts['edges']} 条关系边。"
            f"核心模块 {len(core_modules)} 个，入口 {len(entry_points)} 处。"
        )

        return {
            "project_id": project_id,
            "architecture_summary": summary,
            "languages": languages,
            "frameworks": [
                d["name"] for d in dependencies if d["declared"] and d["source"] != "import"
            ][:12],
            "entry_points": entry_points,
            "core_modules": core_modules,
            "dependencies": dependencies,
            "stats": {
                "files": counts["files"],
                "python_files": python_files,
                "symbols": counts["symbols"],
                "edges": counts["edges"],
                "concepts": counts["concepts"],
                "flows": _flow_count(conn, project_id),
            },
        }
    finally:
        conn.close()


def _flow_count(conn: Any, project_id: int) -> int:
    return int(
        conn.execute("SELECT COUNT(*) FROM flow WHERE project_id = ?", (project_id,)).fetchone()[0]
    )
