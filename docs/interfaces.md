# 接口契约

> 本文记录**层与层之间的契约**。换实现不应该改动上层代码——这是"留接口"的意义。
> 每条契约都标出了它对应的源文档章节。

## 0. 依赖方向

```
api ──→ agent ──→ cognitive ──→ storage
 │        │          │
 │        └──────────┴──→ llm
 └──→ storage
```

**禁止反向依赖**：`storage` 不认识 `agent`；`cognitive` 不认识 `api`；
`agent` 不直接写 SQL（走 `storage` 的连接工厂拿连接）。

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
- 符号的 `qualname` 在**单个项目内唯一**；方法用 `类名.方法名`。
- 无法静态解析的关系产出 `ParsedEdge(confidence < 1, dst_qualname=None)`，
  **不丢弃、不假装确定**。

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
  `[路径:行号]`，对不上的引用会被删掉并降级成推断（`agent/answer.py`）。
- 为什么是 `async`：`explain_concept(deep)` 要等模型，其余要等 I/O。同步签名会逼
  调用方在事件循环里 `asyncio.run`，在 FastAPI 里直接炸。
- v1 全部工具 `mutating=False`。写入与执行交给外部 agent 经 MCP Server 承担。

**v1 工具清单**（`agent/tools_{code,knowledge,project}.py`，共 12 个）：
`search_code` · `find_symbol` · `read_file` · `get_callers` · `get_callees` ·
`list_concepts` · `explain_concept` · `find_concept_instances` · `get_flow` ·
`get_changes`（M6 前返回空壳） · `get_design_decisions` · `get_module_overview`。

请求 0012 增加第十三个基础工具 `propose_exploration`（`agent/tools_exploration.py`）。
它只整理可选流程、已展示要点和至多三项动作，不产生正文引用资格、不执行动作。
`agent/exploration.py` 校验同版本对象和静态关系；`agent/discovery.py` 以已有索引生成首页入口。
知识检索工具仍是独立可选来源，代码检索评测通道保持不变。

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

**当前不实现。** 实现方**不得**使用 shell（`shell=True`），必须以 argv 列表调用。
将来若把执行侧收回自己手里，可照搬 Tapestry 的三层防护：
action digest 审批 / 子进程最小环境 / 白名单校验。

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
`build_learning_tools` 提供可选异步知识工具；首版 Agent 默认通过有界前置检索注入，
原 12 个项目工具及代码检索评测通道保持独立。

schema 2 增加 `concept_rule_version(id,fingerprint)`，repo_state.concept_version 保持 INTEGER。
正文变化只更新本体文案；指纹变化才触发相应项目的概念重新检测，输入为冻结 Git 源码。

## 12. 探索恢复（请求 0012）

`PersistentConversationStore.exploration_context(key)` 返回最多 4KB 的会话探索脉络，
加入既有历史预算，当前问题和工具证据仍具有优先权。只保存已展示内容，不推断用户掌握情况。
schema 4 给 conversation 新增 exploration_json；历史、索引和最近六轮有效问答约定不变。
前后端动作、回合读取和局部材料身份见 [`api-contract.md` §13](api-contract.md#13-项目探索请求-0012adr-0029)。
