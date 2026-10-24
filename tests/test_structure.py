"""关系图与时间线端点（契约 §4.5 / §7.2）。

图的核心承诺有两条：**能走到的节点要在**，**走不到的要明说没走**。
所以除了「返回了什么」，这里还断言 `truncated` 与节点预算的关系。
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from codeinsight.api.app import create_app


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> sqlite3.Connection:
    c = conn
    c.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'demo', 'D:/nowhere/demo')")
    c.execute("INSERT INTO project (id, name, root_path) VALUES (2, 'empty', 'D:/nowhere/empty')")
    c.execute(
        "INSERT INTO repo_state (project_id, head_commit, head_branch, indexed_at, parser_version)"
        " VALUES (1, 'zzz999', 'main', '2026-10-22T08:00:00Z', 't')"
    )
    c.executemany(
        "INSERT INTO file (id, project_id, path, language, content_sha256) VALUES (?, 1, ?, 'python', ?)",
        [
            (1, "src/a.py", "sha-a"),
            (2, "src/b.py", "sha-b"),
            (3, "src/c.py", "sha-c"),
        ],
    )
    # 1 → 2 → 5 是调用链；3 → 1 是反向调用；4 是 1 的不确定被调；6 是孤岛。
    c.executemany(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " is_async, is_private, is_dunder, n_lines, source_sha256)"
        " VALUES (?, 1, ?, ?, ?, ?, ?, ?, 0, 0, 0, 1, 'sha')",
        [
            (1, 1, "src.a.entry", "entry", "function", 1, 4),
            (2, 1, "src.a.helper", "helper", "function", 5, 8),
            (3, 2, "src.b.worker", "worker", "method", 10, 14),
            (4, 2, "src.b.runner", "runner", "function", 20, 24),
            (5, 3, "src.c.deep", "deep", "function", 1, 3),
            (6, 3, "src.c.island", "island", "function", 9, 11),
        ],
    )
    c.executemany(
        "INSERT INTO edge (project_id, src_symbol_id, dst_symbol_id, src_qualname, dst_name,"
        " dst_qualname, kind, lineno, confidence) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 2, "src.a.entry", "helper", "src.a.helper", "call", 2, 1.0),
            (3, 1, "src.b.worker", "entry", "src.a.entry", "call", 12, 1.0),
            (1, 4, "src.a.entry", "runner", "src.b.runner", "call", 3, 0.6),
            (3, 2, "src.b.worker", "helper", "src.a.helper", "references", 13, 1.0),
            (2, 5, "src.a.helper", "deep", "src.c.deep", "call", 6, 1.0),
            (1, None, "src.a.entry", "getattr", None, "call", 4, 0.5),
        ],
    )
    c.execute(
        "INSERT INTO concept (id, name, category, summary, principles, tradeoffs, alternatives,"
        " detection_json, references_json)"
        " VALUES ('demo-async', '异步', 'async', '并发等待。', 'p', 't', 'a', '{}', '[]')"
    )
    c.execute(
        "INSERT INTO concept (id, name, category, summary, principles, tradeoffs, alternatives,"
        " detection_json, references_json)"
        " VALUES ('demo-cache', '缓存', 'cache', '挡住重复计算。', 'p', 't', 'a', '{}', '[]')"
    )
    c.executemany(
        "INSERT INTO concept_instance (project_id, concept_id, symbol_id, path, lineno,"
        " qualname, evidence, confidence) VALUES (1, ?, ?, ?, ?, ?, 'rule', 1.0)",
        [
            ("demo-async", 1, "src/a.py", 1, "src.a.entry"),
            ("demo-cache", 2, "src/a.py", 5, "src.a.helper"),
        ],
    )
    c.commit()
    return c


@pytest.fixture
def client(seeded: sqlite3.Connection) -> TestClient:
    return TestClient(create_app())


# ─── 关系图 ───────────────────────────────────────────────────


def test_graph_focus_depth_one(client: TestClient) -> None:
    body = client.get("/projects/1/graph", params={"qualname": "src.a.entry", "depth": 1}).json()
    assert body["mode"] == "focus"
    assert body["center"] == {"qualname": "src.a.entry", "path": "src/a.py", "lineno": 1}
    # 中心恒在第一位：前端据此决定初始视口。
    assert [n["qualname"] for n in body["nodes"]][0] == "src.a.entry"
    names = {n["qualname"] for n in body["nodes"]}
    assert names == {"src.a.entry", "src.a.helper", "src.b.worker", "src.b.runner"}
    assert all(n["depth"] == 1 for n in body["nodes"][1:])
    assert body["truncated"] is False
    # 未解析到符号的调用（getattr）不进图：图上不能有悬空节点。
    assert all("getattr" not in e for e in body["edges"])


def test_graph_depth_two_reaches_transitive_callee(client: TestClient) -> None:
    body = client.get("/projects/1/graph", params={"qualname": "src.a.entry", "depth": 2}).json()
    depths = {n["qualname"]: n["depth"] for n in body["nodes"]}
    assert depths["src.c.deep"] == 2  # entry → helper → deep
    assert "src.c.island" not in depths


def test_graph_edge_kind_filter(client: TestClient) -> None:
    body = client.get(
        "/projects/1/graph", params={"qualname": "src.a.entry", "kinds": "call"}
    ).json()
    assert {e["kind"] for e in body["edges"]} == {"call"}
    # worker → helper 是 references 边：只留 references 时，
    # 不沿 call 边扩散，邻域就缩到这两个节点。
    body_references = client.get(
        "/projects/1/graph", params={"qualname": "src.a.helper", "kinds": "references"}
    ).json()
    assert {e["kind"] for e in body_references["edges"]} == {"references"}
    assert {n["qualname"] for n in body_references["nodes"]} == {
        "src.a.helper",
        "src.b.worker",
    }


def test_graph_marks_uncertain_edge(client: TestClient) -> None:
    body = client.get("/projects/1/graph", params={"qualname": "src.a.entry"}).json()
    uncertain = [e for e in body["edges"] if e["uncertain"]]
    assert [e["dst"] for e in uncertain] == [4]
    assert uncertain[0]["confidence"] == 0.6


def test_graph_attaches_concept_ids(client: TestClient) -> None:
    body = client.get("/projects/1/graph", params={"qualname": "src.a.entry"}).json()
    by_name = {n["qualname"]: n for n in body["nodes"]}
    assert by_name["src.a.entry"]["concept_ids"] == ["demo-async"]
    assert by_name["src.a.helper"]["concept_ids"] == ["demo-cache"]
    assert by_name["src.b.worker"]["concept_ids"] == []


def test_graph_truncation_is_reported(client: TestClient) -> None:
    body = client.get(
        "/projects/1/graph", params={"qualname": "src.a.entry", "max_nodes": 2}
    ).json()
    assert len(body["nodes"]) == 2
    assert body["truncated"] is True


def test_graph_overview_without_qualname(client: TestClient) -> None:
    body = client.get("/projects/1/graph", params={"max_nodes": 3}).json()
    assert body["mode"] == "overview"
    assert body["center"] is None
    assert body["depth"] is None
    assert [n["qualname"] for n in body["nodes"]] == [
        "src.a.entry",
        "src.a.helper",
        "src.b.runner",
    ]
    assert all(n["depth"] is None for n in body["nodes"])
    # 6 个公开函数/方法，只取 3 个——必须承认截断。
    assert body["truncated"] is True


def test_graph_unknown_symbol_and_bad_params(client: TestClient) -> None:
    res = client.get("/projects/1/graph", params={"qualname": "no.such"})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "symbol_not_found"

    bad_kind = client.get("/projects/1/graph", params={"kinds": "call,telepathy"})
    assert bad_kind.status_code == 400
    assert bad_kind.json()["error"]["code"] == "bad_request"

    bad_depth = client.get("/projects/1/graph", params={"depth": 9})
    assert bad_depth.status_code == 400


def test_graph_empty_project(client: TestClient) -> None:
    body = client.get("/projects/2/graph").json()
    assert body["nodes"] == [] and body["edges"] == []
    assert body["truncated"] is False


# ─── 时间线 ───────────────────────────────────────────────────


@pytest.fixture
def seeded_timeline(seeded: sqlite3.Connection) -> sqlite3.Connection:
    c = seeded
    c.execute(
        "INSERT INTO index_run (id, project_id, head_commit, mode, started_at, finished_at, ok,"
        " files_total, symbols_added) VALUES (1, 1, 'c0', 'full',"
        " '2026-10-20 10:00:00', '2026-10-20 10:00:31', 1, 10, 30)"
    )
    c.execute(
        "INSERT INTO index_run (id, project_id, base_commit, head_commit, mode, started_at,"
        " finished_at, ok, files_total, files_changed, symbols_added, stats_json)"
        " VALUES (2, 1, 'c0', 'c1', 'incremental', '2026-10-21T09:00:00+00:00',"
        " '2026-10-21 09:00:20', 1, 10, 5, 3,"
        ' \'{"changed_symbols": 7, "stale_design_decisions": 1}\')'
    )
    c.execute(
        "INSERT INTO change_record (id, project_id, commit_sha, source, summary, occurred_at,"
        " added_json, removed_json, modified_json) VALUES (1, 1, 'c1', 'git', '新增队列',"
        " '2026-10-21 09:00:05',"
        ' \'{"files": ["a.py"], "symbols": [{"qualname": "x"}]}\','
        ' \'{"files": ["b.py"], "symbols": []}\','
        ' \'{"files": ["c.py"], "symbols": [{"qualname": "y"}, {"qualname": "z"}]}\')'
    )
    c.execute(
        "INSERT INTO staleness_report (project_id, commit_sha, total_chunks, stale_chunks,"
        " stale_rate, by_reason) VALUES (1, 'c1', 100, 0, 0.0,"
        ' \'{"design_decisions": [{"doc_id": "0001", "title": "旧设计",'
        ' "reason": "证据消失"}]}\')'
    )
    c.execute(
        "INSERT INTO change_record (id, project_id, commit_sha, source, summary, occurred_at,"
        " added_json, removed_json, modified_json) VALUES (2, 1, 'c2', 'external_agent',"
        " '外部 agent 记账', '2026-10-22 08:00:00', '', '', '')"
    )
    c.commit()
    return c


def test_timeline_merges_runs_and_external_changes(
    seeded_timeline: sqlite3.Connection, client: TestClient
) -> None:
    body = client.get("/projects/1/timeline").json()
    assert body["head"] == "zzz999"
    ids = [item["id"] for item in body["items"]]
    assert ids == ["change-2", "run-2", "run-1"]

    external = body["items"][0]
    assert external["kind"] == "change"
    assert external["source"] == "external_agent"

    incremental = body["items"][1]
    assert incremental["mode"] == "incremental"
    assert incremental["files"] == {"added": 1, "modified": 1, "deleted": 1, "total": 3}
    assert incremental["symbols_changed"] == 3
    assert incremental["summary"] == "新增队列"
    # change_record 的时间优先于 index_run（同一动作的起点）
    assert incremental["at"] == "2026-10-21T09:00:05Z"
    assert incremental["stale_design_decisions"] == [{"doc_id": "0001", "title": "旧设计"}]

    full = body["items"][2]
    assert full["mode"] == "full"
    assert full["files"]["added"] is None
    assert full["files"]["total"] == 10
    assert full["symbols_changed"] is None
    assert full["summary"].startswith("全量索引")
    assert full["at"] == "2026-10-20T10:00:31Z"


def test_timeline_empty_project(seeded_timeline: sqlite3.Connection, client: TestClient) -> None:
    body = client.get("/projects/2/timeline").json()
    assert body == {"items": [], "total": 0, "head": None}
