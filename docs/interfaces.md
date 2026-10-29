# 接口契约

> 本文记录**层与层之间的契约**。换实现不应该改动上层代码——这是"留接口"的意义。
> 每条契约都标出了它对应的源文档章节。
> 同步基线：`54ab8e6`（2026-10-29）。HTTP／SSE 字段以 [`api-contract.md`](api-contract.md) 为准。

## 0. 依赖方向

```
api ──→ agent ──→ cognitive ──→ storage
 │        │          │
 │        └──────────┴──→ llm
 └──→ storage
```

**禁止反向依赖**：`storage` 不认识 `agent`；`cognitive` 不认识 `api`；
数据库连接统一由 `storage` 工厂配置；Agent 服务和仓储可通过该连接查询、保存事件与会话。

---

## 1. `LanguageParser` · 解析层

`src/codeinsight/cognitive/parsing/base.py`

```python
class LanguageParser(Protocol):
    language: str

    def supports(self, path: str) -> bool: ...
    def parse(self, path: str, source: str, ctx: ParseContext) -> ParsedFile: ...
```

**约定**
- `parse` **不抛异常**。语法错误 / 编码错误降级为"该文件产出空符号集"，
  由调用方记为 skipped，不得让整次索引失败。
- `ParsedFile.path` 必须是 **repo-relative、posix 风格**。
- `qualname` 从仓库根全限定，方法包含模块与类路径；重复定义仍可能同名，
  不能仅凭短名称或 `qualname` 假定唯一，存储同时保留文件与行号。
- 无法静态解析的关系产出 `ParsedEdge(confidence < 1, dst_qualname=None)`，
  **不丢弃、不假装确定**。
- `python-ast-2` 将参数／局部绑定遮蔽的调用保留为不确定，不靠全局唯一短名猜目标；
  更新既有索引后才应用新解析规则（ADR 0044）。

> 对应源文档 §3.2 末句「通过**可扩展的语言解析模块**增加其他语言」。

---

## 2. `Embedder` · 嵌入层

`src/codeinsight/cognitive/embedding/base.py`

```python
class Embedder(Protocol):
    model_id: str  # 'bge-m3@1024'
    dim: int

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...
```

**约定**
- 返回顺序与输入一一对应，维度恒为 `self.dim`。
- 实现方自行分批，避免一次几千条被上游拒绝。
- `model_id` 含维度——换模型即换 `model_id`，`embedding` 表按 `model_id` 过滤，**不需要迁移**。

---

## 3. `KeywordIndex` / `VectorStore` · 检索层

`src/codeinsight/cognitive/retrieval/base.py`

```python
class KeywordIndex(Protocol):
    def search(self, query: str, k: int) -> list[tuple[int, float]]: ...
    def delete(self, ids: Sequence[int]) -> None: ...


class VectorStore(Protocol):
    def upsert(self, ids, vectors) -> None: ...
    def query(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]: ...
    def delete(self, ids: Sequence[int]) -> None: ...
```

**约定**
- 只返回 `(chunk_id, score)`。**融合与排序不在这一层**——那是 retriever 的职责，
  这样换后端时融合逻辑完全不受影响。
- 关键词通道分数越大越相关；稠密通道是 cosine similarity，越大越相关。
- 无命中返回空列表，**不抛异常**。

---

## 4. `ConceptDetector` · 知识层

`src/codeinsight/cognitive/concepts/base.py`

```python
class ConceptDetector(Protocol):
    def detect(
        self, symbols: Sequence[SymbolView], edges: Sequence[EdgeView]
    ) -> list[ConceptInstance]: ...
```

**约定**
- 每个实例必须带 `evidence`（命中了哪条规则，如 `import jwt` / `decorator @app.get`），
  保证结论**可追溯、可质疑**。
- 检测规则声明在 `knowledge/concepts/*.yaml`，**不手工维护"概念 → 代码位置"映射表**。
  概念在代码里的体现是结构性的（导入名、装饰器、基类、调用名、属性名），
  从符号与关系索引自动派生，代码改了重跑检测即同步。

> 对应源文档 §2.6「系统**自动识别**或按需检索项目中的相关概念」。

---

## 5. `DiffSource` · 变更源

