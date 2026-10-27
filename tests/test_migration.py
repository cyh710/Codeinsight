"""schema 版本与迁移。

要点：改 `schema.sql` 的表结构后，老的本地索引库必须能**原地**升级，
不能要求用户删库重��——schema 演进不该让人重新索引一次。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

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


def test_v1_adds_rule_version_mapping_without_losing_project(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    ensure_schema(path)
    with open_sqlite(path) as conn:
        conn.execute("INSERT INTO project (name, root_path) VALUES ('keep-project', '/fixture')")
        conn.execute("DROP TABLE concept_rule_version")
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    assert ensure_schema(path) == "migrated"
    with open_sqlite(path) as conn:
        assert conn.execute("SELECT name FROM project").fetchone()[0] == "keep-project"
        assert conn.execute("SELECT COUNT(*) FROM concept_rule_version").fetchone()[0] == 0
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


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
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='dependency'"
            ).fetchone()[0]
            == 1
        )


def test_migration_keeps_project_rows(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    _make_legacy_db(path)
    ensure_schema(path)
    with open_sqlite(path, row_factory=True) as conn:
        project = conn.execute("SELECT name, root_path FROM project").fetchone()
        assert project["name"] == "tapestry"
        assert project["root_path"] == "D:/demo"


@pytest.mark.parametrize("branch", ["execution-v4", "learning-v5"])
def test_integrated_schema_preserves_both_branch_histories(tmp_path: Path, branch: str) -> None:
    """两支曾使用不同的版本 4；按真实结构升级，不能损失索引或执行记录。"""
    path = tmp_path / f"{branch}.db"
    ensure_schema(path)
    with open_sqlite(path) as conn:
        conn.execute("INSERT INTO project(id,name,root_path) VALUES(7,'keep','/fixture')")
        conn.execute(
            "INSERT INTO file(project_id,path,language,content_sha256) "
            "VALUES(7,'app.py','python','unchanged')"
        )
        conn.execute("INSERT INTO conversation(project_id,id,title) VALUES(7,'c','历史对话')")
        conn.execute(
            "INSERT INTO conversation_turn(project_id,conversation_id,request_id,question,"
            "answer_json,status) VALUES(7,'c','r','旧问题','{\"text\":\"旧回答\"}','completed')"
        )
        if branch == "execution-v4":
            conn.execute("ALTER TABLE conversation DROP COLUMN exploration_json")
            conn.execute("DROP TABLE project_id_counter")
            conn.execute(
                "INSERT INTO execution_task(id,project_id,question,plan_json,status) "
                "VALUES('exec-keep',7,'旧任务','{}','review')"
            )
            conn.execute("PRAGMA user_version=4")
        else:
            conn.execute("UPDATE conversation SET exploration_json='{\"items\":[]}'")
            conn.execute("UPDATE project_id_counter SET last_id=20")
            conn.execute("DROP TABLE execution_task")
            conn.execute("PRAGMA user_version=5")
        conn.commit()

    assert ensure_schema(path) == "migrated"
    assert ensure_schema(path) == "current"
    with open_sqlite(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("SELECT content_sha256 FROM file").fetchone()[0] == "unchanged"
        assert conn.execute("SELECT answer_json FROM conversation_turn").fetchone()[0] == (
            '{"text":"旧回答"}'
        )
        state = conn.execute("SELECT exploration_json FROM conversation").fetchone()[0]
        high_water = conn.execute("SELECT last_id FROM project_id_counter").fetchone()[0]
        if branch == "execution-v4":
            assert state == "{}" and high_water == 7
            assert conn.execute("SELECT status FROM execution_task").fetchone()[0] == "review"
        else:
            assert state == '{"items":[]}' and high_water == 20
            assert conn.execute("SELECT COUNT(*) FROM execution_task").fetchone()[0] == 0
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
