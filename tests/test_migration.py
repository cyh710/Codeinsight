"""schema 版本与迁移。

要点：改 `schema.sql` 的表结构后，老的本地索引库必须能**原地**升级，
不能要求用户删库重��——schema 演进不该让人重新索引一次。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from codeinsight.storage.sqlite import SCHEMA_VERSION, ensure_schema, open_sqlite


def _make_legacy_db(path: Path) -> None:
    """造一个"有 user_version 之前的老库"：file 表还是三个布尔列。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE project (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            root_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE file (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            language TEXT NOT NULL,
            blob_sha TEXT,
            content_sha256 TEXT NOT NULL,
            size_bytes INTEGER,
            line_count INTEGER,
            is_generated INTEGER NOT NULL DEFAULT 0,
            is_vendored INTEGER NOT NULL DEFAULT 0,
            is_test INTEGER NOT NULL DEFAULT 0,
            in_index INTEGER NOT NULL DEFAULT 1,
            UNIQUE(project_id, path)
        );
        INSERT INTO project (id, name, root_path) VALUES (1, 'tapestry', 'D:/demo');
        INSERT INTO file (project_id, path, language, content_sha256, is_test)
        VALUES (1, 'tests/test_x.py', 'python', 'abc', 1);
        INSERT INTO file (project_id, path, language, content_sha256, is_vendored)
        VALUES (1, 'vendor/lib.py', 'python', 'def', 1);
        """
    )
    conn.commit()
    conn.close()


def test_fresh_db_is_created(tmp_path: Path) -> None:
    path = tmp_path / "new.db"
    assert ensure_schema(path) == "created"
    with open_sqlite(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_second_call_is_current(tmp_path: Path) -> None:
    path = tmp_path / "new.db"
    ensure_schema(path)
    assert ensure_schema(path) == "current"


def test_legacy_db_is_migrated_in_place(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    _make_legacy_db(path)

    assert ensure_schema(path) == "migrated"

    with open_sqlite(path, row_factory=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

        # 数据没丢
        rows = conn.execute("SELECT path, role FROM file ORDER BY path").fetchall()
        assert [r["path"] for r in rows] == ["tests/test_x.py", "vendor/lib.py"]
        # 布尔列被回填进了 role
        assert rows[0]["role"] == "test"
        assert rows[1]["role"] == "vendored"

        # 旧的布尔列确实没了
        cols = {r[1] for r in conn.execute("PRAGMA table_info(file)").fetchall()}
        assert "role" in cols
        assert "is_test" not in cols
        assert "is_vendored" not in cols
        assert "is_generated" not in cols

        # 新增的表也建出来了
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='dependency'"
        ).fetchone()[0] == 1


def test_migration_keeps_project_rows(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    _make_legacy_db(path)
    ensure_schema(path)
    with open_sqlite(path, row_factory=True) as conn:
        project = conn.execute("SELECT name, root_path FROM project").fetchone()
        assert project["name"] == "tapestry"
        assert project["root_path"] == "D:/demo"
