"""源码快照保留原始字节身份；三种阅读入口共享同一版本恢复规则。"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codeinsight.cognitive.indexing.scanner import read_blobs


class SourceError(ValueError):
    """向工具与 HTTP 层传递同一种可解释失败，不隐式换用新版文件。"""

    def __init__(self, message: str, code: str = "stale_source") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Source:
    raw: bytes
    sha256: str
    head_commit: str | None
    workspace_changed: bool = False
    index_epoch: int | None = None


def _workspace_changed(root: str, path: str, original: bytes) -> bool:
    if (Path(root) / ".git").exists():
        return False
    try:
        current = read_blobs(Path(root), None, [path])[path]
    except (OSError, RuntimeError, ValueError, KeyError):
        return False
    return current.replace(b"\r\n", b"\n") != original.replace(b"\r\n", b"\n")


def cache_path(conn: sqlite3.Connection, digest: str) -> Path | None:
    """磁盘缓存与索引库同目录；内存库没有持久化快照位置。"""
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SourceError("源码指纹无效。", "bad_request")
    database = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    return Path(database).parent / "sources" / digest[:2] / digest if database else None


def store_bytes(conn: sqlite3.Connection, raw: bytes) -> str:
    """先原子保存内容，再由索引事务登记归属；失败不能发布缺失的新快照。"""
    digest = hashlib.sha256(raw).hexdigest()
    target = cache_path(conn, digest)
    if target is None:
        return digest
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return digest


def register_source(conn: sqlite3.Connection, project_id: int, path: str, digest: str) -> None:
    """归属与索引一起提交；保留旧文件身份，不把缓存目录本身当作读取授权。"""
    conn.execute(
        "INSERT OR IGNORE INTO file_snapshot(project_id,commit_sha,path,content_sha256) "
        "VALUES(?,?,?,?)",
        (project_id, "source:" + digest, path, digest),
    )


def preserve_index(conn: sqlite3.Connection, project_id: int) -> None:
    """旧版本归属随索引事务提交，尚未保存过的字节不会因此被伪造出来。"""
    conn.execute(
        "INSERT OR IGNORE INTO file_snapshot(project_id,commit_sha,path,content_sha256) "
        "SELECT project_id,'source:'||content_sha256,path,content_sha256 FROM file WHERE project_id=?",
        (project_id,),
    )
    conn.execute(
        "INSERT OR IGNORE INTO file_snapshot(project_id,commit_sha,path,content_sha256) "
        "SELECT f.project_id,'epoch:'||r.index_epoch,f.path,f.content_sha256 FROM file f "
        "JOIN repo_state r ON r.project_id=f.project_id WHERE f.project_id=?",
        (project_id,),
    )


def read_source(
    conn: sqlite3.Connection,
    project_id: int,
    path: str,
    *,
    expected_sha: str | None = None,
    head_commit: str | None = None,
    index_epoch: int | None = None,
) -> Source:
    """只读取该项目/路径实际索引过的版本；恢复换行后仍须完全命中原哈希。"""
    if not path or Path(path).is_absolute() or ".." in path.replace("\\", "/").split("/"):
        raise SourceError("索引中没有这个文件。", "not_found")
    row = conn.execute(
        "SELECT f.content_sha256,p.root_path,r.head_commit,r.index_epoch FROM file f "
        "JOIN project p ON p.id=f.project_id LEFT JOIN repo_state r ON r.project_id=p.id "
        "WHERE f.project_id=? AND f.path=?",
        (project_id, path),
    ).fetchone()
    current_epoch = (
        (row[3],)
        if row is not None
        else conn.execute(
            "SELECT index_epoch FROM repo_state WHERE project_id=?", (project_id,)
        ).fetchone()
    )
    historical_epoch = index_epoch is not None and (
        not current_epoch or current_epoch[0] != index_epoch
    )
    if historical_epoch:
        old = conn.execute(
            "SELECT content_sha256 FROM file_snapshot WHERE project_id=? AND commit_sha=? AND path=?",
            (project_id, f"epoch:{index_epoch}", path),
        ).fetchone()
        if old is None:
            raise SourceError("这个索引版本的源码快照未保存，请打开当前版本。", "not_found")
        if expected_sha is not None and expected_sha != old[0]:
            raise SourceError("源码指纹与指定索引版本不符。")
        expected_sha = old[0]
    if expected_sha is None:
        if row is None:
            raise SourceError("索引中没有这个文件。", "not_found")
        digest, root, commit = row[:3]
    elif row is not None and row[0] == expected_sha:
        digest, root, commit = row[:3]
    else:
        historical = conn.execute(
            "SELECT s.content_sha256,p.root_path FROM file_snapshot s JOIN project p ON p.id=s.project_id "
            "WHERE s.project_id=? AND s.path=? AND s.content_sha256=? LIMIT 1",
            (project_id, path, expected_sha),
        ).fetchone()
        if historical is None:
            raise SourceError("这个源码版本不属于该项目的已索引文件。", "not_found")
        digest, root = historical
        commit = head_commit
    if historical_epoch:
        commit = head_commit
    resolved_epoch = (
        index_epoch
        if index_epoch is not None
        else (row[3] if row is not None and digest == row[0] else None)
    )
    if (
        not historical_epoch
        and head_commit is not None
        and row is not None
        and digest == row[0]
        and head_commit != commit
    ):
        raise SourceError("源码提交版本已变化，请重新打开对应版本。")
    target = cache_path(conn, digest)
    if target is not None and target.exists():
        try:
            cached = target.read_bytes()
        except OSError:
            cached = b""
        if hashlib.sha256(cached).hexdigest() == digest:
            return Source(
                cached, digest, commit, _workspace_changed(root, path, cached), resolved_epoch
            )
    try:
        raw = read_blobs(Path(root), commit, [path])[path]
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        raise SourceError(
            "对应的源码快照不可用，请确认目录或更新项目索引。", "read_failed"
        ) from exc
    lf = raw.replace(b"\r\n", b"\n")
    for candidate in (raw, lf, lf.replace(b"\n", b"\r\n")):
        if hashlib.sha256(candidate).hexdigest() == digest:
            try:
                store_bytes(conn, candidate)
            except OSError:
                logging.getLogger(__name__).warning(
                    "无法保存源码快照缓存，仍返回本次已核对的原始内容。"
                )
            return Source(candidate, digest, commit, False, resolved_epoch)
    raise SourceError(
        "该文件内容已变化且没有对应的旧源码快照。请更新项目索引；换行号重试无法恢复旧版。"
    )
