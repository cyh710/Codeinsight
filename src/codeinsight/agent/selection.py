"""选区只是一组定位信息；实际文字必须从指定版本重读。"""

from __future__ import annotations

import sqlite3
from typing import Any

from codeinsight.cognitive.indexing.source_store import SourceError, read_source
from codeinsight.cognitive.workspace import read_workspace


class SelectionError(ValueError):
    def __init__(self, message: str, status: str = "invalid") -> None:
        super().__init__(message)
        self.status = status


def utf16_slice(text: str, start: int, end: int) -> str:
    """零起点、右开区间；拒绝切碎代理对及空选区。"""
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise SelectionError("选区范围无效，请重新选择。")
    raw = text.encode("utf-16-le")
    if end * 2 > len(raw):
        raise SelectionError("选区超出原文范围，请重新选择。")
    try:
        return raw[start * 2 : end * 2].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise SelectionError("选区不能切断一个字符。") from exc


def code_selection(
    conn: sqlite3.Connection, project_id: int, raw: dict[str, Any], max_bytes: int
) -> str:
    """在当前项目的索引快照验证行列；不接受客户端预览文字作为源码。"""
    if not isinstance(raw.get("path"), str) or not raw["path"].strip():
        raise SelectionError("代码选区需要有效文件路径。")
    selection = raw.get("selection")
    if not isinstance(selection, dict):
        raise SelectionError("代码选区格式无效。")
    if raw.get("source_kind") == "workspace":
        if not raw.get("content_sha256"):
            raise SelectionError("工作区选区缺少内容版本，请重新打开文件。", "stale")
        try:
            blob = read_workspace(conn, project_id, raw["path"], raw["content_sha256"]).raw
        except SourceError as exc:
            raise SelectionError(str(exc), "stale") from exc
    else:
        blob = _indexed_selection(conn, project_id, raw)
    return _slice_selection(blob, raw, selection, max_bytes)


def _indexed_selection(conn: sqlite3.Connection, project_id: int, raw: dict) -> bytes:
    row = conn.execute(
        "SELECT f.content_sha256,p.root_path,r.head_commit FROM file f JOIN project p ON p.id=f.project_id "
        "JOIN repo_state r ON r.project_id=p.id WHERE f.project_id=? AND f.path=?",
        (project_id, raw.get("path")),
    ).fetchone()
    if row is None:
        raise SelectionError("选中的代码不在当前项目索引中。", "not_found")
    if (
        raw.get("head_commit") != row["head_commit"]
        or raw.get("content_sha256") != row["content_sha256"]
    ):
        raise SelectionError("代码版本已更新，请重新打开后选择。", "stale")
    if raw.get("index_epoch") is not None:
        epoch = conn.execute(
            "SELECT index_epoch FROM repo_state WHERE project_id=?", (project_id,)
        ).fetchone()
        if epoch is None or epoch[0] != raw["index_epoch"]:
            raise SelectionError("选区来自旧索引，请打开当前版本后重新选择。", "stale")
    try:
        blob = read_source(conn, project_id, raw["path"], expected_sha=raw["content_sha256"]).raw
    except SourceError as exc:
        raise SelectionError(
            str(exc), "stale" if exc.code == "stale_source" else "not_found"
        ) from exc
    return blob


def _slice_selection(blob: bytes, raw: dict, selection: dict, max_bytes: int) -> str:
    lines = blob.decode("utf-8", "replace").splitlines()
    start, end = raw.get("lineno"), raw.get("end_lineno")
    if (
        type(start) is not int
        or type(end) is not int
        or start < 1
        or end < start
        or end > len(lines)
    ):
        raise SelectionError("代码行号范围无效。")
    selected = "\n".join(lines[start - 1 : end])
    first, last = selection.get("start_column"), selection.get("end_column")
    if type(first) is not int or type(last) is not int or first < 1 or last < 1:
        raise SelectionError("代码列号无效。")
    prefix = len(lines[start - 1].encode("utf-16-le")) // 2
    suffix = len(lines[end - 1].encode("utf-16-le")) // 2
    if first > prefix + 1 or last > suffix + 1:
        raise SelectionError("代码列号超出原文。")
    stop = len(selected.encode("utf-16-le")) // 2 - suffix + last - 1
    result = utf16_slice(selected, first - 1, stop)
    if len(result.encode("utf-8")) > max_bytes:
        raise SelectionError("选中代码超出上下文预算，请缩小范围。", "outside_budget")
    return result
