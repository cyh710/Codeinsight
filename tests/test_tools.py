"""只读工具（A13）。

口径：
- 找得到的时候给 `file:line`；找不到的时候给**可执行的中文建议**，不抛异常。
- 调用关系的引用落在**调用点**（源文件那一行），不是被调符号的定义行——
  这两个混了，用户点过去会看到另一个文件。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codeinsight.agent.tool import ToolContext
from codeinsight.agent.tools import ToolServices, build_tools
from codeinsight.agent.tools_code import (
    FindSymbolTool,
    GetCalleesTool,
    GetCallersTool,
    ReadFileTool,
)
from codeinsight.agent.tools_knowledge import FindConceptInstancesTool, ListConceptsTool
from codeinsight.agent.tools_project import GetFlowTool
from codeinsight.storage.sqlite import apply_schema, open_sqlite

SOURCE_A = "\n".join(f"line {i}" for i in range(1, 31)) + "\n"


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = open_sqlite(":memory:", row_factory=True)
    apply_schema(c)
    c.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'demo', '/tmp/demo')")
    c.executemany(
        "INSERT INTO file (id, project_id, path, language, content_sha256, line_count)"
        " VALUES (?, 1, ?, 'python', 'h', ?)",
        [(1, "a.py", 30), (2, "b.py", 10)],
    )
    c.executemany(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " header, docstring, source_sha256)"
        " VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'h')",
        [
            (1, 1, "a.run", "run", "function", 3, 9, "def run():", "入口"),
            (2, 1, "a.helper", "helper", "function", 12, 20, "def helper():", ""),
            (3, 2, "b.call_run", "call_run", "function", 4, 6, "def call_run():", ""),
        ],
    )
    c.executemany(
        "INSERT INTO edge (project_id, src_symbol_id, dst_symbol_id, src_qualname, dst_name,"
        " dst_qualname, kind, lineno, confidence)"
        " VALUES (1, ?, ?, ?, ?, ?, 'call', ?, ?)",
        [
            (3, 1, "b.call_run", "run", "a.run", 5, 1.0),
            (1, 2, "a.run", "helper", "a.helper", 7, 0.6),
        ],
    )
    c.execute(
        "INSERT INTO flow (id, project_id, name, description) VALUES (1, 1, '主流程', '从入口到退出')"
    )
    c.executemany(
        "INSERT INTO flow_step (flow_id, ordinal, qualname, path, lineno, note) VALUES (1, ?, ?, ?, ?, ?)",
        [(1, "a.run", "a.py", 3, "入口"), (2, "a.helper", "a.py", 12, "调用 helper")],
    )
    c.execute("UPDATE flow SET entry_symbol_id=1")
    c.execute("UPDATE flow_step SET symbol_id=CASE ordinal WHEN 1 THEN 1 ELSE 2 END")
    c.execute(
        "INSERT INTO concept (id, name, category, summary, detection_json)"
        " VALUES ('jwt', 'JWT', 'auth', '签名令牌', '{}')"
    )
    c.execute(
        "INSERT INTO concept_instance (project_id, concept_id, symbol_id, file_id, path, lineno,"
        " qualname, evidence, confidence) VALUES (1, 'jwt', 1, 1, 'a.py', 5, 'a.run',"
        " 'call jwt.decode', 1.0)"
    )
    c.commit()
    return c


def _services(conn, tmp_path: Path) -> ToolServices:
    conn.execute("UPDATE project SET root_path=? WHERE id=1", (str(tmp_path),))
    return ToolServices(conn=conn, project_id=1, repo_root=str(tmp_path))


def _ctx() -> ToolContext:
    return ToolContext(project_id=1, repo_root="")


async def test_find_symbol_by_name_and_qualname(conn, tmp_path) -> None:
    tool = FindSymbolTool(_services(conn, tmp_path))
    result = await tool.run({"name": "helper"}, _ctx())
    assert result.error is None
    assert result.data["items"][0]["qualname"] == "a.helper"
    assert result.data["citations"][0]["path"] == "a.py"

    by_qualname = await tool.run({"name": "b.call_run"}, _ctx())
    assert by_qualname.data["items"][0]["path"] == "b.py"


async def test_find_symbol_missing_gives_actionable_error(conn, tmp_path) -> None:
    tool = FindSymbolTool(_services(conn, tmp_path))
    result = await tool.run({"name": "nothing_here"}, _ctx())
    assert result.error == "not_found"
    assert "search_code" in result.content


async def test_callers_point_at_the_call_site(conn, tmp_path) -> None:
    tool = GetCallersTool(_services(conn, tmp_path))
    result = await tool.run({"symbol": "run"}, _ctx())
    assert result.error is None
    item = result.data["items"][0]
    assert item["src_qualname"] == "b.call_run"
    assert item["src_path"] == "b.py"
    assert item["lineno"] == 5
    # 引用必须是「调用点所在文件那一行」，不是 a.run 的定义行。
    assert result.data["citations"][0] == {
        "source_kind": "index",
        "index_epoch": 0,
        "head_commit": None,
        "path": "b.py",
        "lineno": 5,
        "end_lineno": 5,
        "qualname": "b.call_run",
    }


async def test_callees_mark_uncertain_edges(conn, tmp_path) -> None:
    tool = GetCalleesTool(_services(conn, tmp_path))
    result = await tool.run({"symbol": "run"}, _ctx())
    item = result.data["items"][0]
    assert item["dst_qualname"] == "a.helper"
    assert item["uncertain"] is True  # confidence 0.6
    assert "⚠" in result.content


async def test_read_file_numbers_lines(conn, tmp_path) -> None:
    import hashlib

    (tmp_path / "a.py").write_text(SOURCE_A, encoding="utf-8")
    conn.execute(
        "UPDATE file SET content_sha256 = ? WHERE project_id = 1 AND path = 'a.py'",
        (hashlib.sha256((tmp_path / "a.py").read_bytes()).hexdigest(),),
    )
    tool = ReadFileTool(_services(conn, tmp_path))
    result = await tool.run({"path": "a.py", "start_line": 3, "end_line": 5}, _ctx())
    assert result.error is None
    assert "3  line 3" in result.content
    assert "5  line 5" in result.content
    assert result.data["citations"][0]["lineno"] == 3


async def test_read_file_does_not_cite_changed_unindexed_source(conn, tmp_path) -> None:
    import hashlib

    conn.execute(
        "UPDATE file SET content_sha256=? WHERE path='a.py'",
        (hashlib.sha256(SOURCE_A.encode()).hexdigest(),),
    )
    (tmp_path / "a.py").write_text("changed source", encoding="utf-8")
    result = await ReadFileTool(_services(conn, tmp_path)).run(
        {"path": "a.py", "source_kind": "index"}, _ctx()
    )
    assert result.error == "stale_source" and not result.data.get("citations")


async def test_read_file_does_not_create_out_of_range_citation(conn, tmp_path) -> None:
    (tmp_path / "a.py").write_text(SOURCE_A, encoding="utf-8")
    result = await ReadFileTool(_services(conn, tmp_path)).run(
        {"path": "a.py", "start_line": 10000}, _ctx()
    )
    assert result.error == "bad_request" and not result.data.get("citations")


async def test_read_file_rejects_unknown_path(conn, tmp_path) -> None:
    tool = ReadFileTool(_services(conn, tmp_path))
    result = await tool.run({"path": "../../etc/passwd"}, _ctx())
    assert result.error == "not_found"


async def test_get_flow_lists_and_expands(conn, tmp_path) -> None:
    tool = GetFlowTool(_services(conn, tmp_path))
    listing = await tool.run({}, _ctx())
    assert listing.data["items"][0]["name"] == "主流程"

    expanded = await tool.run({"flow_name": "主"}, _ctx())
    assert [step["ordinal"] for step in expanded.data["steps"]] == [1, 2]
    assert expanded.data["citations"][0]["path"] == "a.py"


async def test_list_concepts_counts_instances(conn, tmp_path) -> None:
    tool = ListConceptsTool(_services(conn, tmp_path))
    result = await tool.run({}, _ctx())
    assert result.data["items"][0]["concept_id"] == "jwt"
    assert result.data["items"][0]["instance_count"] == 1


async def test_find_concept_instances(conn, tmp_path) -> None:
    tool = FindConceptInstancesTool(_services(conn, tmp_path))
    result = await tool.run({"concept_id": "jwt"}, _ctx())
    assert result.data["items"][0]["evidence"] == "call jwt.decode"
    assert result.data["citations"][0]["lineno"] == 5


async def test_concept_uncertainty_is_in_model_text_not_only_metadata(conn, tmp_path) -> None:
    conn.execute("UPDATE concept_instance SET confidence = 0.4")
    result = await FindConceptInstancesTool(_services(conn, tmp_path)).run(
        {"concept_id": "jwt"}, _ctx()
    )
    assert "待核对" in result.content and "confidence=0.4" in result.content
    assert result.data["items"][0]["confidence"] == 0.4


async def test_registry_has_fifteen_readonly_tools(conn, tmp_path) -> None:
    registry = build_tools(_services(conn, tmp_path))
    assert len(registry) == 15
    assert all(tool.mutating is False for tool in registry)
    assert "search_code" in registry.names
    assert len(registry.schemas()) == 15
