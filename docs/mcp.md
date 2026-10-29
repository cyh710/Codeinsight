# MCP Server（源文档 §2.7-3 / ADR 0008）

把 CodeInsight 的**只读理解能力**通过
[MCP](https://modelcontextprotocol.io) 暴露给外部 agent。
写代码、跑命令、跑测试仍由外部 agent 负责（它们自带沙箱）——
CodeInsight 占住「理解 / 变更验证 / 认知更新」这三段。

## 启动

```bash
uv run ci mcp --project tapestry     # stdio
```

- `--project` 可省略：只有一个已索引项目时自动绑定；有多个会报错并列出可选项。
- `--db` 可指定索引库路径（缺省 `.ci/codeinsight.db`）。
- **stdout 是 JSON-RPC 通道**，日志全部走 stderr；不要在这里 `print`。

## 接到 Claude Code

在仓库根放一个 `.mcp.json`（项目级 MCP 配置）：

```json
{
  "mcpServers": {
    "codeinsight": {
      "command": "uv",
      "args": [
        "run", "--directory", "D:/path/to/CodeInsight",
        "ci", "mcp", "--project", "tapestry"
      ]
    }
  }
}
```

然后在 Claude Code 里 `/mcp` 能看到 `codeinsight` 已连接，就可以让它
「用 codeinsight 查一下对话流在哪实现」。

其他 MCP 客户端（Codex、Cursor 等）同理：启动命令换成上面的 `command + args` 即可。

## 工具清单

| 工具 | 用途 |
|---|---|
| `search_code` | 自然语言 / 标识符检索，返回带 `file:line` 的证据 |
| `find_symbol` | 按名字精确找定义（签名、docstring、引用数） |
| `list_files` / `search_files` | 列出、搜索当前工作区文件，无需先索引 |
| `read_file` | 默认读当前工作区；传完整来源target可恢复旧快照（带行号） |
| `get_callers` / `get_callees` | 调用关系（<1 置信度标「可能」） |
| `get_flow` | 真实调用边支持的静态候选；不代表运行顺序，副作用为启发式候选 |
| `get_module_overview` | 模块职责与主要符号 |
| `get_design_decisions` | ADR 及其代码证据 |
| `get_changes` | 最近一次索引更新的变更、影响范围、过期设计说明 |
| `list_concepts` / `explain_concept` / `find_concept_instances` | 项目里的技术概念与三级解释 |
| `search_knowledge` / `read_knowledge_topic` | 内置教材（**不是**项目证据） |
| `propose_exploration` | 整理本轮可选流程、要点与最多三个动作；不执行动作 |
| `list_projects` | 已索引项目与当前绑定（服务多项目实例时用） |

## 返回形状

每次调用返回两部分：

- `content`：给模型读的中文文本（可能被截断）；
- `structured_content`：结构化数据，**引用在 `citations[]` 里**。
  位置字段为 `path/lineno/end_lineno/qualname`，可附完整 `target`，以及
  `source_kind/content_sha256/index_epoch/head_commit`。跨调用恢复原来源时优先使用完整
  `target`，不能只凭路径和旧行号打开当前文件。正文被截断也不会丢结构化来源。

工具失败（找不到符号、路径不存在）返回 `is_error: true` + 可读原因，
不抛异常——外部 agent 能据此换策略，而不是整个会话崩掉。

## 设计取舍

- **工具表来自 `ToolRegistry`，不重写第二份 schema**。逐个写 `@tool`
  包装函数等于把参数说明抄两遍，迟早出现「注册表说一套、MCP 说另一套」。
- **教材与项目证据永远分开**：知识工具的 `structured_content` 里没有
  `citations`，模型没法把「SQL 是什么」当成「这个项目用了 SQL」。
- **只读**：`tool.mutating` 为真时直接拒绝。写操作走另一条路——编排执行
  （ADR 0008 修订 / ADR 0035）：对话内识别开发任务后由 CodeInsight 驱动
  外部 agent 在隔离分支上干活，经双重审批合入；MCP 工具本身保持只读。

## 工具数量与验证记录

当前注册表有 15 个基础工具；正常加载随包教材后增加 2 个知识工具，MCP 再增加
`list_projects`，共 **18 个**。实际目录以当前进程的 `list_tools` 为准。
`propose_exploration` 为只读附加结果提交工具，不执行提问或代码操作；
仅有请求内短编号不足以恢复跨调用材料。

早期版本曾用官方 `mcp` Python 客户端的 `stdio_client` + `ClientSession` 真机跑过：

```
initialize          → codeinsight 0.1.0
list_tools          → 15 个（14 个项目/知识工具 + list_projects）
call_tool search_code → 文本 + structured_content.citations（3 条）
call_tool list_projects → 已索引项目与绑定标记
```

这是当时 15 个工具的记录，不代表当前目录数量。当前离线回归覆盖 MCP 默认调用的
新文件读取、显式旧快照和并发读取隔离；最近整体验证见
[工程报告](reports/2026-10-28-debug-core-consistency.md)，未在该轮启动真实外部 agent。

## 来源与读取生命周期（ADR0043）

普通项目问题从当前文件开始，索引辅助定位和关系分析。解释围绕问题展开，关键实现提供少量来源链接，不要求逐句引用或事实/推断分栏。

每次MCP不带版本的`read_file`/`search_files`重新读取当前文件，避免长期进程缓存旧工作区。
若要跨调用固定版本，将上一结果`citations[].target`完整传给`read_file`的`target`参数；
也可显式传`path/source_kind/content_sha256/head_commit/index_epoch`原字段。
例如`read_file({"target": <上一结果的完整target>})`。来源必须属于同一项目及路径。
短`source_ref`只用于一次请求内探索，不是跨调用凭证；跨调用应使用完整target。
HTTP问答在同一次请求内固定同文件首次默认读取的版本，下一次请求重读当前磁盘。
