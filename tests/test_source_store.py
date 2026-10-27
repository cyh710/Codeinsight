"""源码版本、换行恢复和历史归属的离线验收。"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.selection import code_selection
from codeinsight.api.app import create_app
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.cognitive.indexing.source_store import SourceError, cache_path, read_source
from codeinsight.storage.sqlite import db_path, open_sqlite


def test_cache_write_failure_can_still_read_verified_legacy_source(
    source_project, data_dir, monkeypatch, caplog
):
    from codeinsight.cognitive.indexing import source_store

    with open_sqlite(db_path(data_dir)) as conn:
        old = read_source(conn, 1, "app.py")
        cache_path(conn, old.sha256).unlink()

        def cannot_write(*args):
            raise PermissionError("offline")

        monkeypatch.setattr(source_store, "store_bytes", cannot_write)
        assert read_source(conn, 1, "app.py").raw == old.raw
        assert "无法保存" in caplog.text


def test_failed_reindex_preserves_published_index_and_snapshot(
    source_project, data_dir, monkeypatch
):
    from codeinsight.cognitive.indexing import indexer

    def fail(*args, **kwargs):
        raise RuntimeError("offline publication failure")

    monkeypatch.setattr(indexer, "_write_file", fail)
    source_project.joinpath("app.py").write_bytes(b"def new_function():\n    return 2\n")
    with pytest.raises(RuntimeError):
        index_project(db_path(data_dir), root=source_project, name="local", embed=False)
    with open_sqlite(db_path(data_dir)) as conn:
        assert (
            conn.execute("SELECT index_epoch FROM repo_state WHERE project_id=1").fetchone()[0] == 1
        )
        assert b"def save(value)" in read_source(conn, 1, "app.py").raw


@pytest.fixture
def source_project(tmp_path, data_dir):
    root = tmp_path / "local"
    root.mkdir()
    (root / "app.py").write_bytes(b"def save(value):\n    return value\n")
    index_project(db_path(data_dir), root=root, name="local", embed=False)
    return root


def test_source_identity_does_not_pick_up_new_epoch_after_read(
    source_project, data_dir, monkeypatch
):
    from codeinsight.cognitive.indexing import source_store

    with open_sqlite(db_path(data_dir)) as conn:

        def publish_during_read(*args):
            conn.execute("UPDATE repo_state SET index_epoch=2 WHERE project_id=1")
            conn.commit()
            return False

        monkeypatch.setattr(source_store, "_workspace_changed", publish_during_read)
        source = read_source(conn, 1, "app.py")
        assert source.index_epoch == 1
        assert conn.execute("SELECT index_epoch FROM repo_state").fetchone()[0] == 2


def test_snapshot_is_shared_by_reader_selection_and_new_versions(source_project, data_dir):
    root = source_project
    (root / "app.py").write_bytes(b"def save(value):\n    return value + 1\n")
    with TestClient(create_app()) as client:
        old = client.get("/projects/1/code", params={"path": "app.py", "source_kind": "index"}).json()
        assert "return value + 1" not in old["content"]
        assert old["workspace_changed"]
        with open_sqlite(db_path(data_dir), row_factory=True) as conn:
            text = code_selection(
                conn,
                1,
                {
                    "path": "app.py",
                    "head_commit": old["head_commit"],
                    "content_sha256": old["content_sha256"],
                    "lineno": 2,
                    "end_lineno": 2,
                    "selection": {"start_column": 5, "end_column": 17},
                },
                100,
            )
            assert text == "return value"
        index_project(db_path(data_dir), root=root, name="local", embed=False)
        latest = client.get("/projects/1/code", params={"path": "app.py", "source_kind": "index"}).json()
        assert "return value + 1" in latest["content"] and latest["index_epoch"] == 2
        previous = client.get(
            "/projects/1/code", params={"path": "app.py", "index_epoch": 1}
        ).json()
        assert previous["content"] == old["content"]
        root.joinpath("app.py").unlink()
        assert (
            client.get("/projects/1/code", params={"path": "app.py", "index_epoch": 1}).json()[
                "content"
            ]
            == old["content"]
        )


@pytest.mark.parametrize("before,after", [(b"\n", b"\r\n"), (b"\r\n", b"\n")])
def test_legacy_newline_restore_requires_exact_original_hash(
    source_project, data_dir, before, after
):
    root = source_project
    original = b"def save(value):\n    return value\n".replace(b"\n", before)
    root.joinpath("app.py").write_bytes(original)
    index_project(db_path(data_dir), root=root, name="local", embed=False)
    with open_sqlite(db_path(data_dir)) as conn:
        digest = hashlib.sha256(original).hexdigest()
        cache_path(conn, digest).unlink()
        root.joinpath("app.py").write_bytes(original.replace(before, after))
        restored = read_source(conn, 1, "app.py")
        assert restored.raw == original and restored.sha256 == digest
        assert cache_path(conn, digest).read_bytes() == original


def test_real_change_does_not_get_normalized_or_promoted_to_old_version(source_project, data_dir):
    with open_sqlite(db_path(data_dir)) as conn:
        original = read_source(conn, 1, "app.py")
        cache_path(conn, original.sha256).unlink()
        source_project.joinpath("app.py").write_text(
            "def save(value):\n return value + 1\n", encoding="utf-8"
        )
        with pytest.raises(SourceError, match="内容已变化"):
            read_source(conn, 1, "app.py")


def test_corruption_cannot_create_source_and_cross_project_cache_is_not_authority(
    source_project, data_dir
):
    with open_sqlite(db_path(data_dir)) as conn:
        source = read_source(conn, 1, "app.py")
        cache_path(conn, source.sha256).write_bytes(b"corrupt")
        assert read_source(conn, 1, "app.py").raw == source.raw
        conn.execute("INSERT INTO project(id,name,root_path) VALUES(2,'other','missing')")
        conn.commit()
        with pytest.raises(SourceError):
            read_source(conn, 2, "app.py", expected_sha=source.sha256)
        with pytest.raises(SourceError):
            read_source(conn, 1, "../app.py", expected_sha=source.sha256)
        cache_path(conn, source.sha256).write_bytes(b"corrupt")
        source_project.joinpath("app.py").unlink()
        source_project.rmdir()
        with pytest.raises(SourceError, match="快照不可用"):
            read_source(conn, 1, "app.py")
