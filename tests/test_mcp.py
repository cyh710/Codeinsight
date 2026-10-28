"""MCP Server（源文档 §2.7-3 / ADR 0008）。

这里测**分发层**：工具目录翻得对不对、调用能不能落到 ToolRegistry、
失败会不会变成可读错误。协议层（initialize / list_tools / call_tool
的 JSON-RPC 往返）用官方 `mcp` 客户端手工验证过：

    stdio_client → ClientSession.initialize() → 15 个工具
    → call_tool("search_code") 返回文本 + structured_content.citations

不把协议往返写进测试，是因为它要起子进程跑 `uv run ci mcp`，
在 CI 上比被测逻辑本身更脆弱。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codeinsight.agent.service import ProjectNotFound
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.mcp.server import call_tool, list_tools, open_runtime

CORE_PY = '''\
"""核心逻辑。"""


def helper() -> int:
    """帮忙。"""
    return 1
'''

MAIN_PY = '''\
"""入口。"""

from pkg.core import helper


def main() -> int:
    """跑一下。"""
    return helper()
'''


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def indexed_db(tmp_path: Path) -> Path:
    repo = tmp_path / "demo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "core.py").write_text(CORE_PY, encoding="utf-8")
    (repo / "pkg" / "main.py").write_text(MAIN_PY, encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    db = tmp_path / "ci.db"
    index_project(db, root=repo, name="demo")
    return db


@pytest.fixture
def runtime(indexed_db: Path):
    rt = open_runtime(None, db=indexed_db)
    try:
        yield rt
    finally:
        rt.close()


def test_tool_catalog_is_derived_from_the_registry(runtime) -> None:
    tools = list_tools(runtime)
    names = [tool.name for tool in tools]
    assert "search_code" in names
    assert "get_changes" in names
    assert "search_knowledge" in names  # B 线接入后注册的知识工具
    assert names[-1] == "list_projects"
    assert len(tools) == len(runtime.registry) + 1

    search = next(tool for tool in tools if tool.name == "search_code")
    # schema 原样搬运：注册表里怎么写的，MCP 就怎么看到。
    assert search.input_schema["required"] == ["query"]


@pytest.mark.asyncio
async def test_call_tool_dispatches_and_returns_citations(runtime) -> None:
    result = await call_tool(runtime, "find_symbol", {"name": "helper"})
    assert result.is_error is False
    assert "pkg.core.helper" in result.content[0].text
    citations = (result.structured_content or {}).get("citations") or []
    assert citations and citations[0]["path"] == "pkg/core.py"


@pytest.mark.asyncio
async def test_unknown_tool_is_a_readable_error(runtime) -> None:
    result = await call_tool(runtime, "nope", {})
    assert result.is_error is True
    assert "search_code" in result.content[0].text


@pytest.mark.asyncio
async def test_list_projects_marks_the_bound_one(runtime) -> None:
    result = await call_tool(runtime, "list_projects", {})
    data = result.structured_content or {}
    assert data["bound"] == "demo"
    assert data["items"][0]["name"] == "demo"
    assert data["items"][0]["bound"] is True
    assert data["items"][0]["symbols"] >= 3


def test_two_projects_without_flag_is_an_explicit_error(indexed_db: Path) -> None:
    """有多个项目时必须让用户选——猜一个去回答比报错糟得多。"""
    index_project(indexed_db, root=indexed_db.parent / "demo", name="second")
    with pytest.raises(ProjectNotFound) as excinfo:
        open_runtime(None, db=indexed_db)
    assert "second" in str(excinfo.value)


async def test_mcp_default_reads_fresh_and_explicit_target_restores_original(runtime):
    path = Path(runtime.session.repo_root) / "new.txt"
    path.write_text("version = 1\n", encoding="utf-8")
    first = await call_tool(runtime, "read_file", {"path": "new.txt"})
    old = first.structured_content["citations"][0]["target"]
    path.write_text("version = 2\n", encoding="utf-8")
    second = await call_tool(runtime, "read_file", {"path": "new.txt"})
    assert not second.is_error and "version = 2" in second.content[0].text
    restored = await call_tool(runtime, "read_file", {"target": old})
    assert not restored.is_error and "version = 1" in restored.content[0].text
    again = await call_tool(runtime, "read_file", {"path": "new.txt"})
    assert "version = 2" in again.content[0].text
    foreign = await call_tool(runtime, "read_file", {"target": {**old, "project_id": 99}})
    assert foreign.is_error