`src/codeinsight/cognitive/changes/base.py`

```python
class DiffSource(Protocol):
    def head(self) -> str: ...
    def changed_files(self, since: str | None) -> list[ChangedFile]: ...
    def diff(self, since: str | None) -> str: ...
    def file_at(self, path: str, commit: str) -> str | None: ...
```

**约定**
- `since=None` 表示与工作区对比。
- `file_at` 用于**符号级**判断（内容是否真的变了），不只是文件级。

> 对应源文档 §4.2 第 2 步「检测**文件和代码符号**变化」。

---

## 6. `Tool` · Agent 工具

`src/codeinsight/agent/tool.py`

```python
class Tool(Protocol):
    name: str
    description: str
    parameters: Mapping[str, Any]  # JSON Schema
    mutating: bool

    async def run(self, arguments: Mapping[str, Any], ctx: ToolContext) -> ToolResult: ...
```

**约定**
- `run` **不抛异常**。失败返回 `ToolResult(error=...)`，让 Agent 有机会换个策略，
  而不是整个回合崩掉。
- `content` 是给模型看的文本（可能被截断）；`data` 是结构化数据（不进模型上下文，
  但会被引用与前端使用）。**两者分离保证截断 `content` 不破坏 `data` 里的 `file:line`。**
- `data["citations"]` 是**本回合的 grounded 集合**：运行时拿它校验模型答案里的
  `[路径:行号]` 的位置与来源身份。无效或多版本有歧义的引用不变成可点击链接，
  解释保留；不因缺引用自动归为推断或整篇弃答（ADR 0040、0044）。
- 为什么是 `async`：`explain_concept(deep)` 要等模型，其余要等 I/O。同步签名会逼
  调用方在事件循环里 `asyncio.run`，在 FastAPI 里直接炸。
- v1 全部工具 `mutating=False`。写入与执行交给外部 agent 经 MCP Server 承担。

**当前注册表**：15 个基础工具；启用随包教材时另有 2 个知识工具。
完整名称与 MCP 暴露方式见 [`mcp.md`](mcp.md)。

`list_files/search_files/read_file` 默认访问当前工作区，索引用于检索和静态关系。
`propose_exploration` 只整理可选流程、已展示要点和至多三项动作，不执行动作。
服务端按实际取得的来源补齐版本，多版本可用请求内 `source_ref` 选择；
短编号不跨请求。`get_flow` 只沿真实静态调用边返回候选，不代表运行顺序。

HTTP 每次问答固定同文件首次默认读取的版本；MCP 每次不带版本的调用重读当前文件。
显式旧版本使用完整来源目标，不由长期工具对象缓存隐式决定。
知识工具保持独立来源，代码检索评测通道不变（ADR 0042–0044）。

---

## 7. `LLMProvider` · 模型层

`src/codeinsight/llm/provider.py`

```python
class LLMProvider(Protocol):
    model_id: str

    async def complete(self, system, messages, *, max_tokens=0, temperature=0.0) -> str: ...
    async def complete_with_tools(
        self, system, messages, tools, *, max_tokens=0, temperature=0.0, tool_choice="auto"
    ) -> ToolCallResponse: ...

    def stream_with_tools(
        self, system, messages, tools, *, max_tokens=0, temperature=0.0, tool_choice="auto"
    ) -> AsyncIterator[StreamChunk]: ...
```

`StreamChunk(text, tool_calls, finish_reason)`：正文增量边到边交；
`tool_calls` **只在流末尾**给出——工具参数是分片到达的，拼完之前交出去只是半截 JSON。

**约定**
- `model_id` 含版本，评测报告必须记录它。
- `temperature` 默认 0，保证评测可复现。

> 接口形态移植自 Tapestry `ai-companion-agent` @ `agent-v1`（Apache-2.0）的
> `BaseLLMClient`，见 `docs/ported-from-tapestry.md`。

---

## 8. `CommandRunner` · 执行层

`src/codeinsight/execution/base.py`

```python
class CommandRunner(Protocol):
    async def run(self, argv, *, cwd: Path, timeout=60.0, env=None) -> CommandOutcome: ...
```

