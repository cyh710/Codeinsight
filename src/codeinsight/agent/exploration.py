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
    """由请求内来源、完整快照身份或索引符号定位；不读取客户端预览。"""
    if not isinstance(raw, dict):
        return None
    if raw.get("project_id", pid) != pid:
        return None
    if raw.get("qualname") is not None and not isinstance(raw["qualname"], str):
        return None
    if raw.get("path") is not None and not isinstance(raw["path"], str):
        return None
    if raw.get("qualname") and "lineno" not in raw and "source_ref" not in raw:
        located = conn.execute(
            "SELECT f.path,s.lineno FROM symbol s JOIN file f ON f.id=s.file_id WHERE s.project_id=? AND s.qualname=? AND (? IS NULL OR f.path=?) ORDER BY f.path,s.lineno LIMIT 1",
            (pid, raw["qualname"], raw.get("path"), raw.get("path")),
        ).fetchone()
        if located:
            raw = {**raw, "path": located[0], "lineno": located[1]}
            if not raw.get("source_kind") and not raw.get("content_sha256"):
                from codeinsight.cognitive.source_targets import indexed_target

                indexed = indexed_target(conn, pid, located[0], located[1])
                if indexed:
                    raw = {**raw, **indexed, "qualname": raw["qualname"]}
    from codeinsight.agent.source_scope import CURRENT_SCOPE

    scope = CURRENT_SCOPE.get()
    if scope is None and "source_ref" in raw:
        return None
    if scope is not None:
        resolved = scope.resolve(raw)
        if resolved is not None:
            if raw.get("qualname") and not resolved.get("qualname"):
                row = conn.execute(
                    "SELECT 1 FROM symbol s JOIN file f ON f.id=s.file_id WHERE s.project_id=? AND f.path=? AND f.content_sha256=? AND s.qualname=? AND s.lineno<=? AND s.end_lineno>=?",
                    (
                        pid,
                        resolved["path"],
                        resolved.get("content_sha256"),
                        raw["qualname"],
                        resolved["lineno"],
                        resolved["lineno"],
                    ),
                ).fetchone()
                if row:
                    resolved["qualname"] = raw["qualname"]
            return resolved
        if "source_ref" in raw or (
            not raw.get("content_sha256")
            and any(s.get("path") == raw.get("path") for s in scope.sources.values())
        ):
            return None
    path, line, name = raw.get("path"), raw.get("lineno", 1), raw.get("qualname")
    if name is not None and not isinstance(name, str):
        return None
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        return None
    if raw.get("source_kind") == "workspace":
        from codeinsight.cognitive.indexing.source_store import SourceError
        from codeinsight.cognitive.workspace import read_workspace

        if not isinstance(path, str) or not isinstance(raw.get("content_sha256"), str):
            return None
        try:
            source = read_workspace(conn, pid, path, raw["content_sha256"])
        except (SourceError, OSError):
            return None
        total = len(source.raw.decode("utf-8", "replace").splitlines())
        end = raw.get("end_lineno", line)
        if type(end) is not int or end < line or line > total or end > total:
            return None
        return {
            "kind": "code",
            "project_id": pid,
            "path": path,
            "lineno": line,
            "end_lineno": min(end, line + 199, total),
            "source_kind": "workspace",
            "content_sha256": source.sha256,
            "head_commit": None,
            "qualname": None,
        }
    if raw.get("source_kind") == "index" and raw.get("content_sha256"):
        from codeinsight.cognitive.indexing.source_store import SourceError, read_source

        try:
            source = read_source(
                conn,
                pid,
                path,
                expected_sha=raw["content_sha256"],
                index_epoch=raw.get("index_epoch"),
                head_commit=raw.get("head_commit"),
            )
        except (SourceError, OSError, TypeError):
            return None
        total = len(source.raw.decode("utf-8", "replace").splitlines())
        end = raw.get("end_lineno", line)
        if type(end) is not int or end < line or line > max(1, total) or end > max(1, total):
            return None
        return {
            **raw,
            "kind": "code",
            "project_id": pid,
            "lineno": line,
            "end_lineno": min(end, line + 199, max(1, total)),
        }
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
    end = raw.get("end_lineno", line)
    if type(end) is not int or end < line or end > max(1, row[0] or 0):
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
        "source_kind": "index",
        "index_epoch": version(conn, pid)["index_epoch"],
        "path": path,
        "lineno": line,
        "end_lineno": min(end, line + 199),
        "qualname": symbol[1] if symbol else None,
        "head_commit": version(conn, pid)["head_commit"],
        "content_sha256": row[1],
    }


def target(conn: sqlite3.Connection, pid: int, raw: Any, learning: Any = None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("project_id", pid) != pid:
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
            "dependency": "index"
            if kind in {"graph", "timeline"}
            else "knowledge"
            if resolved and resolved["kind"] == "knowledge"
            else "source"
            if resolved
            else "none",
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
                    "label": str(node.get("label") or resolved.get("qualname") or resolved["path"])[
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
            if not all(
                n["target"].get("qualname") and _current_identity(conn, pid, n["target"])
                for n in (a, b)
            ):
                continue
            row = conn.execute(
                "SELECT e.kind,e.confidence FROM edge e JOIN symbol s ON s.id=e.src_symbol_id "
                "JOIN symbol d ON d.id=e.dst_symbol_id JOIN file sf ON sf.id=s.file_id "
                "JOIN file df ON df.id=d.file_id WHERE e.project_id=? AND s.qualname=? "
                "AND d.qualname=? AND sf.path=? AND df.path=? AND e.kind='call' LIMIT 1",
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
        connected = {e[k] for e in edges for k in ("source", "target")}
        if edges:
            result["flow"] = {
                "title": str(flow.get("title") or "与当前问题有关的静态关系")[:100],
                "nodes": [n for n in nodes.values() if n["id"] in connected],
                "edges": edges,
            }
    return result


def _current_identity(conn: sqlite3.Connection, pid: int, source: dict) -> bool:
    if source.get("source_kind") != "workspace" and any(
        source.get(k) != version(conn, pid)[k] for k in ("index_epoch", "head_commit")
    ):
        return False
    row = conn.execute(
        "SELECT content_sha256 FROM file WHERE project_id=? AND path=?", (pid, source["path"])
    ).fetchone()
    if source.get("content_sha256"):
        return bool(row and row[0] == source["content_sha256"])
    return (
        source.get("index_epoch") == version(conn, pid)["index_epoch"]
        and source.get("head_commit") == version(conn, pid)["head_commit"]
    )


def requires_index(action: dict) -> bool:
    """静态关系与时间线依赖当前索引；不可变源码和教材各自检查版本。"""
    return action.get("kind") in {"graph", "timeline"} or action.get("dependency") == "index"


def plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"\s+", " ", re.sub(r"[*`#]", "", text)).strip()
