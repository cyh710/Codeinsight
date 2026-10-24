# 0004. 问答端点接线（`POST /query` · `POST /query/stream`）

- **提出方**：A 线
- **日期**：2026-10-24
- **紧急度**：M3 的引擎侧已完成，接口侧只差这一层接线
- **状态**：⏳ 待 C 线接线（契约不变，§8 早已冻结）

## 结论先行

M3 的运行时已经在 A 线落地并通过测试，**契约不用改**。C 线只需要在
`src/codeinsight/api/` 新增一个 `query.py`，把 HTTP 请求翻译成
`AgentRuntime.run()`，再把 `RuntimeEvent` 按 §8.3 原样转发成 SSE。

## 怎么接（可直接照抄）

```python
from codeinsight.agent.service import open_agent

session = open_agent(db_path(settings.data_dir), project_name)   # 每次请求开一次
try:
    answer = await session.runtime.run(
        project_id=session.project_id,
        question=body.question,
        conversation_id=body.conversation_id or "",
        emit=push_event,          # async (RuntimeEvent) -> None
    )
finally:
    session.close()
```

`RuntimeEvent.type` 与 SSE 事件名**一一对应**：
`meta` · `delta` · `tool` · `evidence` · `answer` · `error` · `done`。
`data` 就是事件体，直接 `json.dumps`。**不要加字段、不要改名。**

非流式 `/query` 直接把 `await runtime.run(...)` 的返回值摊到 §8.1 的形状：

| §8.1 字段 | 取哪里 |
|---|---|
| `text` | `answer.text` |
| `facts` / `inferences` | `answer.facts` / `answer.inferences`（**已分开**，不要合并） |
| `citations` | `answer.citations` → `{path, lineno, end_lineno, qualname, snippet}` |
| `tools_used` | `answer.tools_used` |
| `abstained` / `abstention_reason` | 同名 |
| `evidence` | 从 `emit` 收到的 `evidence` 事件里累积（A 线不重复构造） |

## 三条必须照做的约束

1. **`done` 一定会发**。运行时在 `finally` 里发，哪怕上游挂了、`error` 已经发过。
   C 线不要自己再补一个——重复的 `done` 会让前端提前收尾。
2. **`conversation_id` 必须原样透传**。会话历史存在进程级 `ConversationStore` 里
   （A 线默认已经是进程级），同一个 id 才能连续追问。空串表示新会话。
3. **每个请求一个 `AgentSession`，用完 `close()`**。SQLite 连接不跨线程共享；
   session 里带着连接、检索器与工具集，别在模块级复用。

## 错误映射

运行时不抛异常：上游错误会以 `error` 事件（SSE）或 `answer.error`（非流式）返回，
`code` 已经是契约 §0.3 的取值（`upstream_error` / `timeout` / `internal_error`）。
非流式端点遇到 `answer.error` 时按 §0.3 的形状返回对应 HTTP 状态即可。

## 不在本次范围

- 并发限流 / 排队：单用户本地工具，一个请求一个 session。
- 取消：前端断开时 SSE 生成器会被回收，`finally` 仍会把 `done` 写进账本。

## 影响的调用点

| 文件 | 动作 |
|---|---|
| `src/codeinsight/api/query.py` | 新增：两个端点 |
| `src/codeinsight/api/app.py` | 注册 router |
| `frontend/src/api/agent.ts` | 按 §8.2 / §8.3 实现（C 线本就有计划） |

## A 线已完成的部分

- `agent/runtime.py`：≤10 轮模型循环、每轮 ≤16 次工具调用、两层字节预算、
  流式 delta、`answer`/`done` 恰好一次。
- `agent/answer.py`：**引用校验**——模型写的 `[路径:行号]` 必须命中本回合工具
  真正读到过的位置，否则从正文删掉并降级为推断。
- `agent/tools_*.py`：12 个只读工具，`mutating=False`。
- `agent/ledger.py`：`agent_task` / `agent_event` 事件溯源。
- `agent/service.py`：`open_agent()` 一行拿到运行时。
- `ci ask`：同样的装配，命令行可用（`uv run ci ask "…" --project tapestry`）。
