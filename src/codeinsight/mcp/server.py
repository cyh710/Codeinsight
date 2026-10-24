"""MCP stdio server：工具目录与调用分发。

为什么用低层 `Server` 而不是 FastMCP 的装饰器：我们的工具是**数据驱动**的
（`ToolRegistry` 里已经是 name / description / JSON Schema），
逐个写 `@mcp.tool()` 包装函数等于把同一份 schema 抄两遍，
迟早出现「注册表里的参数说明」和「MCP 看到的参数说明」不一致。

这里只做三件事：

1. `list_tools`：把注册表原样翻成 `types.Tool`。
2. `call_tool`：按名字分发到 `Tool.run()`，把 `content` 给模型、
   `data`（含 `file:line` 引用）放进 `structured_content`。
3. `list_projects`：让外部 agent 知道自己连的是哪个项目、还有哪些可选。

**stdout 是协议通道**：任何日志、警告、print 都必须走 stderr，
否则一行日志就会把 JSON-RPC 流冲坏。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.models import InitializationOptions, ServerCapabilities
from mcp.server.stdio import stdio_server

from codeinsight import __version__
from codeinsight.agent.service import AgentSession, ProjectNotFound, open_agent
from codeinsight.agent.tool import ToolContext, ToolResult
from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path, open_sqlite

__all__ = [
    "McpRuntime",
    "build_server",
    "call_tool",
    "list_tools",
    "open_runtime",
    "run_stdio",
]

INSTRUCTIONS = """\
CodeInsight 是一个本地代码理解服务。它索引过一个真实仓库（符号、调用边、
概念实例、设计说明），你可以用这里的工具查「代码在哪、怎么串起来、为什么这么写」，
而不是靠 grep 猜。

使用建议：
- 先 `search_code` 或 `find_symbol` 定位，再用 `read_file` / `get_callers` 看上下文。
- 任何指向代码的结论都带 `file:line`（在 structured_content 的 citations 里）。
  引用教材内容时不要当作项目事实——教材和项目证据是两套来源。
