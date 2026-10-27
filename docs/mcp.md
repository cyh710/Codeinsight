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
| `read_file` | 读索引版本里的源码（带行号） |
| `get_callers` / `get_callees` | 调用关系（<1 置信度标「可能」） |
| `get_flow` | 从入口到副作用的业务流程 |
| `get_module_overview` | 模块职责与主要符号 |
| `get_design_decisions` | ADR 及其代码证据 |
| `get_changes` | 最近一次索引更新的变更、影响范围、过期设计说明 |
| `list_concepts` / `explain_concept` / `find_concept_instances` | 项目里的技术概念与三级解释 |
| `search_knowledge` / `read_knowledge_topic` | 内置教材（**不是**项目证据） |
| `list_projects` | 已索引项目与当前绑定（服务多项目实例时用） |

## 返回形状

每次调用返回两部分：

- `content`：给模型读的中文文本（可能被截断）；
- `structured_content`：结构化数据，**引用在 `citations[]` 里**
  （`{path, lineno, end_lineno, qualname}`）。正文被截断也不会丢引用。

工具失败（找不到符号、路径不存在）返回 `is_error: true` + 可读原因，
不抛异常——外部 agent 能据此换策略，而不是整个会话崩掉。

## 设计取舍

- **工具表来自 `ToolRegistry`，不重写第二份 schema**。逐个写 `@tool`
  包装函数等于把参数说明抄两遍，迟早出现「注册表说一套、MCP 说另一套」。
- **教材与项目证据永远分开**：知识工具的 `structured_content` 里没有
  `citations`，模型没法把「SQL 是什么」当成「这个项目用了 SQL」。
- **只读**：`tool.mutating` 为真时直接拒绝。写操作走另一条路——编排执行
  （ADR 0008 修订 / ADR 0032）：对话内识别开发任务后由 CodeInsight 驱动
  外部 agent 在隔离分支上干活，经双重审批合入；MCP 工具本身保持只读。

## 已验证

用官方 `mcp` Python 客户端的 `stdio_client` + `ClientSession` 真机跑过：

```
initialize          → codeinsight 0.1.0
list_tools          → 15 个（14 个项目/知识工具 + list_projects）
call_tool search_code → 文本 + structured_content.citations（3 条）
call_tool list_projects → 已索引项目与绑定标记
```
