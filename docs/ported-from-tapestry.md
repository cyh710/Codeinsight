# 移植说明 · 来自 Tapestry（织忆）

CodeInsight 有一部分代码直接从 **Tapestry**（`github.com/cyh710/Tapestry`，Apache-2.0）
的 `agent-v1` 分支移植过来。本文记录**移植了什么、改了什么、为什么**。

Tapestry 与 CodeInsight 是**两个独立项目**，解决不同问题：

| | Tapestry（织忆） | CodeInsight |
|---|---|---|
| 场景 | 角色陪伴、长程记忆 | 代码理解、仓库认知 |
| 形态 | local-first 桌面应用 | 本地索引 + Agent 服务 |

两者不互相依赖，也不在同一个仓库里。

---

## 已移植

| 文件 | 来源 | 改动 |
|---|---|---|
| `src/codeinsight/storage/sqlite.py` | `backend/storage/sqlite.py` | 基本照搬。加了 `foreign_keys=ON`、`apply_schema()`、`db_path()` |
| `src/codeinsight/llm/provider.py` | `backend/llm/client.py` 的 `BaseLLMClient` | **只保留接口形状**。丢掉织忆那层产品化 provider 绑定（`primary_chat` / `provider_registry` / `api_key_store`）——CodeInsight 是单用户本地工具，不需要账号与路由 |
| `src/codeinsight/agent/tool.py` | `backend/agent/tools.py` 的工具定义模式 | 改为 Protocol + `ToolResult(content/data)` 分离。织忆是数据驱动的 schema 列表 + if/elif 分发，这里用 Protocol 便于加 `mutating` 标记与审批扩展 |
| `src/codeinsight/llm/transport.py` | `backend/llm/transport.py` | 基本照搬：3 次指数退避 + 抖动、同 origin 连续失败 3 次冷却 20s、**流只在首字节前重试**。错误类型改成本项目的 `UpstreamError` |
| `src/codeinsight/llm/response_parser.py` | `backend/llm/response_parser.py` | 整份拿 `extract_json()`：围栏 / `<think>` / 尾部闲话 / 字符串内未转义引号 / `{{…}}` 双层包裹 |
| `src/codeinsight/agent/context.py` | `backend/services/agent_runner.py` 的 `_messages_from_events` | **思路移植，代码重写**：交互组不可拆 + 两层字节预算。上限按代码场景重定（12 KB / 24 KB / 64 KB） |

## 计划移植（尚未）

| 目标 | 来源 | 备注 |
|---|---|---|
| `parse_tool_arguments()` | `backend/llm/tool_arguments.py` | 未移植。OpenAI 兼容协议下参数已是 JSON 字符串，`_parse_arguments()` 够用；多 provider 方言是 M7 之后的事 |
| action digest 审批 | `backend/services/agent_tasks.py` | P2 备用。若将来把执行侧收回自己手里，整套移植 |
| `classify_action` 权限分类 | `backend/agent/permissions.py` | P2 备用。同上 |
| **整个前端基建** | `frontend/` | **M4。直接复制**，清单见 [`functional-spec.md` §3.3](functional-spec.md#c3--前端复制织忆前端基建只换业务组件)。含 `vite.config.ts`（SSE proxy）、`src/components/common/` 全 11 个通用件、`src/theme/palettes.ts`、`src/store/themeStore.ts`、`src/api/stream.ts`（SSE 解析 + watchdog）、`src/api/agent.ts`（`jsonRequest` + 错误类）、`src/store/chat*Actions.ts`（slice 拆分法）、`src/components/chat/`（MessageBubble / ChatWindow / InputBox / agentTimeline）、`tests/helpers/http.ts`（SSE 夹具） |

## 明确丢弃（织忆有、CodeInsight 不要）

- `agent_turn_execution.py` / `agent_turn_store.py` / `agent_turns.py` —— 织忆里 chat 内嵌了**第二套** agent runtime，与 `agent_runner` 并存。两套都背是负担，不移植。
- 桌宠 / 微信 bot / 角色卡 / 分支记忆 / 音色克隆 —— 产品特性，与代码理解无关。
- `windows_mcp.py` / 截图 / 交付物（deliverable）体系 —— 桌面自动化与文档改写场景专用。
- ChromaDB 依赖 —— 见上文，向量层改用 SQLite + numpy。

---

## 移植时保留的经验（比代码更值钱）

这四条写进了 CodeInsight 的设计原则，见 `docs/interfaces.md` 与 `README.md`：

1. **工具结果走事件溯源回灌**，不直接塞 prompt。织忆的 `_messages_from_events` 把事件折成"交互组"，
   好处是"账本里看到的"与"模型看到的"来自同一份记录。
2. **截断用同一个对象写记录与事件**。两处若截断不一致，就会出现"账本里有、模型没看到"或反之。
3. **上下文两层分别设界**：持久化层与模型上下文层各有一套上限，混着说会露馅。
4. **fail-closed 优先于 fail-open**：无法确认的一律拒绝执行并列为 UNKNOWN，不做"猜测式"处理。

## 许可

Tapestry 以 Apache-2.0 发布，CodeInsight 同样以 Apache-2.0 发布。
移植的代码保留原版权声明与出处标注；本文件即为出处声明的一部分
（Apache-2.0 §4(d)）。