- `get_changes` 告诉你最近一次索引更新改了什么、影响谁、哪些设计说明已过期。
- 工具都是只读的：改代码、跑命令由你（外部 agent）负责。
"""

LIST_PROJECTS = types.Tool(
    name="list_projects",
    description="列出这个 CodeInsight 实例里已经建过索引的项目，以及当前连接绑定的是哪个。",
    input_schema={"type": "object", "properties": {}, "required": []},
)


@dataclass
class McpRuntime:
    """一个 MCP 进程的生命周期对象：一个项目、一个连接、一张工具表。"""

    session: AgentSession
    bound_project: str
    db: Path

    @property
    def registry(self):
        return self.session.runtime.registry

    def close(self) -> None:
        self.session.close()


def open_runtime(project: str | None, *, db: str | Path | None = None) -> McpRuntime:
    """打开 MCP 运行时。

    `project` 为空时：只有一个项目就用它；有多个则报错并列出可选项——
    猜一个项目去回答，比明确报错糟得多。
    """
    path = Path(db) if db else db_path(settings.data_dir)
    if not path.exists():
        raise FileNotFoundError(f"索引库不存在：{path}（先跑 ci index）")

    name = project or _sole_project(path)
    try:
        session = open_agent(path, name)
    except ProjectNotFound as exc:
        raise ProjectNotFound(
            f"没有名为 {name} 的项目；可用：{', '.join(_project_names(path))}"
        ) from exc
    return McpRuntime(session=session, bound_project=name, db=path)


def _project_names(path: Path) -> list[str]:
    conn = open_sqlite(path)
    try:
        return [row[0] for row in conn.execute("SELECT name FROM project ORDER BY name")]
    finally:
        conn.close()


def _sole_project(path: Path) -> str:
    names = _project_names(path)
    if len(names) == 1:
        return names[0]
    if not names:
        raise ProjectNotFound("这个实例还没有索引任何项目（先跑 ci index）")
    raise ProjectNotFound(
        f"有多个项目，必须用 --project 指定：{', '.join(names)}"
    )


def list_tools(runtime: McpRuntime) -> list[types.Tool]:
    """注册表 → MCP 工具目录。schema 原样翻译，不重写成第二份。"""
    tools = [
        types.Tool(
            name=tool.name,
            description=tool.description,
            input_schema=dict(tool.parameters),
        )
        for tool in runtime.registry
    ]
    tools.append(LIST_PROJECTS)
    return tools


async def call_tool(runtime: McpRuntime, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    """分发一次调用。**不抛异常**：工具失败也要让外部 agent 看到可读原因。"""
    if name == "list_projects":
        return _projects_result(runtime)

    tool = runtime.registry.get(name)
    if tool is None:
        return _text(
            f"没有名为 {name} 的工具。可用：{', '.join(runtime.registry.names)}",
            is_error=True,
        )
    if tool.mutating:
        # v1 全部只读；写工具将来要接审批（ADR 0008），不能悄悄放开。
        return _text(f"{name} 是写操作，当前 MCP 版本不开放。", is_error=True)

    try:
        result: ToolResult = await tool.run(
            arguments,
            ToolContext(
                project_id=runtime.session.project_id,
                repo_root=runtime.session.repo_root,
                conversation_id="mcp",
            ),
        )
    except Exception as exc:  # noqa: BLE001 —— 协议层兜底，绝不把栈回溯塞给客户端
        return _text(f"工具执行失败：{type(exc).__name__}: {exc}", is_error=True)

    structured = _json_safe(result.data) if result.data else None
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=result.content)],
        structured_content=structured,
        is_error=bool(result.error),
    )


def build_server(runtime: McpRuntime) -> Server:
    """装配 MCP server 的两个处理器。"""

    async def on_list_tools(_ctx, _params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=list_tools(runtime))

    async def on_call_tool(_ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        return await call_tool(runtime, params.name, dict(params.arguments or {}))

    return Server(
        "codeinsight",
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def run_stdio(project: str | None, *, db: str | Path | None = None) -> None:
    """在 stdin/stdout 上跑 MCP（Claude Code 就是按这个方式连的）。"""
    runtime = open_runtime(project, db=db)
    server = build_server(runtime)
    options = InitializationOptions(
        server_name="codeinsight",
        server_version=__version__,
        capabilities=ServerCapabilities(tools=types.ToolsCapability(list_changed=False)),
        instructions=INSTRUCTIONS,
    )
    print(
        f"[codeinsight-mcp] 已绑定项目 {runtime.bound_project}，"
        f"{len(runtime.registry)} 个工具；等待客户端…",
        file=sys.stderr,
        flush=True,
    )
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)
    finally:
        runtime.close()


# ── 内部 ──────────────────────────────────────────────────────


def _projects_result(runtime: McpRuntime) -> types.CallToolResult:
    conn = open_sqlite(runtime.db, row_factory=True)
    try:
        rows = conn.execute(
            """
            SELECT p.name, p.root_path, r.head_commit, r.indexed_at,
                   (SELECT COUNT(*) FROM file WHERE project_id = p.id) AS files,
                   (SELECT COUNT(*) FROM symbol WHERE project_id = p.id) AS symbols
            FROM project p LEFT JOIN repo_state r ON r.project_id = p.id
            ORDER BY p.name
            """
        ).fetchall()
    finally:
        conn.close()
    items = [
        {
            "name": row["name"],
            "root_path": row["root_path"],
            "head_commit": row["head_commit"],
            "indexed_at": row["indexed_at"],
            "files": int(row["files"]),
            "symbols": int(row["symbols"]),
            "bound": row["name"] == runtime.bound_project,
        }
        for row in rows
    ]
    lines = [
        f"- {item['name']}{'（当前绑定）' if item['bound'] else ''}"
        f"：{item['files']} 文件 / {item['symbols']} 符号"
        f" @ {str(item['head_commit'] or '')[:8]}"
        for item in items
    ]
    return types.CallToolResult(
        content=[types.TextContent(type="text", text="已索引项目：\n" + "\n".join(lines))],
        structured_content={"items": items, "bound": runtime.bound_project},
    )


def _text(text: str, *, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], is_error=is_error
    )


def _json_safe(value: Any) -> Any:
    """结构化内容必须是 JSON 可序列化的；路径等类型转成字符串。"""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
