"""工作区问答不依赖索引；历史、选区和API均以已保存字节为准。"""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from codeinsight.agent.exploration import normalize
from codeinsight.agent.selection import code_selection
from codeinsight.agent.source_scope import source_scope
from codeinsight.agent.tool import ToolContext
from codeinsight.agent.tools import ToolServices, build_tools
from codeinsight.api.app import create_app
from codeinsight.cognitive.indexing.source_store import SourceError
from codeinsight.cognitive.workspace import list_paths, read_current, read_workspace
from codeinsight.llm.provider import StreamChunk, ToolCall


@pytest.fixture
def workspace(conn, tmp_path):
    root = tmp_path / "unindexed"
    root.mkdir()
    (root / "new.py").write_text('def run():\n    return "中文😀"\n', encoding="utf-8")
    (root / "experiments").mkdir()
    (root / "experiments" / "score_output.txt").write_text(
        "MRR=0.75\nRecall=0.9\n", encoding="utf-8"
    )
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(1,'unindexed',?)", (str(root),))
    conn.commit()
    return root


@pytest.mark.asyncio
async def test_unindexed_directory_search_and_read_are_independent(conn, workspace):
    services = ToolServices(conn, 1, str(workspace))
    tools = build_tools(services)
    ctx = ToolContext(1, str(workspace))
    listing = await tools.get("list_files").run({}, ctx)
    assert "new.py" in listing.data["paths"]
    search = await tools.get("search_files").run({"query": "MRR", "pattern": "experiments"}, ctx)
    assert "MRR=0.75" in search.content
    item = search.data["citations"][0]
    assert item["source_kind"] == "workspace" and len(item["content_sha256"]) == 64
    assert conn.execute("SELECT COUNT(*) FROM file").fetchone()[0] == 0
    read = await tools.get("read_file").run({"path": "new.py"}, ctx)
    assert not read.error and "中文😀" in read.content
    workspace.joinpath("new.py").write_text("new content", encoding="utf-8")
    again = await tools.get("read_file").run({"path": "new.py"}, ctx)
    assert "中文😀" in again.content and again.data["citations"] == read.data["citations"]


async def test_request_versions_and_unindexed_exploration_targets(conn, workspace):
    tools = build_tools(ToolServices(conn, 1, str(workspace)))
    ctx = ToolContext(1, str(workspace))
    with source_scope():
        first = await tools.get("read_file").run({"path": "new.py"}, ctx)
        citation = first.data["citations"][0]
        workspace.joinpath("new.py").write_text("version = 2\n", encoding="utf-8")
        same = await tools.get("read_file").run({"path": "new.py"}, ctx)
        assert "中文😀" in same.content
        raw = {
            "actions": [
                {"kind": "code", "label": "看实现", "target": {"path": "new.py", "lineno": 1}}
            ]
        }
        resolved = normalize(conn, 1, raw)["actions"][0]
        assert resolved["dependency"] == "source"
        assert resolved["target"]["content_sha256"] == citation["content_sha256"]
        assert "source_ref" in citation and citation["source_ref"] in first.content
        for target in (
            {"source_ref": "missing"},
            {"source_ref": []},
            {"source_ref": citation["source_ref"], "lineno": 999},
            {"source_ref": citation["source_ref"], "lineno": 1, "end_lineno": 999},
            {"source_ref": citation["source_ref"], "project_id": 99},
        ):
            assert not normalize(
                conn, 1, {"actions": [{"kind": "code", "label": "错误", "target": target}]}
            )["actions"]
    with source_scope():
        fresh = await tools.get("read_file").run({"path": "new.py"}, ctx)
        assert "version = 2" in fresh.content
    for target in (
        {**citation["target"], "end_lineno": 999},
        {**citation["target"], "source_ref": citation["source_ref"]},
    ):
        assert not normalize(
            conn, 1, {"actions": [{"kind": "code", "label": "错误", "target": target}]}
        )["actions"]


async def test_multiple_observed_versions_require_source_ref(conn, workspace):
    tools = build_tools(ToolServices(conn, 1, str(workspace)))
    ctx = ToolContext(1, str(workspace))
    old = read_workspace(conn, 1, "new.py")
    workspace.joinpath("new.py").write_text("version = 2\n", encoding="utf-8")
    with source_scope():
        first = await tools.get("read_file").run({"path": "new.py"}, ctx)
        second = await tools.get("read_file").run(
            {"path": "new.py", "source_kind": "workspace", "content_sha256": old.sha256}, ctx
        )

        def action(t):
            return normalize(conn, 1, {"actions": [{"kind": "code", "label": "读", "target": t}]})[
                "actions"
            ]

        assert not action({"path": "new.py", "lineno": 1})
        assert (
            action({"source_ref": first.data["citations"][0]["source_ref"], "lineno": 1})[0][
                "target"
            ]["content_sha256"]
            != old.sha256
        )
        assert (
            action({"source_ref": second.data["citations"][0]["source_ref"], "lineno": 1})[0][
                "target"
            ]["content_sha256"]
            == old.sha256
        )