这个通用命令 Protocol 仍只保留接口；当前执行编排使用
`execution/driver.py` 的 `ExecutorDriver.execute(request, emit)`，由
`ClaudeCodeDriver`／`ZCodeDriver` 调用外部 agent，不通过只读 Agent 工具执行命令。
驱动器以 argv 启动子进程；计划批准、隔离工作树执行、结果审阅及合入见 ADR 0035。
服务重启后遗留执行任务转失败并保留分支和工作树，不自动续跑或清理（ADR 0044）。

---

## 9. 存储层

`src/codeinsight/storage/sqlite.py`

```python
def open_sqlite(path, *, row_factory=False) -> sqlite3.Connection
def apply_schema(conn) -> None
def db_path(data_dir, name="codeinsight.db") -> Path
```

**约定**
- 每个连接都设 `journal_mode=WAL` / `busy_timeout=5000` / `synchronous=NORMAL` / `foreign_keys=ON`。
- `check_same_thread` 保持开启：**后台线程必须在自己线程内开连接**。
- `apply_schema` 幂等（全部 `IF NOT EXISTS`）。
- 服务入口通过 `ensure_schema` 原地迁移；当前版本仅校验，不在普通读取请求重跑建表写入。
  当前 schema 为 6，兼容两条分支的历史结构，不能据早期 schema 4 记录删除重建数据库。
- 索引扫描／解析在隔离库构建，完成后短事务发布本项目索引；不以整库替换覆盖并发会话或其他项目。
  最终发布仍会持有写锁，外部长期占锁需明确返回可重试原因（ADR 0044）。
- FTS5 虚表用 **external content + 触发器**与应用层同步——
  手工维护 insert/update/delete 三处同步代码，最容易出的 bug 是"文件删了 FTS 里残留旧行"。

---

## 10. 上下文有界（两层）

| 层 | 常量 | 值 |
|---|---|---|
| 持久化 | `max_tool_result_bytes` | 80,000 |
| 模型 | `max_context_bytes` | 64,000 |
| 模型 | `max_context_message_bytes` | 24,000 |
| 模型 | `max_tool_calls_per_turn` | 16 |
| 模型 | `max_model_turns` | 0（默认不限总轮次，正数主动限额） |

**约定**：截断用**同一个对象**写"事件记录"与"模型上下文"，
保证账本和模型看到的永远一致（源文档 §3.1 第四层末句的精神）。

> 对应源文档 §3.2「上下文管理」。

## 11. 学习接入（请求 0005）

`LearningBridge.prepare_goal(question, max_message_bytes=..., reading_context=...)`
返回目标消息和 `PreparedKnowledge`。Agent 对同一回合保留快照，最终通过
`finalize_answer` 输出知识来源、正文目标和最多三项学习入口，不重复检索更换版本。
代码阅读目标走现有 `read_file` 的同一执行/事件/账本路径，教材不注入代码证据集合。
`knowledge_directory` 只查 CodeInsight 安装包或源码资产，不依赖被分析项目的工作目录。
`build_learning_tools` 提供可选异步知识工具。没有显式阅读目标时，仅唯一术语或定义式疑问
自动注入最多一个完整章节；放不进预算就跳过。普通项目问题不通过宽泛检索自动补教材。
显式阅读／选区按原版本和预算读取，不额外叠加自动章节；模型仍可主动调用知识工具。

历史 schema 1→2 增加 `concept_rule_version(id,fingerprint)`，repo_state.concept_version 保持 INTEGER。
正文变化只更新本体文案；指纹变化才触发相应项目的概念重新检测，输入为冻结 Git 源码。

## 12. 探索恢复（请求 0012）

`PersistentConversationStore.exploration_context(key)` 返回最多 4KB 的会话探索脉络，
加入既有历史预算，当前问题和工具证据仍具有优先权。只保存已展示内容，不推断用户掌握情况。
历史 schema 3→4 给 conversation 新增 exploration_json；当前集成 schema 为 6，
历史、索引和最近六轮有效问答约定不变。脉络表示已讨论内容，不表示用户已掌握或新版项目事实。
前后端动作、回合读取和局部材料身份见 [`api-contract.md` §13](api-contract.md#13-项目探索请求-0012adr-0029)。
