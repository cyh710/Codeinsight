"""探索建议的规范化与索引校验；不会执行模型或客户端提供的命令。"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict
from typing import Any


def version(conn: sqlite3.Connection, project_id: int) -> dict:
    """版本同时包含提交及 epoch，无 Git 目录也能可靠失效。"""
    row = conn.execute(
        "SELECT head_commit,index_epoch FROM repo_state WHERE project_id=?", (project_id,)
    ).fetchone()
    return {
        "project_id": project_id,
        "head_commit": row[0] if row else None,
        "index_epoch": row[1] if row else 0,
    }


def code_target(conn: sqlite3.Connection, pid: int, raw: dict) -> dict | None:
    """仅返回同一项目索引里的真实文件/符号范围，不读取客户端预览。"""
    if not isinstance(raw, dict):
        return None
    if raw.get("project_id", pid) != pid:
        return None
    path, line, name = raw.get("path"), raw.get("lineno", 1), raw.get("qualname")
    if name is not None and not isinstance(name, str):
        return None
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        return None
    if name:
        row = conn.execute(
            "SELECT f.path,s.lineno FROM symbol s JOIN file f ON f.id=s.file_id "
            "WHERE s.project_id=? AND s.qualname=? AND (? IS NULL OR f.path=?)",
            (pid, name, path, path),
        ).fetchone()
        if not row:
            return None
        path, line = row
    if not isinstance(path, str) or path.startswith(("/", "\\")) or ".." in path.split("/"):
        return None
    row = conn.execute(
        "SELECT line_count,content_sha256 FROM file WHERE project_id=? AND path=?", (pid, path)
    ).fetchone()
    if not row or line > max(1, row[0] or 0):
        return None
    if ("head_commit" in raw and raw["head_commit"] != version(conn, pid)["head_commit"]) or (
        "content_sha256" in raw and raw["content_sha256"] != row[1]
    ):
        return None
    symbol = conn.execute(
        "SELECT id,qualname FROM symbol WHERE project_id=? AND file_id IN "
        "(SELECT id FROM file WHERE project_id=? AND path=?) "
        "AND lineno<=? AND end_lineno>=? ORDER BY lineno DESC LIMIT 1",
        (pid, pid, path, line, line),
    ).fetchone()
    return {
        "kind": "code",
        "project_id": pid,
        "path": path,
        "lineno": line,
        "end_lineno": min(
            max(
                line,
                raw.get("end_lineno", line) if type(raw.get("end_lineno", line)) is int else line,
            ),
            line + 199,
            max(1, row[0]),
        ),
        "qualname": symbol[1] if symbol else None,
        "head_commit": version(conn, pid)["head_commit"],
        "content_sha256": row[1],
    }


def target(conn: sqlite3.Connection, pid: int, raw: Any, learning: Any = None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("kind", "code") == "code":
        return code_target(conn, pid, raw)
    if raw.get("kind") == "knowledge" and learning is not None:
        item = learning.library.target(raw.get("topic_id"), raw.get("section_id"))
        if item is not None and raw.get("version", item.version) == item.version:
            return {"kind": "knowledge", **asdict(item), "href": item.href}
    return None


def normalize(conn: sqlite3.Connection, pid: int, raw: Any, learning: Any = None) -> dict:
    """附加内容独立降级；未知对象和不成立的边不会污染正常回答。"""
    result = {**version(conn, pid), "takeaways": [], "actions": [], "flow": None}
    if not isinstance(raw, dict):
        return result
    result["takeaways"] = (
        [s.strip()[:240] for s in raw.get("takeaways", [])[:12] if isinstance(s, str) and s.strip()]
        if isinstance(raw.get("takeaways"), list)
        else []
    )
    actions = raw.get("actions", [])
    for action in actions[:12] if isinstance(actions, list) else []:
        if not isinstance(action, dict):
            continue
        kind = action.get("kind")
        if not isinstance(kind, str) or kind not in {
            "follow_up",
            "code",
            "knowledge",
            "graph",
            "timeline",
        }:
            continue
        label = action.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        resolved = target(conn, pid, action.get("target"), learning)
        question = action.get("question", "")
        if kind == "follow_up":
            if not isinstance(question, str) or not question.strip():
                continue
            if action.get("target") is not None and resolved is None:
                continue
        elif kind in {"code", "graph"} and (not resolved or resolved["kind"] != "code"):
            continue
        elif kind == "graph" and not resolved.get("qualname"):
            continue
        elif kind == "knowledge" and (not resolved or resolved["kind"] != "knowledge"):
            continue
        elif kind == "timeline":
            if not conn.execute(
                "SELECT 1 FROM index_run WHERE project_id=? LIMIT 1", (pid,)
            ).fetchone():
                continue
            resolved = None
        clean = {
            "kind": kind,
            "label": label.strip()[:80],
            "reason": str(action.get("reason") or "")[:180],
            "target": resolved,
            "question": question.strip()[:1000] if kind == "follow_up" else "",
        }
        clean["id"] = hashlib.sha256(
            json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        if clean["id"] not in {a["id"] for a in result["actions"]}:
            result["actions"].append(clean)
        if len(result["actions"]) == 3:
            break
    flow = raw.get("flow")
    if isinstance(flow, dict):
        nodes = {}
        for node in flow.get("nodes", [])[:8] if isinstance(flow.get("nodes"), list) else []:
            if not isinstance(node, dict) or not isinstance(node.get("id"), str):
                continue
            resolved = code_target(conn, pid, node.get("target", {}))
            if resolved:
                nodes[node["id"]] = {
                    "id": node["id"],
                    "label": str(node.get("label") or resolved["qualname"] or resolved["path"])[
                        :80
                    ],
                    "role": str(node.get("role") or "")[:220],
                    "target": resolved,
                }
        edges = []
        for edge in flow.get("edges", [])[:16] if isinstance(flow.get("edges"), list) else []:
            if not isinstance(edge, dict):
                continue
            if not isinstance(edge.get("source"), str) or not isinstance(edge.get("target"), str):
                continue
            a, b = nodes.get(edge.get("source")), nodes.get(edge.get("target"))
            if not a or not b:
                continue
            row = conn.execute(
                "SELECT e.kind,e.confidence FROM edge e JOIN symbol s ON s.id=e.src_symbol_id "
                "JOIN symbol d ON d.id=e.dst_symbol_id JOIN file sf ON sf.id=s.file_id "
                "JOIN file df ON df.id=d.file_id WHERE e.project_id=? AND s.qualname=? "
                "AND d.qualname=? AND sf.path=? AND df.path=? AND e.kind IN ('call','imports','inherits') LIMIT 1",
                (
                    pid,
                    a["target"]["qualname"],
                    b["target"]["qualname"],
                    a["target"]["path"],
                    b["target"]["path"],
                ),
            ).fetchone()
            if row:
                edges.append(
                    {"source": a["id"], "target": b["id"], "kind": row[0], "uncertain": row[1] < 1}
                )
            else:
                contains = conn.execute(
                    "SELECT 1 FROM symbol s JOIN symbol p ON (s.parent_symbol_id=p.id OR (p.kind='module' AND p.file_id=s.file_id)) "
                    "JOIN file pf ON pf.id=p.file_id JOIN file sf ON sf.id=s.file_id "
                    "WHERE s.project_id=? AND p.project_id=? AND p.qualname=? AND s.qualname=? "
                    "AND pf.path=? AND sf.path=?",
                    (
                        pid,
                        pid,
                        a["target"]["qualname"],
                        b["target"]["qualname"],
                        a["target"]["path"],
                        b["target"]["path"],
                    ),
                ).fetchone()
                if contains:
                    edges.append(
                        {
                            "source": a["id"],
                            "target": b["id"],
                            "kind": "contains",
                            "uncertain": False,
                        }
                    )
        connected = {e[k] for e in edges for k in ("source", "target")}
        if edges:
            result["flow"] = {
                "title": str(flow.get("title") or "与当前问题有关的静态关系")[:100],
                "nodes": [n for n in nodes.values() if n["id"] in connected],
                "edges": edges,
            }
    return result


def plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"\s+", " ", re.sub(r"[*`#]", "", text)).strip()
