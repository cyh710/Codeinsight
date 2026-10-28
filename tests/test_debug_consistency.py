"""审查复现：版本混用、词法遮蔽、隔离索引发布与重启恢复；不调用模型。"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.answer import GroundedFile, Grounding, split_answer
from codeinsight.api import query
from codeinsight.api.app import create_app
from codeinsight.cognitive.indexing import indexer, staging
from codeinsight.cognitive.parsing.base import ParseContext
from codeinsight.cognitive.parsing.python_parser import PythonParser
from codeinsight.llm.provider import StreamChunk
from codeinsight.storage.sqlite import db_path, open_sqlite


def test_citation_ranges_cannot_join_versions_and_ambiguous_versions_do_not_link():
    g = Grounding()
    g.add(GroundedFile("app.py", 1, 2, source_kind="workspace", content_sha256="v1"))
    g.add(GroundedFile("app.py", 3, 4, source_kind="workspace", content_sha256="v2"))
    answer = split_answer("两种实现可以比较 [app.py:1-4]。", g)
    assert not answer.citations and "两种实现可以比较" in answer.text
    g.add(GroundedFile("app.py", 3, 4, source_kind="workspace", content_sha256="v1"))
    answer = split_answer("一份完整实现 [app.py:1-4]。", g)
    assert answer.citations[0].content_sha256 == "v1"
    assert answer.citations[0].end_lineno == 4
    g.add(GroundedFile("app.py", 1, 4, source_kind="workspace", content_sha256="v2"))
    assert not split_answer("两版都覆盖 [app.py:1-4]。", g).citations


@pytest.mark.parametrize("binding", ["parameter", "assignment", "loop"])
def test_shadowed_callable_is_uncertain_and_never_links_to_same_named_function(binding):
    body = {
        "parameter": "def run(helper):\n    return helper()\n",
        "assignment": "def run():\n    helper = lambda: 2\n    return helper()\n",
        "loop": "def run():\n    for helper in []:\n        helper()\n",
    }[binding]
    parsed = PythonParser().parse(
        "app.py",
        "def helper():\n    return 1\n\n" + body,
        ParseContext(project_id=1, repo_root="fixture"),
    )
    edge = next(e for e in parsed.edges if e.src_qualname == "app.run" and e.dst_name == "helper")
    assert edge.dst_qualname is None and edge.confidence < 1


class OfflineProvider:
    model_id = "offline-debug"

    async def stream_with_tools(self, *args, **kwargs):
        yield StreamChunk(text="已有材料可以继续阅读。", finish_reason="stop")


def test_staging_allows_questions_and_source_reads_and_preserves_parallel_changes(
    data_dir, tmp_path, monkeypatch
):
    root = tmp_path / "first"
    root.mkdir()
    root.joinpath("app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    database = db_path(data_dir)
    indexer.index_project(database, root=root, name="first")
    root.joinpath("new.py").write_text("def added():\n    return 2\n", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    other.joinpath("other.py").write_text("def separate():\n    return 3\n", encoding="utf-8")
    entered, release = threading.Event(), threading.Event()
    original = indexer._write_file

    def slow_write(conn, **kwargs):
        if kwargs["repo_file"].path == "new.py":
            entered.set()
            assert release.wait(10), "测试未释放隔离构建"
        return original(conn, **kwargs)

    monkeypatch.setattr(indexer, "_write_file", slow_write)
    monkeypatch.setattr(query, "_PROVIDER_FACTORY", OfflineProvider)
    with TestClient(create_app()) as client, ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(indexer.index_project, database, root=root, name="first")
        try:
            assert entered.wait(10)
            code = client.get("/projects/1/code?path=app.py")
            assert code.status_code == 200
            cid = client.post("/projects/1/conversations").json()["id"]
            answer = client.post(
                "/query",
                json={"project_id": 1, "conversation_id": cid, "question": "这个项目做什么"},
            )
            assert answer.status_code == 200 and "已有材料" in answer.json()["text"]
            indexer.index_project(database, root=other, name="other")
        finally:
            release.set()
        future.result(timeout=10)
        assert client.get(f"/projects/1/conversations/{cid}/turns").json()["items"]
        historical = client.get(
            "/projects/1/code",
            params={
                "path": "app.py",
                "source_kind": "workspace",
                "content_sha256": code.json()["content_sha256"],
            },
        )
        assert historical.status_code == 200
    with closing(open_sqlite(database)) as conn:
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not conn.execute(
            "SELECT 1 FROM symbol s JOIN file f ON f.id=s.file_id WHERE s.project_id<>f.project_id"
        ).fetchone()
        assert not conn.execute(
            "SELECT 1 FROM chunk c JOIN symbol s ON s.id=c.symbol_id WHERE c.project_id<>s.project_id"
        ).fetchone()
        assert conn.execute("SELECT COUNT(*) FROM file WHERE project_id=1").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM file WHERE project_id=2").fetchone()[0] == 1
        assert (
            conn.execute("SELECT COUNT(*) FROM chunk_fts WHERE chunk_fts MATCH 'added'").fetchone()[
                0
            ]
            > 0
        )


def test_publish_failure_does_not_replace_old_index(data_dir, tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    root.joinpath("app.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    database = db_path(data_dir)
    indexer.index_project(database, root=root, name="repo")
    root.joinpath("app.py").write_text("def changed():\n    return 2\n", encoding="utf-8")
    original = staging._insert

    def fail(conn, table, row, **kwargs):
        if table == "symbol":
            raise RuntimeError("离线模拟发布失败")
        return original(conn, table, row, **kwargs)

    monkeypatch.setattr(staging, "_insert", fail)
    with pytest.raises(RuntimeError, match="发布失败"):
        indexer.index_project(database, root=root, name="repo")
    with closing(open_sqlite(database)) as conn:
        assert conn.execute("SELECT 1 FROM symbol WHERE qualname='app.old'").fetchone()
        assert (
            conn.execute("SELECT index_epoch FROM repo_state WHERE project_id=1").fetchone()[0] == 1
        )
        assert conn.execute("SELECT ok FROM index_run ORDER BY id DESC LIMIT 1").fetchone()[0] == 0


def test_restart_fails_lost_execution_without_removing_worktree(conn, tmp_path):
    root = tmp_path / "worktree"
    root.mkdir()
    root.joinpath("kept.txt").write_text("kept")
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(1,'fixture',?)", (str(tmp_path),))
    conn.execute(
        "INSERT INTO execution_task(id,project_id,question,status,driver,plan_json,result_json,worktree_path) VALUES('lost',1,'fixture','executing','off','{}',?,?)",
        (json.dumps({"progress": [{"text": "原进度"}]}), str(root)),
    )
    conn.commit()
    with TestClient(create_app()) as client:
        result = client.get("/projects/1/executions/lost").json()
        assert result["status"] == "failed" and "重启" in result["error"]
        assert result["progress"] == [{"text": "原进度"}]
    assert root.joinpath("kept.txt").read_text() == "kept"


def test_external_database_writer_has_recoverable_error(conn, tmp_path, monkeypatch):
    from codeinsight.storage import sqlite as storage

    monkeypatch.setattr(storage, "BUSY_TIMEOUT_MS", 50)
    tmp_path.joinpath("app.py").write_text("value = 1\n")
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(1,'fixture',?)", (str(tmp_path),))
    conn.commit()
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        conn.execute("UPDATE project SET name='pending' WHERE id=1")
        try:
            response = client.post("/projects/1/conversations")
            assert response.status_code == 503
            assert response.json()["error"]["detail"] == "database_busy"
            source = client.get("/projects/1/code?path=app.py")
            assert source.status_code == 409 and "繁忙" in source.json()["error"]["hint"]
        finally:
            conn.rollback()