async def test_concurrent_scopes_do_not_clear_each_others_versions(conn, workspace):
    import asyncio

    from codeinsight.agent.source_scope import CURRENT_SCOPE

    ready = asyncio.Event()

    async def first():
        with source_scope() as scope:
            scope.versions["new.py"] = "first"
            ready.set()
            await asyncio.sleep(0.01)
            assert CURRENT_SCOPE.get() is scope and scope.versions["new.py"] == "first"

    async def second():
        await ready.wait()
        with source_scope() as scope:
            assert not scope.versions
            scope.versions["new.py"] = "second"

    await asyncio.gather(first(), second())


def test_current_read_and_history_survive_modification_and_removed_root(conn, workspace):
    old = read_workspace(conn, 1, "new.py")
    workspace.joinpath("new.py").write_bytes(b"changed\n")
    assert read_workspace(conn, 1, "new.py").sha256 != old.sha256
    workspace.joinpath("new.py").unlink()
    assert read_workspace(conn, 1, "new.py", old.sha256).raw == old.raw
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(2,'other',?)", (str(workspace),))
    conn.commit()
    with pytest.raises(SourceError):
        read_workspace(conn, 2, "new.py", old.sha256)
    with pytest.raises(SourceError):
        read_workspace(conn, 1, "another.py", old.sha256)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        "/outside.py",
        "C:\\outside.py",
        "new.py:secret",
        ".env",
        "nested/.env.local",
        "id_rsa",
        "secret.key",
        "node_modules/a.py",
    ],
)
def test_workspace_rejects_escape_caches_and_secrets(conn, workspace, path):
    with pytest.raises(SourceError):
        read_workspace(conn, 1, path)


def test_binary_size_and_symlink_are_not_read(conn, workspace, tmp_path):
    workspace.joinpath("binary.data").write_bytes(b"abc\0def")
    workspace.joinpath("huge.txt").write_bytes(b"x" * 2_000_001)
    for path in ("binary.data", "huge.txt"):
        with pytest.raises(SourceError):
            read_current(str(workspace), path)
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    try:
        workspace.joinpath("link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("当前Windows用户不能创建符号链接")
    with pytest.raises(SourceError):
        read_workspace(conn, 1, "link.txt")


def test_utf16_selection_uses_saved_workspace_bytes(conn, workspace):
    source = read_workspace(conn, 1, "new.py")
    workspace.joinpath("new.py").write_text("changed", encoding="utf-8")
    raw = {
        "path": "new.py",
        "source_kind": "workspace",
        "content_sha256": source.sha256,
        "lineno": 2,
        "end_lineno": 2,
        "selection": {"start_column": 13, "end_column": 17},
    }
    assert code_selection(conn, 1, raw, 100) == "中文😀"
    raw["content_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        code_selection(conn, 1, raw, 100)


def test_workspace_code_api_versions_and_new_file_tree(conn, workspace):
    with TestClient(create_app()) as client:
        response = client.get("/projects/1/code", params={"path": "new.py"})
        assert response.status_code == 200
        old = response.json()
        assert old["source_kind"] == "workspace" and "index_epoch" not in old
        workspace.joinpath("new.py").write_text("changed", encoding="utf-8")
        history = client.get(
            "/projects/1/code",
            params={
                "path": "new.py",
                "source_kind": "workspace",
                "content_sha256": old["content_sha256"],
            },
        ).json()
        assert history["content"] == old["content"]
        tree = client.get("/projects/1/files?source_kind=workspace").json()
        assert {f["path"] for f in tree} == {"new.py", "experiments/score_output.txt"}


class WorkspaceProvider:
    model_id = "offline-workspace"

    def __init__(self):
        self.calls = 0

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield StreamChunk(
                tool_calls=[
                    ToolCall("s", "search_files", {"query": "MRR", "pattern": "experiments"})
                ]
            )
        elif self.calls == 2:
            yield StreamChunk(
                tool_calls=[ToolCall("r", "read_file", {"path": "experiments/score_output.txt"})]
            )
        else:
            yield StreamChunk(
                text="本次结果记录的MRR为0.75 [experiments/score_output.txt:1]。单次成绩不能证明所有配置都更好。",
                finish_reason="stop",
            )


@pytest.mark.parametrize("streaming", [False, True])
def test_real_query_assembly_without_index_and_source_identity(
    conn, workspace, monkeypatch, streaming
):
    from codeinsight.api import query

    monkeypatch.setattr(query, "_PROVIDER_FACTORY", WorkspaceProvider)
    with TestClient(create_app()) as client:
        response = client.post(
            "/query/stream" if streaming else "/query",
            json={"project_id": 1, "question": "成绩如何？"},
        )
        assert response.status_code == 200
        if streaming:
            frames = response.text.split("\n\n")
            answer = next(
                json.loads(f.split("data: ")[1]) for f in frames if f.startswith("event: answer\n")
            )
        else:
            answer = response.json()
        assert "0.75" in answer["text"] and not answer.get("abstained")
        citation = answer["citations"][0]
        assert citation["source_kind"] == "workspace" and citation["index_epoch"] is None
        assert (
            citation["content_sha256"]
            == hashlib.sha256(
                workspace.joinpath("experiments/score_output.txt").read_bytes()
            ).hexdigest()
        )
        assert any(e["source_kind"] == "workspace" for e in answer["evidence"])


def test_directory_scan_reports_limits(workspace):
    paths, truncated = list_paths(str(workspace), limit=1)
    assert len(paths) == 1 and truncated
