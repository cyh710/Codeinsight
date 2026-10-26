"""真实临时 Git 仓库验证重新定位，不触发模型或 Embedding。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from codeinsight.api import projects
from codeinsight.api.app import create_app
from codeinsight.cognitive.indexing import indexer
from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path, open_sqlite


@pytest.fixture
def relocated_repo(data_dir: Path, tmp_path: Path) -> tuple[int, Path, Path]:
    original = tmp_path / "before"
    original.mkdir()
    (original / "sample.py").write_text("def hello():\n    return '中文😀'\n", encoding="utf-8")
    for arguments in [
        ["init"],
        ["add", "."],
        ["-c", "user.name=fixture", "-c", "user.email=fixture@invalid", "commit", "-m", "fixture"],
    ]:
        subprocess.run(["git", "-C", str(original), *arguments], check=True, capture_output=True)
    result = indexer.index_project(db_path(data_dir), root=original, name="retained")
    with open_sqlite(db_path(data_dir)) as conn:
        conn.execute(
            "INSERT INTO conversation(project_id,id,title) VALUES (?,'kept','原对话')",
            (result.project_id,),
        )
        conn.execute(
            "INSERT INTO conversation_turn(project_id,conversation_id,request_id,question,answer_json,status) "
            "VALUES (?,'kept','old','原问题',?,'completed')",
            (
                result.project_id,
                json.dumps({"answer": "原回答", "source_head_commit": result.head_commit}),
            ),
        )
        conn.commit()
    moved = tmp_path / "after"
    shutil.move(str(original), moved)
    return result.project_id, original, moved


def test_relocate_preserves_identity_history_and_reads_source(relocated_repo):
    project_id, original, moved = relocated_repo
    client = TestClient(create_app())
    assert client.get(f"/projects/{project_id}").json()["source_available"] is False
    before = client.get(f"/projects/{project_id}/conversations/kept/turns").json()
    response = client.post(f"/projects/{project_id}/relocate", json={"root_path": str(moved)})
    assert response.status_code == 202, response.text
    assert response.json()["id"] == project_id
    detail = client.get(f"/projects/{project_id}").json()
    assert detail["root_path"] == str(moved.resolve())
    assert detail["status"] == "ready"
    assert detail["source_available"] is True
    assert detail["files"] == 1
    assert client.get(f"/projects/{project_id}/conversations/kept/turns").json() == before
    source = client.get(f"/projects/{project_id}/code", params={"path": "sample.py"})
    assert source.status_code == 200, source.text
    assert "中文😀" in source.text


def test_rebuild_failure_rolls_back_even_after_old_index_deleted(relocated_repo, monkeypatch):
    project_id, original, moved = relocated_repo
    client = TestClient(create_app())
    before = client.get(f"/projects/{project_id}").json()

    def fail_after_clear(*args, **kwargs):
        raise RuntimeError("测试模拟写入失败")

    monkeypatch.setattr(indexer, "_write_file", fail_after_clear)
    assert (
        client.post(f"/projects/{project_id}/relocate", json={"root_path": str(moved)}).status_code
        == 202
    )
    detail = client.get(f"/projects/{project_id}").json()
    assert detail["status"] == "failed"
    assert detail["root_path"] == str(original)
    assert detail["head_commit"] == before["head_commit"]
    assert detail["files"] == before["files"]
    assert detail["symbols"] == before["symbols"]
    assert "保留" in detail["index_error"]


@pytest.mark.parametrize("kind", ["missing", "ordinary", "uncommitted"])
def test_invalid_directory_cannot_change_existing_project(relocated_repo, tmp_path, kind):
    project_id, original, moved = relocated_repo
    target = tmp_path / kind
    if kind != "missing":
        target.mkdir()
    if kind == "uncommitted":
        subprocess.run(["git", "init", str(target)], check=True, capture_output=True)
    client = TestClient(create_app())
    response = client.post(f"/projects/{project_id}/relocate", json={"root_path": str(target)})
    assert response.status_code == 400
    assert client.get(f"/projects/{project_id}").json()["root_path"] == str(original)


@pytest.mark.parametrize("running", ["index", "answer"])
def test_active_work_prevents_relocation(relocated_repo, running):
    project_id, original, moved = relocated_repo
    with open_sqlite(db_path(settings.data_dir)) as conn:
        if running == "index":
            conn.execute(
                "INSERT INTO index_run(project_id,head_commit,mode) VALUES (?,'','full')",
                (project_id,),
            )
        else:
            conn.execute(
                "INSERT INTO conversation_turn(project_id,conversation_id,request_id,question) VALUES (?,'kept','busy','处理中')",
                (project_id,),
            )
        conn.commit()
    client = TestClient(create_app())
    assert (
        client.post(f"/projects/{project_id}/relocate", json={"root_path": str(moved)}).status_code
        == 409
    )
    assert client.get(f"/projects/{project_id}").json()["root_path"] == str(original)


def test_service_restart_recovers_reservation_and_allows_retry(relocated_repo, monkeypatch):
    project_id, original, moved = relocated_repo
    original_worker = projects.rebuild_relocated_project
    monkeypatch.setattr(projects, "rebuild_relocated_project", lambda *args: None)
    client = TestClient(create_app())
    assert (
        client.post(f"/projects/{project_id}/relocate", json={"root_path": str(moved)}).status_code
        == 202
    )
    assert client.get(f"/projects/{project_id}").json()["status"] == "indexing"
    with TestClient(create_app()) as restarted:
        detail = restarted.get(f"/projects/{project_id}").json()
        assert detail["status"] == "failed"
        assert "服务重启" in detail["index_error"]
        assert detail["root_path"] == str(original)
        monkeypatch.setattr(projects, "rebuild_relocated_project", original_worker)
        assert (
            restarted.post(
                f"/projects/{project_id}/relocate", json={"root_path": str(moved)}
            ).status_code
            == 202
        )
        assert restarted.get(f"/projects/{project_id}").json()["status"] == "ready"


def test_import_and_reimport_reserve_one_run_before_background_starts(relocated_repo, monkeypatch):
    _, _, root = relocated_repo
    client = TestClient(create_app())
    worker = projects.start_indexing
    queued = []
    monkeypatch.setattr(projects, "start_indexing", lambda *args: queued.append(args))
    first = client.post("/projects", json={"root_path": str(root), "name": "fresh"})
    assert first.status_code == 202
    project_id = first.json()["id"]
    assert client.get(f"/projects/{project_id}").json()["status"] == "indexing"
    assert (
        client.post("/projects", json={"root_path": str(root), "name": "fresh"}).status_code == 409
    )
    worker(*queued.pop())
    assert client.get(f"/projects/{project_id}").json()["status"] == "ready"
    second = client.post("/projects", json={"root_path": str(root), "name": "fresh"})
    assert second.status_code == 202
    assert client.get(f"/projects/{project_id}").json()["status"] == "indexing"
    worker(*queued.pop())
    with open_sqlite(db_path(settings.data_dir)) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM index_run WHERE project_id=?", (project_id,)
            ).fetchone()[0]
            == 2
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM index_run WHERE project_id=? AND finished_at IS NULL",
                (project_id,),
            ).fetchone()[0]
            == 0
        )


def test_import_retains_requested_git_version(relocated_repo):
    _, _, root = relocated_repo
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    (root / "new.py").write_text("new = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@invalid",
            "commit",
            "-m",
            "new",
        ],
        check=True,
        capture_output=True,
    )
    client = TestClient(create_app())
    accepted = client.post(
        "/projects", json={"root_path": str(root), "name": "pinned", "ref": commit}
    )
    assert accepted.status_code == 202
    detail = client.get(f"/projects/{accepted.json()['id']}").json()
    assert detail["status"] == "ready"
    assert detail["head_commit"] == commit
    assert detail["files"] == 1
