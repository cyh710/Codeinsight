"""项目移除只影响 CodeInsight 数据；忙碌保护与身份迁移独立验收。"""

import pytest
from fastapi.testclient import TestClient

from codeinsight.api.app import create_app
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.storage.conversations import ConversationRepository
from codeinsight.storage.sqlite import SCHEMA_VERSION, db_path, ensure_schema, open_sqlite


@pytest.fixture
def removable(data_dir, tmp_path):
    roots = []
    for name in ("keep", "remove"):
        root = tmp_path / name
        root.mkdir()
        (root / "app.py").write_text("def save(value):\n    return value\n", encoding="utf-8")
        index_project(db_path(data_dir), root=root, name=name)
        roots.append(root)
    return roots


def test_remove_cascades_only_its_data_and_keeps_source_and_other_project(removable, data_dir):
    with open_sqlite(db_path(data_dir), row_factory=True) as conn:
        repo = ConversationRepository(conn)
        for pid in (1, 2):
            repo.reserve(pid, "c", "r", "保留范围", None)
            repo.event(pid, "c", "r", "answer", {"text": "已保存解释"})
            repo.event(pid, "c", "r", "done", {})
        conn.execute(
            "INSERT INTO agent_task(id,project_id,conversation_id,question,status) VALUES('old',2,'c','q','completed')"
        )
        conn.execute(
            "INSERT INTO agent_event(task_id,type,payload_json) VALUES('old','answer','{}')"
        )
        conn.commit()
    with TestClient(create_app()) as client:
        response = client.delete("/projects/2")
        assert response.status_code == 200, response.text
        assert response.json() == {"project_id": 2, "removed": True, "source_deleted": False}
        assert client.get("/projects/2").status_code == 404
        assert (
            client.get("/projects/1/conversations/c/turns/r").json()["answer"]["text"]
            == "已保存解释"
        )
        assert client.get("/knowledge/tree").status_code == 200
        assert client.delete("/projects/2").status_code == 404
    assert (removable[1] / "app.py").read_text(encoding="utf-8").startswith("def save")
    with open_sqlite(db_path(data_dir)) as conn:
        for table in ("file", "symbol", "chunk", "conversation", "conversation_turn", "agent_task"):
            assert not conn.execute(f"SELECT 1 FROM {table} WHERE project_id=2").fetchone()
        assert not conn.execute("SELECT 1 FROM agent_event WHERE task_id='old'").fetchone()
        assert conn.execute("SELECT COUNT(*) FROM chunk_fts").fetchone()[0] > 0
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


@pytest.mark.parametrize("kind", ["index", "answer", "agent", "planned", "executing", "review"])
def test_busy_project_is_not_removed(removable, data_dir, kind):
    # 启动恢复完成后再模拟当前进程正在运行的任务。
    with TestClient(create_app()) as client:
        with open_sqlite(db_path(data_dir), row_factory=True) as conn:
            if kind == "index":
                conn.execute(
                    "INSERT INTO index_run(project_id,head_commit,mode) VALUES(2,'','full')"
                )
            elif kind == "answer":
                ConversationRepository(conn).reserve(2, "busy", "r", "正在生成", None)
            elif kind == "agent":
                conn.execute(
                    "INSERT INTO agent_task(id,project_id,conversation_id,question,status) VALUES('running',2,'c','q','running')"
                )
            else:
                conn.execute(
                    "INSERT INTO execution_task(id,project_id,question,plan_json,status) "
                    "VALUES('exec-busy',2,'q','{}',?)",
                    (kind,),
                )
            conn.commit()
        response = client.delete("/projects/2")
        assert response.status_code == 409
        assert client.get("/projects/2").status_code == 200
        assert client.delete("/projects/1").status_code == 200


def test_removed_id_is_not_reused_by_cli_or_api(removable, data_dir, tmp_path):
    with TestClient(create_app()) as client:
        assert client.delete("/projects/2").status_code == 200
        root = tmp_path / "new"
        root.mkdir()
        (root / "x.py").write_text("x = 1\n", encoding="utf-8")
        response = client.post("/projects", json={"root_path": str(root), "name": "api-new"})
        assert response.status_code == 202, response.text
        fresh = response.json()["id"]
        assert fresh > 2
        assert client.delete(f"/projects/{fresh}").status_code == 200
    index_project(db_path(data_dir), root=root, name="cli-new")
    with open_sqlite(db_path(data_dir)) as conn:
        assert conn.execute("SELECT id FROM project WHERE name='cli-new'").fetchone()[0] > fresh


def test_migration_4_to_5_preserves_index_and_reserves_existing_ids(removable, data_dir):
    with open_sqlite(db_path(data_dir)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM symbol").fetchone()[0]
        conn.execute("DROP TABLE project_id_counter")
        conn.execute("PRAGMA user_version=4")
        conn.commit()
    assert ensure_schema(db_path(data_dir)) == "migrated"
    with open_sqlite(db_path(data_dir)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM symbol").fetchone()[0] == count
        assert conn.execute("SELECT last_id FROM project_id_counter").fetchone()[0] == 2
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
