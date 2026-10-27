"""WAL 写事务持续期间，状态读取不能隐式申请写锁或看到半成品。"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from codeinsight.api.app import create_app
from codeinsight.storage import sqlite as storage


def test_project_reads_work_while_index_writer_keeps_transaction(
    conn: sqlite3.Connection, tmp_path: Path, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 缩短锁等待，让旧实现稳定失败而非拖住测试；不缩短索引或模拟提前释放锁。
    monkeypatch.setattr(storage, "BUSY_TIMEOUT_MS", 50)
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(1,'fixture',?)", (str(tmp_path),))
    conn.execute(
        "INSERT INTO file(project_id,path,language,content_sha256,line_count) "
        "VALUES(1,'app.py','python','committed',1)"
    )
    conn.execute("INSERT INTO conversation(project_id,id,title) VALUES(1,'c','已保存的对话')")
    conn.commit()

    with TestClient(create_app()) as client:
        conn.execute(
            "INSERT INTO index_run(project_id,head_commit,mode) VALUES(1,'fixture','full')"
        )
        conn.commit()
        conn.execute("UPDATE file SET content_sha256='uncommitted' WHERE project_id=1")
        assert conn.in_transaction
        try:
            responses = {
                endpoint: client.get(endpoint)
                for endpoint in (
                    "/projects",
                    "/projects/1",
                    "/projects/1/files",
                    "/projects/1/overview",
                    "/conversations?project_id=1",
                    "/projects/1/conversations/c",
                    "/projects/1/conversations/c/turns",
                )
            }
            for endpoint, response in responses.items():
                assert response.status_code == 200, (endpoint, response.text)
                assert conn.in_transaction
            assert responses["/projects/1"].json()["status"] == "indexing"
            assert responses["/projects/1"].json()["files"] == 1
            assert responses["/projects/1/conversations/c"].json()["title"] == "已保存的对话"
            with closing(storage.open_sqlite(storage.db_path(data_dir))) as reader:
                assert (
                    reader.execute("SELECT content_sha256 FROM file").fetchone()[0] == "committed"
                )
        finally:
            conn.rollback()
        conn.execute("UPDATE index_run SET finished_at=datetime('now'),ok=1 WHERE project_id=1")
        conn.commit()
        assert client.get("/projects/1").json()["status"] == "ready"
