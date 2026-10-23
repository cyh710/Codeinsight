"""API 路由测试：对契约形状逐端点验证（docs/api-contract.md）。

种子数据走 schema 直插——不依赖索引器（A 线 A3 未合入），只验证
C 线负责的"查询与组装"这一层。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from codeinsight.api import indexing
from codeinsight.api.app import create_app
from codeinsight.storage.sqlite import db_path


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> sqlite3.Connection:
    """一个有真实形状数据的索引库：1 项目 ready，2 项目 indexing。"""
    c = conn
    c.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'demo', 'D:/nowhere/demo')")
    c.execute(
        "INSERT INTO project (id, name, root_path) VALUES (2, 'pending', 'D:/nowhere/pending')"
    )
    c.execute(
        "INSERT INTO repo_state (project_id, head_commit, head_branch, indexed_at, parser_version, index_epoch)"
        " VALUES (1, 'abc123', 'main', '2026-10-24T08:31:05Z', 't', 1)"
    )
    # 项目 1：一次成功的索引 run（状态推导走 index_run）
    c.execute(
        "INSERT INTO index_run (project_id, head_commit, mode, started_at, finished_at, ok)"
        " VALUES (1, 'abc123', 'full', '2026-10-24T08:30:00Z', '2026-10-24T08:31:05Z', 1)"
    )

    c.executemany(
        "INSERT INTO file (id, project_id, path, language, content_sha256, size_bytes, line_count, role)"
        " VALUES (?, 1, ?, 'python', ?, ?, ?, ?)",
        [
            (1, "src/a.py", "sha-a", 100, 10, "source"),
            (2, "src/b.py", "sha-b", 200, 20, "source"),
            (3, "tests/test_a.py", "sha-t", 50, 5, "test"),
        ],
    )
    # 符号：a.helper 在两个文件里同名（ambiguous 用例）；b.worker 调 a.helper
    c.executemany(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " header, docstring, is_async, is_private, is_dunder, n_lines, source_sha256)"
        " VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, 'sha')",
        [
            (1, 1, "src.a.entry", "entry", "function", 1, 3, "def entry():", "入口", 3),
            (2, 1, "src.a.helper", "helper", "function", 5, 8, "def helper():", "帮忙", 4),
            (3, 2, "src.b.helper", "helper", "function", 1, 2, "def helper():", None, 2),
            (4, 2, "src.b.worker", "worker", "method", 10, 30, "def worker():", "干活", 21),
        ],
    )
    # 同 qualname 第二处定义（契约 §4.2 的 ambiguous 场景）
    c.execute(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " header, docstring, is_async, is_private, is_dunder, n_lines, source_sha256)"
        " VALUES (5, 1, 3, 'src.a.helper', 'helper', 'function', 1, 2, 'def helper():',"
        " '测试里的替身', 0, 0, 0, 2, 'sha')"
    )
    # 模块（overview 的 core_modules 用例）
    c.execute(
        "INSERT INTO module (project_id, file_id, qualname, docstring, is_core)"
        " VALUES (1, 1, 'src.a', '模块 a 的职责', 1)"
    )
    # 边：两条确定的 call（指向 helper）+ 一条动态调用（getattr，confidence 0.5）
    c.executemany(
        "INSERT INTO edge (project_id, src_symbol_id, dst_symbol_id, src_qualname, dst_name,"
        " dst_qualname, kind, lineno, confidence)"
        " VALUES (1, ?, ?, ?, ?, ?, 'call', ?, ?)",
        [
            (1, 2, "src.a.entry", "helper", "src.a.helper", 2, 1.0),
            (4, 2, "src.b.worker", "helper", "src.a.helper", 12, 1.0),
            (1, None, "src.a.entry", "getattr", None, 3, 0.5),
        ],
    )
    # chunk：worker 的源码正文（symbol source 拼装用例）
    c.execute(
        "INSERT INTO chunk (project_id, symbol_id, file_id, ordinal, part_count, qualname, name,"
        " kind, lineno, end_lineno, body, token_text, source_sha256, file_content_sha256)"
        " VALUES (1, 4, 2, 0, 1, 'src.b.worker', 'worker', 'method', 10, 12,"
        " 'def worker():\n    helper()\n    return 1', 'worker helper', 'sha', 'sha')"
    )
    # 概念与实例（知识层用例）
    c.execute(
        "INSERT INTO concept (id, name, category, summary, principles, tradeoffs, alternatives,"
        " detection_json, references_json)"
        " VALUES ('demo-cache', '缓存', 'cache', '用缓存挡住重复计算。', '读前查，写后填。',"
        " '换速度，付出一致性代价。', '不用缓存。', '{}', '[\"https://example.com\"]')"
    )
    c.executemany(
        "INSERT INTO concept_instance (project_id, concept_id, symbol_id, file_id, path, lineno,"
        " qualname, evidence, confidence) VALUES (1, 'demo-cache', ?, ?, ?, ?, ?, ?, ?)",
        [
            (2, 1, "src/a.py", 5, "src.a.helper", "call redis.Redis", 1.0),
            (4, 2, "src/b.py", 10, "src.b.worker", "import redis", 0.7),
        ],
    )
    c.commit()
    return c


@pytest.fixture
def client(seeded: sqlite3.Connection) -> TestClient:
    return TestClient(create_app())


def err(body: dict) -> dict:
    return body["error"]


# ─── 项目 ─────────────────────────────────────────────────────


def test_projects_list_carries_counts(client: TestClient) -> None:
    items = client.get("/projects").json()
    assert len(items) == 2
    demo = next(p for p in items if p["name"] == "demo")
    assert demo["files"] == 3
    assert demo["symbols"] == 5


def test_project_detail_status_and_counts(client: TestClient) -> None:
    body = client.get("/projects/1").json()
    assert body["status"] == "ready"
    assert body["chunks"] == 1
    assert body["edges"] == 3
    assert body["concepts"] == 1
    assert body["concept_instances"] == 2


def test_project_without_finished_run_is_indexing(client: TestClient) -> None:
    assert client.get("/projects/2").json()["status"] == "indexing"


def test_unknown_project_404_contract_shape(client: TestClient) -> None:
    res = client.get("/projects/999")
    assert res.status_code == 404
    e = err(res.json())
    assert e["code"] == "project_not_found"
    assert set(e) == {"code", "title", "hint", "detail"}


# ─── 文件与符号 ───────────────────────────────────────────────


def test_files_bare_array_with_symbol_count(client: TestClient) -> None:
    body = client.get("/projects/1/files").json()
    assert isinstance(body, list)
    a = next(f for f in body if f["path"] == "src/a.py")
    assert a["symbol_count"] == 2
    assert a["role"] == "source"


def test_symbols_filter_kind_and_pagination_shape(client: TestClient) -> None:
    body = client.get("/projects/1/symbols", params={"kind": "method"}).json()
    assert body["total"] == 1
    assert body["items"][0]["qualname"] == "src.b.worker"
    assert body["items"][0]["out_degree"] == 1

    page = client.get("/projects/1/symbols", params={"limit": 2, "offset": 2}).json()
    assert len(page["items"]) == 2
    assert page["total"] == 5


def test_symbol_detail_relations_and_source(client: TestClient) -> None:
    body = client.get("/projects/1/symbols/src.a.helper").json()
    assert body["in_degree"] == 2
    assert {r["qualname"] for r in body["callers"]} == {"src.a.entry", "src.b.worker"}
    assert all(r["uncertain"] is False for r in body["callers"])
    assert body["concept_ids"] == ["demo-cache"]

    worker = client.get("/projects/1/symbols/src.b.worker").json()
    # 源码按 chunk 拼回，带行号前缀（契约 §4.2）
    assert worker["source"].startswith("10 | def worker():")

    # 动态调用（getattr，confidence 0.5）：挂在 entry 的被调里，标不确定
    entry = client.get("/projects/1/symbols/src.a.entry").json()
    dynamic = next(r for r in entry["callees"] if r["qualname"] == "getattr")
    assert dynamic["uncertain"] is True
    assert dynamic["note"]


def test_symbol_detail_ambiguous_alternatives(client: TestClient) -> None:
    body = client.get("/projects/1/symbols/src.a.helper").json()
    assert body["ambiguous"] is True
    assert body["alternatives"][0]["path"] == "tests/test_a.py"


def test_symbol_not_found_404(client: TestClient) -> None:
    res = client.get("/projects/1/symbols/no.such")
    assert res.status_code == 404
    assert err(res.json())["code"] == "symbol_not_found"


def test_callers_endpoint_shape(client: TestClient) -> None:
    body = client.get("/projects/1/symbols/src.a.helper/callers").json()
    assert body["total"] == 2
    assert all(
        set(r) == {"qualname", "path", "lineno", "confidence", "uncertain", "note"}
        for r in body["items"]
    )


# ─── 概览 ─────────────────────────────────────────────────────


def test_overview_numbers_from_index(client: TestClient) -> None:
    body = client.get("/projects/1/overview").json()
    assert "3 个文件" in body["architecture_summary"]
    assert body["languages"][0]["language"] == "python"
    assert body["core_modules"][0]["qualname"] == "src.a"
    assert body["stats"]["symbols"] == 5


# ─── 知识层 ───────────────────────────────────────────────────


def test_concepts_list_with_instance_count(client: TestClient) -> None:
    body = client.get("/projects/1/concepts").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["concept_id"] == "demo-cache"
    assert item["instance_count"] == 2


def test_concept_detail_and_instances(client: TestClient) -> None:
    detail = client.get("/projects/1/concepts/demo-cache").json()
    assert detail["instance_paths"] == ["src/a.py", "src/b.py"]

    inst = client.get("/projects/1/concepts/demo-cache/instances").json()
    assert inst["total"] == 2
    assert inst["items"][0]["evidence"] == "call redis.Redis"


def test_explain_quick_reads_ontology_without_llm(client: TestClient) -> None:
    body = client.post("/projects/1/concepts/demo-cache/explain", json={"depth": "quick"}).json()
    assert body["llm_used"] is False
    assert body["summary"].startswith("用缓存")


def test_explain_project_derives_facts_from_index(client: TestClient) -> None:
    body = client.post("/projects/1/concepts/demo-cache/explain", json={"depth": "project"}).json()
    assert body["llm_used"] is False
    assert len(body["facts"]) == 2
    assert body["facts"][0]["citation"]["path"] == "src/a.py"
    assert body["inferences"] == []


def test_explain_deep_until_llm_wired(client: TestClient) -> None:
    res = client.post("/projects/1/concepts/demo-cache/explain", json={"depth": "deep"})
    assert res.status_code == 502
    assert err(res.json())["code"] == "upstream_error"


def test_concept_not_found(client: TestClient) -> None:
    res = client.get("/projects/1/concepts/nope")
    assert res.status_code == 404
    assert err(res.json())["code"] == "concept_not_found"


# ─── 流程与变更 ───────────────────────────────────────────────


def test_flows_empty_until_detector_lands(client: TestClient) -> None:
    assert client.get("/projects/1/flows").json() == {"items": [], "total": 0}


def test_changes_shell_fields_frozen(client: TestClient) -> None:
    body = client.get("/projects/1/changes", params={"since": "abc"}).json()
    assert body["since"] == "abc"
    assert body["files"] == {"added": [], "modified": [], "deleted": []}
    assert set(body) == {
        "since",
        "head",
        "summary",
        "files",
        "changed_symbols",
        "impacted",
        "tests",
        "stale_design_decisions",
    }


# ─── POST /projects（异步建索引） ──────────────────────────────


def test_create_project_rejects_missing_dir(client: TestClient, data_dir: Path) -> None:
    res = client.post("/projects", json={"root_path": "D:/definitely/not/here"})
    assert res.status_code == 400
    assert err(res.json())["code"] == "bad_request"


def test_create_project_indexes_and_becomes_ready(
    client: TestClient, tmp_path: Path, data_dir: Path
) -> None:
    """引擎合入后：真实建索引，状态如实变成 ready，库里真的有符号。"""
    repo = tmp_path / "arepo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "core.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )

    res = client.post("/projects", json={"root_path": str(repo), "name": "arepo"})
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "indexing"
    assert body["name"] == "arepo"

    detail = client.get(f"/projects/{body['id']}").json()
    assert detail["status"] == "ready"

    conn = sqlite3.connect(db_path(data_dir))
    try:
        quals = {
            row[0]
            for row in conn.execute(
                "SELECT qualname FROM symbol WHERE project_id = ?", (body["id"],)
            )
        }
        assert "pkg.core.helper" in quals
    finally:
        conn.close()


def test_create_project_honestly_fails_when_engine_raises(
    client: TestClient, tmp_path: Path, data_dir: Path, monkeypatch
) -> None:
    """引擎抛异常时：状态如实为 failed，错误信息可读——绝不假装 ready。"""

    def _boom(conn, project_id, root_path, ref):
        raise RuntimeError("索引引擎炸了")

    monkeypatch.setattr(indexing, "_ENGINE_CALLABLE", _boom)

    repo = tmp_path / "arepo"
    repo.mkdir()
    res = client.post("/projects", json={"root_path": str(repo), "name": "arepo"})
    body = res.json()

    detail = client.get(f"/projects/{body['id']}").json()
    assert detail["status"] == "failed"
    conn = sqlite3.connect(db_path(data_dir))
    try:
        stats = json.loads(
            conn.execute(
                "SELECT stats_json FROM index_run WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                (body["id"],),
            ).fetchone()[0]
        )
        assert "索引引擎炸了" in stats["detail"]
    finally:
        conn.close()


def test_create_project_rejects_duplicate_name(client: TestClient, tmp_path: Path) -> None:
    repo = tmp_path / "dup"
    repo.mkdir()
    assert (
        client.post("/projects", json={"root_path": str(repo), "name": "demo"}).status_code == 400
    )
