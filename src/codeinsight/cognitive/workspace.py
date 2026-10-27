"""有界只读工作区访问；读取资格来自项目根，历史资格来自已登记的内容身份。"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path, PureWindowsPath

from codeinsight.cognitive.indexing.scanner import BINARY_SUFFIXES
from codeinsight.cognitive.indexing.source_store import (
    Source,
    SourceError,
    cache_path,
    store_bytes,
)

MAX_FILE_BYTES = 2_000_000
MAX_ENTRIES = 10000
MAX_SEARCH_BYTES = 8_000_000
SKIP_DIRS = frozenset(
    {
        ".git",
        ".ci",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".zcode",
        ".codex",
    }
)


def allowed(path: str) -> bool:
    """工作区文本不继承 Git 忽略规则，实验结果可读；密钥与缓存始终排除。"""
    parts = path.replace("\\", "/").split("/")
    name = parts[-1].lower()
    return not (
        any(p.lower() in SKIP_DIRS for p in parts)
        or name == ".env"
        or name.startswith(".env.")
        or name in {"id_rsa", "id_ed25519", "credentials", "credentials.json", "secrets.json"}
        or Path(name).suffix in BINARY_SUFFIXES | {".pem", ".key", ".p12", ".pfx", ".lock"}
    )


def resolve(root: str, path: str) -> Path:
    """拒绝绝对路径、越界路径和符号链接，根目录不存在时给可恢复错误。"""
    base = Path(root).resolve()
    relative = path.replace("\\", "/")
    if (
        not path
        or PureWindowsPath(path).drive
        or ":" in relative
        or relative.startswith("/")
        or ".." in relative.split("/")
    ):
        raise SourceError("文件路径不在当前项目内。", "not_found")
    if not allowed(relative):
        raise SourceError("该路径为缓存、二进制或敏感文件，不参与项目阅读。", "not_found")
    target = base / relative
    if not base.is_dir():
        raise SourceError("项目源码目录不可用；历史快照与教材仍可阅读。", "read_failed")
    cursor = base
    for part in relative.split("/"):
        cursor = cursor / part
        if cursor.is_symlink() or cursor.is_junction():
            raise SourceError("不读取符号链接或目录联接。", "not_found")
    if not target.resolve().is_relative_to(base):
        raise SourceError("文件路径不在当前项目内。", "not_found")
    return target


def read_current(root: str, path: str) -> bytes:
    """读取单个有界文本文件，不要求索引或 Git。"""
    target = resolve(root, path)
    try:
        if target.stat().st_size > MAX_FILE_BYTES:
            raise SourceError("文件超过2MB阅读上限，请选择较小的文本结果。", "outside_budget")
        with target.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
    except FileNotFoundError as exc:
        raise SourceError("当前工作区没有这个文件，请浏览目录确认路径。", "not_found") from exc
    except OSError as exc:
        raise SourceError("当前文件无法读取，请确认路径和访问权限。", "read_failed") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise SourceError("文件超过2MB阅读上限，请选择较小的文本结果。", "outside_budget")
    if b"\0" in raw:
        raise SourceError("文件为二进制，无法作为文本读取。", "not_found")
    return raw


def read_workspace(
    conn: sqlite3.Connection, project_id: int, path: str, expected_sha: str | None = None
) -> Source:
    """默认读取磁盘；带哈希只读取该项目/路径已保存的工作区快照。"""
    project = conn.execute("SELECT root_path FROM project WHERE id=?", (project_id,)).fetchone()
    if project is None or not allowed(path):
        raise SourceError("项目或文件不存在。", "not_found")
    if expected_sha:
        row = conn.execute(
            "SELECT 1 FROM file_snapshot WHERE project_id=? AND path=? AND commit_sha=? AND content_sha256=?",
            (project_id, path, "workspace:" + expected_sha, expected_sha),
        ).fetchone()
        if row is None:
            raise SourceError("此工作区快照不属于当前项目和文件。", "not_found")
        target = cache_path(conn, expected_sha)
        try:
            raw = target.read_bytes() if target else read_current(project[0], path)
        except OSError as exc:
            raise SourceError("已保存的工作区快照不可用。", "read_failed") from exc
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise SourceError("工作区快照已损坏，请重新打开当前文件。", "read_failed")
    else:
        raw = read_current(project[0], path)
        try:
            expected_sha = store_bytes(conn, raw)
            conn.execute(
                "INSERT OR IGNORE INTO file_snapshot(project_id,commit_sha,path,content_sha256) VALUES(?,?,?,?)",
                (project_id, "workspace:" + expected_sha, path, expected_sha),
            )
            conn.commit()
        except (OSError, sqlite3.Error) as exc:
            raise SourceError(
                "读取了当前文件，但无法保存对应版本；请检查数据目录权限和空间后重试。",
                "save_failed",
            ) from exc
    return Source(raw, expected_sha, None)


def list_paths(root: str, *, limit: int = 2000, path: str = "") -> tuple[list[str], bool]:
    """按目录排序有界扫描，跳过链接；截断必须由调用方呈现。"""
    base = Path(root).resolve()
    if not base.is_dir():
        raise SourceError("项目源码目录不可用。", "read_failed")
    scan = resolve(root, path) if path else base
    if not scan.is_dir():
        raise SourceError("指定目录不存在，请确认项目相对路径。", "not_found")
    result: list[str] = []
    visited = 0
    incomplete = False

    def unreadable(_error: OSError) -> None:
        nonlocal incomplete
        incomplete = True

    for directory, dirs, names in os.walk(scan, followlinks=False, onerror=unreadable):
        visited += len(dirs)
        if visited > MAX_ENTRIES:
            return result, True
        dirs[:] = sorted(
            d
            for d in dirs
            if allowed((Path(directory) / d).relative_to(base).as_posix())
            and not (Path(directory) / d).is_symlink()
            and not (Path(directory) / d).is_junction()
        )
        for name in sorted(names):
            visited += 1
            path = (Path(directory) / name).relative_to(base).as_posix()
            if visited > MAX_ENTRIES or len(result) >= limit:
                return result, True
            if allowed(path) and not (Path(directory) / name).is_symlink():
                result.append(path)
    return result, incomplete
