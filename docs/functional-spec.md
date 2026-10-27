# 功能实现需求书 · 三线并行

> **这份文档是三条线唯一的对齐依据。** 三个 agent 都以本文为准；
> 本文与代码冲突时，先改本文再改代码。
>
> 配套：[`../AGENTS.md`](../AGENTS.md)（作业规程）· [`workspace.md`](workspace.md)（三线怎么协作）·
> [`roadmap.md`](roadmap.md)（阶段与验收）· [`interfaces.md`](interfaces.md)（接口契约）·
> [`decisions/`](decisions/)（技术决策与理由）

---

## 0. 共同约定

### 0.1 仓库与分支

| 分支 | 归属 | 说明 |
|---|---|---|
| `main` | A 线（我） | **集成分支，只有我能合**。合之前必须全量测试通过 |
| `feat/knowledge` | B 线（知识探索） | |
| `feat/frontend` | C 线（前端 + API） | |

每个 agent 在**自己的 worktree**里工作，不共用工作目录：

```
<仓库根>              main            A 线
<仓库根>-wt-knowledge feat/knowledge  B 线
<仓库根>-wt-frontend  feat/frontend   C 线
```

> 三条线是同一次开发期的并行分工。合并流程与冲突处理见
> [`requests/README.md`](requests/README.md) 里的规矩。

### 0.2 目录所有权（一个目录只有一个 agent 能写）

```
src/codeinsight/
├── cognitive/
│   ├── parsing/      A 线
│   ├── indexing/     A 线
│   ├── retrieval/    A 线
│   ├── embedding/    A 线
│   ├── concepts/     B 线   ← 独占
│   └── changes/      A 线
├── agent/            A 线
├── llm/              A 线
├── execution/        A 线
├── storage/          A 线   ← 契约文件，B/C 只读
├── api/              C 线   ← 契约由 A 线冻结，见 §1.3
├── eval/             A 线   ← concept 臂由 B 线提供
├── models.py         A 线   ← 契约文件，B/C 只读
├── config.py         A 线   ← 契约文件，B/C 只读
└── cli.py            A 线

knowledge/concepts/   B 线   ← 独占
frontend/             C 线   ← 独占
tests/                各自写自己的目录，不共用文件名
docs/                 A 线维护；B/C 需要加文档时提需求
```

**越界修改的处理**：发现需要改别人目录的文件时，**不要直接改**——
在 PR/提交信息里写清"需要 X 改 Y 的什么"，由 A 线统一改。

### 0.3 冻结的契约（不要改）

| 契约 | 位置 | 状态 |
|---|---|---|
| 领域模型 | `src/codeinsight/models.py` | ✅ 冻结 |
| 数据契约 | `src/codeinsight/storage/schema.sql` | ✅ 冻结（`file.role` 单值分类 + `dependency` 表见 §1.2） |
| API + SSE 契约 | `docs/api-contract.md` | ✅ 冻结（18 个端点 + SSE 事件词汇表，见 §1.2） |
| 前端类型 | `frontend/src/api/types.ts` | ✅ 冻结（与契约一一对应，C 线照它写） |
| 索引样例 | `fixtures/sample-index.json` | ✅ 已产出（688 文件 / 790 符号 / 5109 边，B/C 对它开发） |
| **前端基建来源** | 织忆 `frontend/` | ✅ 清单见 §3.3 |

### 0.4 怎么提需求

任何一条线需要契约变更时：

1. 在自己的分支上**不改**契约文件；
2. 在 `docs/requests/` 下加一个 `NNNN-<简述>.md`，写清：要什么、为什么、影响的调用点；
3. 提给 A 线，A 线评估后统一改契约并同步给三条线。

---

## 1. A 线（我）：索引 + 检索 + Agent + MCP + 集成

### 1.1 交付顺序

```
M1 索引  →  M2 检索  →  M3 Agent  →  M7 MCP
              └─ 与 B/C 并行  ─┘
```

### 1.2 M1 · 索引层

#### A1 扫描器 `cognitive/indexing/scanner.py`

```python
@dataclass(frozen=True)
class RepoFile:
    path: str          # repo-relative，posix 风格
    blob_sha: str | None
    size_bytes: int

def list_repo_files(root: Path, *, ref: str | None = None) -> list[RepoFile]
```

- **用 `git ls-tree -r -z --name-only <ref>` 取文件，不扫工作区**。
  命令必须带 `-c core.quotepath=false`，否则非 ASCII 路径会被加引号输出导致解析错误。
- 非 git 目录才 fallback 到 `os.walk`。
- 排除：`.git/` `build_cache/` `node_modules/` `.venv/` `dist/` `*.lock`
- 按魔数 + 体积判二进制并排除。
- 给每个文件标一个**互斥**的 `role`：`source` `test` `vendored` `generated` `config` `doc`
  （优先级 vendored > generated > test > config > doc > source）。
- **三档范围**（ADR 0015）：
  - 第一档·**不进索引**：`build_cache/` `node_modules/` `.venv/` `dist/` `*.min.js` 二进制 `*.lock`
  - 第二档·**符号入、chunk 不入**：第三方目录（`mobile_sam/` 等）→ `role='vendored'`。
    项目 `import` 了它，那条 import 边是"项目用了 X"的证据，要留；
    但第三方内部实现不该出现在检索结果里。
  - 第三档·**全量入、同等对待**：`tests/` `docs/` `scripts/` `backend/`。
    **不做任何降权**——降权是人为偏置，会污染 §5 的对照实验（ADR 0003 同理）。
- **验收**：对织忆 `agent-v1` 取到的文件数与 `git ls-tree` 一致；不含 `dist/` `.venv/`；
  非 ASCII 路径原样保留（不带引号、不转义）。

#### A2 Python 解析器 `cognitive/parsing/python_parser.py`

```python
class PythonParser:
    language = "python"

    def supports(self, path: str) -> bool: ...
    def parse(self, path: str, source: str, ctx: ParseContext) -> ParsedFile: ...
```

- 只用标准库 `ast`（ADR 0001）。
- 符号 kind：`module` / `class` / `function` / `method` / `property` / `constant`。
- **qualname 一律从仓库根全限定**：`<模块 qualname>.<局部路径>`。
  模块 qualname = 路径转点号（`backend/core/chunk_bm25.py` → `backend.core.chunk_bm25`，
  `backend/__init__.py` → `backend`）。
  局部路径规则：模块级 `foo`；方法 `Class.method`；嵌套 `outer.inner`。
  全限定是**必须的**——跨文件解析调用要靠它（`foo` 和 `bar.foo` 是两个东西）。
- **产出五类边**：

  | kind | 来源 | dst_name |
  |---|---|---|
  | `call` | `ast.Call` 的 func（Name / Attribute） | **完整点号路径**（`jwt.decode` / `helper`） |
  | `inherits` | `ast.ClassDef.bases` | 基类名 |
  | `decorator` | `decorator_list` | 装饰器名（`app.get` / `lru_cache`） |
  | `imports` | `ast.Import` / `ast.ImportFrom` | **完整模块路径**（`backend.config`） |
  | `references` | 属性被读取但未调用 | 完整点号路径（`self.x` → `x`） |

  > **为什么 `call` 与 `imports` 都用完整路径而不是最后一个标识符 / 顶层包名**：
  > 源文档 §2.6 的概念检测规则里 `call_names: [jwt.decode]` 是按全路径写的——
  > 只留 `decode` 就分不清 `jwt.decode` 和 `os.decode`；
  > 而 `from backend.config import settings` 记成 `backend` 会让项目内部上百条导入
  > 全变成同一个名字，既没法做模块依赖分析（§2.2-3），也没法做概念检测。
  >
  > **本体按「整串相等或前缀相等」匹配**：`import_names: [jwt]` 能命中
  > `jwt` 和 `jwt.algorithms`；`import_names: [backend]` 能命中 `backend.config`。

- **相对导入要解析成绝对模块路径**：`backend/api/pet.py` 里
  `from .core import x` → `backend.api.core`，`from ..services import y` → `backend.services`。
  相对导入能确定是仓库内部的模块，直接给 `dst_qualname`。

- **动态调用**（`getattr` / `importlib` / 字符串反射）→ `confidence=0.5`、`dst_qualname=None`。
  **不能丢弃，也不能假装确定**（§2.2）。
- 解析失败**不抛异常**，产出空符号集，由索引器记为 `skipped`（ADR 0012）。

#### A3 符号与关系落库 `cognitive/indexing/{symbols,edges}.py`

- `module.qualname` = 路径转点号（`src/xxx.py` → `src.xxx`）。
- `symbol` 表：`UNIQUE(project_id, file_id, qualname, lineno)`。
- `edge.dst_symbol_id`：能唯一解析就填；**同名多义（多个符号同名）时留 NULL**，
  靠 `dst_name` + `dst_qualname` 保留线索。**不能随便挑一个。**

#### A4 入口与依赖识别（§2.1-1 / §2.1-2）

- `entry_point` 表：`kind` ∈ `file` / `console_script` / `framework_app`；
  识别 `main.py` `app.py` `__main__.py` 与 `pyproject.toml` 的 `[project.scripts]`。
- `dependency` 表（**M1 新增**）：从 `pyproject.toml` / `requirements*.txt` 解析，
  同时把 `import` 到但不在依赖表里的记为 `source='import'`。

#### A5 关键业务流程（§2.2-4 / §2.1-6）

```python
def detect_flows(symbols, edges, entry_points, *, max_depth: int = 12) -> list[Flow]
```

- 从入口 BFS，得到主链路；`flow_step` 记录 (symbol, path, lineno)。
- "流程"= 从入口到**有外部副作用的符号**（写文件 / 发请求 / 落库 / 改全局状态）。

#### A6 设计说明索引（§2.4-5）

- 扫 `docs/decisions/` `docs/adr/` `ADR-*.md`。
- 解析标题行 / frontmatter → `doc_id` `title` `status`。
- 抽"声称的机制"→ `claims_json`（`[{concept_id, pattern}]`），
  与 B 线的 `concept_instance` 比对 → M6 的**设计说明过期检测**。

#### A7 切块（ADR 0005）

```python
def chunk_symbol(symbol, source_lines, *, max_lines: int = 120) -> list[ChunkSpec]
```

- 以符号为原子；超标按语句边界二次切分，写 `ordinal` / `part_count`，
  **`symbol_id` 仍指向原符号**。
- `token_text` = `split_identifiers(body)` 的产物（见 §1.3）。
- `source_sha256` = 该 chunk 源码的 sha256；`file_content_sha256` = 文件的 sha256。

#### A8 稠密检索（ADR 0002）

```python
class SqliteVectorStore(VectorStore):
    def upsert(self, ids, vectors) -> None
    def query(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]
    def delete(self, ids) -> None
```

- numpy 暴力余弦；向量归一化后点积即 cosine。
- 查询时按 `model_id` 拉全量拼成 ndarray，**按 `repo_state.index_epoch` 缓存失效**。
- `text_sha256` 命中则复用旧向量。

**M1 验收**：对织忆 `agent-v1` 建索引成功；符号数、调用边数与 AST 抽查一致；
`git ls-tree` 文件数与入库文件数一致（扣除排除规则）。

### 1.3 M2 · 检索层

#### A9 代码分词器 `retrieval/tokenizer.py`（**关键**）

```python
def split_identifiers(text: str) -> list[str]
```

- 每个标识符产出：**全名 + snake 分词 + camel 分词 + 小写形式**。
  例：`get_user_name` → `get_user_name get user name`；
  `HTTPServer` → `HTTPServer httpserver http server`。
- 中文走 **jieba**（纯 Python）：不做这一步，中文 docstring 成巨型 token，
  会通过 BM25 长度归一化**系统性压低中文重的 chunk**，污染对照实验结论（ADR 0003）。
- **入库与查询共用这一个函数**，由单元测试保证口径一致。

#### A10 三路检索 + 融合

| 通道 | 实现 | 产出 |
|---|---|---|
| BM25 | `Fts5KeywordIndex.search`（FTS5 `bm25()`） | `(chunk_id, score)` |
| 稠密 | `SqliteVectorStore.query` | `(chunk_id, score)` |
| 符号关系 | 精确符号命中 → 定义 + 调用者 + 被调者 + 同文件兄弟 | `(chunk_id, score)` |

- 融合 `reciprocal_rank_fusion(rankings, k=60)`（移植织忆 `backend/core/chunk_bm25.py`）。
- **邻域扩展**：命中后沿 `edge` 走 `retrieval_neighbor_depth`（默认 1）跳，扩展证据 score 打折。
- **不手工加检索策略**——评测的对照组就是这个检索器的可配置版本。

#### A11 检索器接口

```python
class Retriever:
    def retrieve(self, query: str, k: int, *, project_id: int) -> list[Evidence]
```

- `Evidence` 用 `models.py` 里的结构（`path` / `lineno` / `end_lineno` / `qualname` /
  `snippet` / `score` / `lanes` / `concept_ids`）。

**M2 验收**：对织忆 `agent-v1` 抽 10 个"在哪里实现"的问题，10 个都给出正确 `file:line`。

### 1.4 M3 · Agent 层

#### A12 Runtime

```python
class AgentRuntime:
    async def run(self, *, project_id: int, question: str, conversation_id: str,
                  provider: LLMProvider, registry: ToolRegistry) -> Answer
```

- 总轮次默认不限（请求 0020；`max_model_turns=0`），每轮**重新装配上下文**。
- 上下文装配：目标（钉在原始位置）+ 最近 N 个完整交互组 + 工具目录（作为独立参数，不进 messages）。
- 工具结果**先落 `agent_event`，再由装配折回 messages**——同一份对象（ADR 0010）。
- 无 tool_calls → 生成 `Answer`（facts/inferences 分离，ADR 0007）。
- 正数轮次上限仅在调用方主动配置时生效；空输出或主动限额仍如实返回“未完成”。
- 检索无命中 → `abstained=True` + 原因，**不允许编造 `file:line`**。

#### A13 12 个只读工具（`agent/tools_*.py`）

| 工具 | 入参 | 出参 | 依赖 |
|---|---|---|---|
| `search_code` | `query, top_k` | 命中列表（符号 / `file:line` / 分数 / 命中通道） | A 线 |
| `find_symbol` | `name` | 定义位置 + 签名 + docstring + 引用处 | A 线 |
| `read_file` | `path, start_line?, end_line?` | 带行号的源码片段 | A 线 |
| `get_callers` | `symbol` | 调用点（含不确定标记） | A 线 |
| `get_callees` | `symbol` | 被调点 | A 线 |
| `list_concepts` | `query?` | 概念 + 实例数 | **B 线** |
| `explain_concept` | `concept_id, depth` | 三级深度解释 | **B 线** |
| `find_concept_instances` | `concept_id` | 实例列表 | **B 线** |
| `get_flow` | `flow_name?` | 流程步骤 | A 线 |
| `get_changes` | `since?` | 变更文件 / 受影响符号 / 摘要 | A 线（M6） |
| `get_design_decisions` | `query?` | 设计说明 + 证据 | A 线（M1） |
| `get_module_overview` | `path` | 模块职责 + 出入口 | A 线 |

- 全部 `mutating=False`（ADR 0008）。
- `run()` **不抛异常**（ADR 0012），失败返回 `ToolResult(error=...)`，
  `content` 写**可读的中文说明**（模型要能据此自我修正）。

#### A14 LLM Provider

- `llm/openai_compat.py`：OpenAI 兼容协议，DeepSeek / SiliconFlow / 本地都走它。
- `llm/response_parser.py`：**移植织忆的 `extract_json()`**（处理 fence、多余解释、
  未转义引号、双层包裹）。
- `llm/transport.py`：**移植织忆的 `request_with_retry()`**（3 次指数退避 + 抖动）
  与同 origin 熔断（3 次失败冷却 20s）。

#### A15 SSE 端点 `api/query.py`（实现由 C 线，契约由 A 线冻结）

见 §1.6。

### 1.5 M7 · MCP Server

- 把 12 个工具暴露成 MCP tools（ADR 0008）。
- 外部 agent（Claude Code / Codex）作为 MCP 客户端调用。
- 工具描述要**外部 agent 用得顺手**：写清用途与参数、返回结构化。

### 1.6 我要在本周补的三份契约

| 文件 | 内容 | 谁最需要 |
|---|---|---|
| `docs/api-contract.md` | 端点清单 + 请求/响应体 + SSE 事件词汇表 | C 线 |
| `frontend/src/api/types.ts` | 与契约一一对应的 TS 类型 | C 线 |
| `fixtures/sample-index.json` | **织忆 `agent-v1` 的真实索引快照**（符号 + 边 + file:line） | B 线、C 线 |

---

## 2. B 线（知识探索）：概念本体 + 检测 + 解释

> 归属：`src/codeinsight/cognitive/concepts/` + `knowledge/concepts/`

### 2.1 B1 · 概念本体格式

**一个概念一个文件**：`knowledge/concepts/<id>.yaml`

```yaml
id: jwt                      # 必填，小写 kebab-case，全局唯一
name: JWT 身份认证            # 必填
category: auth               # 必填，枚举见下
summary: 用签名令牌承载身份声明的无状态认证机制。   # 必填，1–2 句（"快速理解"用）
principles: |                # 选填，"深入探索"用
  载荷编码后用对称/非对称密钥签名，验证方只需验签不需查库。
tradeoffs: |                 # 选填，"深入探索"用
  换取无状态与可水平扩展，代价是签发前无法即时吊销。
alternatives: |              # 选填，"深入探索"用
  会话 ID + 服务端存储；不透明令牌 + 撤销表。
detection:                   # 必填
  import_names: [jwt, jose, pyjwt, authlib]
  call_names: [jwt.decode, jwt.encode]
  attribute_names: [Authorization]
  decorator_names: [requires_auth, verify_token]
  base_classes: []
  string_markers: []
references:                   # 选填，权威链接
  - https://datatracker.ietf.org/doc/html/rfc7519
```

**category 枚举**：`auth` `cache` `db` `concurrency` `async` `http` `config` `pattern`
`data-structure` `security` `observability` `testing` `build` `other`

**detection 规则键 → 匹配对象**（关键，靠这个才能自动派生）：

| 键 | 匹配什么 | 命中的边 kind | 匹配规则 |
|---|---|---|---|
| `import_names` | 被导入的模块路径 | `imports` | 整串相等 **或** 前缀相等（`jwt` 命中 `jwt.algorithms`） |
| `call_names` | 被调用的名字（`a.b` 形式匹配 `Attribute` 的完整路径） | `call` | 整串相等 **或** 末段相等（`jwt.decode` 命中 `jwt.decode` 与 `decode`） |
| `attribute_names` | 属性名 | `references` | 末段相等（`self.redis` 记成 `redis`） |
| `decorator_names` | 装饰器名 | `decorator` | 末段相等（`app.get` 命中 `get`） |
| `base_classes` | 基类名 | `inherits` | 整串相等 |
| `string_markers` | 源码中的字符串字面量 | 源码匹配 | 精确包含 |

> **为什么规则是"相等或前缀/末段"而不是精确匹配**：边的 `dst_name` 存的是
> **完整点号路径**（见 §1.2 A2），因为只存最后一段就分不清 `jwt.decode` 和 `os.decode`，
> 只存顶层包名又会把 `backend.config` 和 `backend.services` 混成一个。
> 完整路径 + 灵活的匹配规则两头都能兼顾。

**硬约束**：
- **不手工维护"概念 → 代码位置"映射表**（ADR 0011）。位置由规则自动派生。
- 每个概念必须有 `summary`——"快速理解"这一级**不调 LLM**，直接读它。
- `tradeoffs` 是这个概念最值钱的部分，要写，不要留空。

### 2.2 B2 · 本体加载 `concepts/ontology.py`

```python
@dataclass(frozen=True)
class Concept:
    id: str; name: str; category: str
    summary: str; principles: str; tradeoffs: str; alternatives: str
    detection: DetectionRules
    references: tuple[str, ...]

def load_ontology(directory: Path) -> dict[str, Concept]
```

- 校验：必填字段齐全、`id` 唯一、`category` 合法、`detection` 键合法。
- **校验失败要报错**（不是静默跳过）——本体是自己写的，出错要立刻发现。
- 本体版本号写进 `repo_state.concept_version`，改了版本号就重跑检测。

### 2.3 B3 · 检测器 `concepts/detector.py`

```python
class RuleBasedDetector(ConceptDetector):
    def detect(self, symbols: Sequence[SymbolView], edges: Sequence[EdgeView]) -> list[ConceptInstance]
```

- 逐条规则在 `SymbolView` / `EdgeView` 上跑，产出 `ConceptInstance`。
- **`evidence` 必须写清命中了什么**，例：`import jwt` / `decorator @app.get` /
  `call redis.Redis` / `inherits Base`。
- `confidence` < 1 表示推断出来的（例：`string_markers` 命中 → 0.7）。
- 与 `concept_instance` 表的对接由 A 线提供写入函数，B 线只产出 `ConceptInstance` 列表。

**验收**：对织忆 `agent-v1` 跑一遍，人工核对实例准确率 **≥ 0.8**；
每个实例都能说清"为什么认定这里用了这个概念"。

### 2.4 B4 · 三级深度解释 `concepts/explain.py`

```python
def explain(concept: Concept, *, instances: list[ConceptInstance],
            relations: list[Relation], depth: ConceptDepth,
            provider: LLMProvider | None = None) -> Explanation
```

| 深度 | 内容 | 调 LLM？ | 延迟要求 |
|---|---|---|---|
| `quick` 快速理解 | 概念是什么、用途 | **不调**，直接读本体 `summary` | 瞬时 |
| `project` 结合项目 | 在本项目的实现位置 + 执行方式 + **与其他模块的关系** | 只做轻量串场 | <1s |
| `deep` 深入探索 | 原理 + 设计权衡 + 其他实现方式 + 与现有代码的联系 | 调 | 可慢 |

- `project` 级的"位置/执行方式/调用关系"**全部从索引自动派生**，不是 LLM 猜的。
- `deep` 级的输出**必须分 facts / inferences**（ADR 0007），facts 要带 `file:line`。

### 2.5 B5 · 知识关联检索（供检索层使用）

- 概念通道：用户问"这个项目用了什么缓存机制"时，
  按概念本体匹配出相关概念 → 返回其实例 → 作为**第四路检索**参与 RRF。
- 这一路的检索实现由 A 线负责（`retrieval/concept_lane.py`），
  **B 线提供的是"概念 → 实例"的查询能力**。

### 2.6 B6 · 评测配合（M5）

- 提供 concept 臂的检测结果：**给定一个概念 id，列出所有实例**。
- 配合人工标注 **gold set**：在织忆 `agent-v1` 上人工标注 30 个
  "概念 → 实例"对，用于算 P / R / F1。

### 2.7 B7 · 设计说明过期检测的概念侧（M6）

- `design_decision.claims_json` 里的 `concept_id` + `pattern`，
  与 `concept_instance` 比对：**声称的机制在代码里还有没有**。
- 这是 §2.4 第 5 问的实现。

---

## 3. C 线（前端 + API）

> 归属：`frontend/` + `src/codeinsight/api/`

### 3.1 C1 · API 端点

```
GET  /health
GET  /projects
POST /projects                              body: {root_path, ref?}   建索引（异步）
GET  /projects/{id}
GET  /projects/{id}/overview                项目概览（技术栈/模块职责/入口）
GET  /projects/{id}/files                   文件树
GET  /projects/{id}/symbols?q=&kind=&limit= 符号列表
GET  /projects/{id}/symbols/{qualname}      符号详情（定义 + 引用 + 关系）
GET  /projects/{id}/symbols/{qualname}/callers
GET  /projects/{id}/symbols/{qualname}/callees
GET  /projects/{id}/flows                   关键业务流程
GET  /projects/{id}/concepts                概念列表（含实例数）
GET  /projects/{id}/concepts/{concept_id}   概念详情（本体 + 实例数）
GET  /projects/{id}/concepts/{concept_id}/instances
POST /projects/{id}/concepts/{concept_id}/explain   body: {depth: quick|project|deep}
GET  /projects/{id}/changes?since=          变更说明
POST /query                                 非流式问答
POST /query/stream                          SSE 流式问答
```

**契约在 `docs/api-contract.md`（A 线本周补），实现照它做。**

### 3.2 C2 · SSE 事件词汇表

```
event: meta     data: {task_id, conversation_id, model, tools[]}
event: delta    data: {text}                      文本增量
event: tool     data: {name, status, summary}     工具调用开始/结束
event: evidence data: {path, lineno, end_lineno, qualname, snippet, lanes[], concepts[]}
event: answer   data: {facts[], inferences[], citations[], abstained, reason}
event: error    data: {code, title, hint}
event: done     data: {abstained, reason}
```

- `evidence` 事件让前端能**边流边渲染证据面板**，不必等最终答案。
- `answer` 事件的 `facts[]` 与 `inferences[]` 前端**必须分开显示**（ADR 0007）。

### 3.3 C3 · 前端：**复制织忆前端基建，只换业务组件**

> **决策**：CodeInsight 的前端**不做视觉设计**。直接复制织忆 `ai-companion-agent@agent-v1`
> 的 `frontend/` 基建（Apache-2.0，出处见 `docs/ported-from-tapestry.md`），
> 只重写业务相关的组件与 API 模块。
>
> 这样 C 线的工作从"设计 + 实现"降级为"复制 + 替换"，设计风险归零，
> 也保证两个项目观感一致。

#### 依赖（与织忆完全一致，只多两个）

```json
"dependencies": {
  "@tailwindcss/vite": "^4.3.0", "lucide-react": "^1.42.0",
  "react": "^19.2.6", "react-dom": "^19.2.6",
  "react-markdown": "^10.1.0", "tailwindcss": "^4.3.0", "zustand": "^5.0.13",
  "@monaco-editor/react": "^4.6.0",   // 新增：证据面板代码查看（懒加载）
  "reactflow": "^11.11.0"             // 新增：M8 关系图
}
```

**Monaco 必须懒加载**（`React.lazy`）——它有 ~5 MB，
不懒加载会让首屏白屏，违背 §2.1 收尾句「用户不需要逐个打开文件阅读」。

#### ✅ 直接复制（只改 import 路径，不改逻辑）

| 来源（织忆 `frontend/`） | 说明 |
|---|---|
| `vite.config.ts` | **SSE proxy 段必须保留**——`text/event-stream` 响应要注入 `X-Accel-Buffering: no` 与 `Cache-Control: no-cache` |
| `tsconfig.json` `tsconfig.app.json` `tsconfig.node.json` `eslint.config.js` | 原样 |
| `index.html` `public/` | 原样 |
| `src/index.css` | Tailwind 4 入口 + 主题变量 |
| `src/theme/palettes.ts` | 调色板 —— **CodeInsight 沿用同一套配色** |
| `src/store/themeStore.ts` | 主题 store |
| `src/hooks/useDelayedFlag.ts` | |
| `src/components/common/` **全部 11 个** | `Button` `Chip` `ConfirmDialog` `Modal` `Presence` `RetryableImage` `Select` `Skeleton` `Toast` `motion.ts` `selectOptions.ts` |
| `tests/helpers/http.ts` | SSE 测试夹具：`stubFetch` `fakeResponse` `sseResponse` `hangingSseResponse` `silentSseResponse` `FakeEventSource` |
| `tests/palettes.test.ts` `tests/motionTokens.test.ts` `tests/presence.test.ts` `tests/modalLayering.test.ts` `tests/selectDropdown.test.ts` | **通用件自带的测试一起带过来**——保证通用件没被改坏 |

#### 🔁 抄结构、不抄内容

| 来源 | 抄什么 | 换成什么 |
|---|---|---|
| `src/api/client.ts` | `BASE = '/api'` 模式 | 端口改成 8020 |
| `src/api/stream.ts` | 手写 SSE 解析（`getReader()` + `TextDecoder` + 按 `\n` 切行）+ **watchdog**（首字节 120s / 流中静默 30s 超时） | 事件类型换成 §3.2 的词汇表 |
| `src/api/agent.ts` | `jsonRequest<T>` + `AgentApiError(detail, status)` | 端点换成 CodeInsight 的 |
| `src/store/chatStore.ts` + `chatTypes.ts` + `chat*Actions.ts` | **vanilla store + `createXxxActions` slice 拆分 + 类型集中在一个 `types.ts`** 的组织法 | slice 换成 `projectStore` / `workbenchStore` / `chatStore` |
| `src/components/chat/MessageBubble.tsx` + `replySegments.ts` | `react-markdown` 渲染 + 分段 + `fixMarkdownBold` + 流式动画类名（`reply-text-in` / `reply-settled`） | 内容换成事实/推断双栏 |
| `src/components/chat/agentTimeline.ts` | 事件 → 时间线行的**投影**模式 | 换成 CodeInsight 的 SSE 事件 |
| `src/components/chat/ChatWindow.tsx` | 滚动吸底（`scrollAnchorRef` / `wasAtBottomRef`）+ 流式渲染骨架 | |
| `src/components/chat/InputBox.tsx` | 输入框骨架 | 去掉图片粘贴 / ASR 录音 / agent 模式切换 |
| `src/components/chat/AgentEventCard.tsx` | 按事件类型分支渲染卡片 | 换成 CodeInsight 的事件类型 |

#### ❌ 不要（织忆有、CodeInsight 用不上）

`src/pet/` 全部 · `pet.html`（桌宠双入口）· `src/components/{pet,creation,settings,character,sidebar,memory}/` ·
`src/api/{wx,branches,proactive,memory,asr,voice,uploads,downloads,dataManagement,providerSettings,session,theme,character*,settings}.ts` ·
`src/store/{characterStore,chatVoiceActions,chatCapabilityActions,chatBranchActions,chatHistory,voicePrefs,proactiveUnread}.ts` ·
`src/hooks/{useASRRecorder,useMemoryPanelData,useModeSetting}.ts` · `src/utils/audioWav.ts`

#### ✍️ CodeInsight 新写

```
frontend/src/
├── main.tsx                       重写（不再挂 pet.html）
├── App.tsx                        重写（三栏布局）
├── api/
│   ├── types.ts                   ← A 线提供并冻结
│   ├── client.ts                  抄织忆
│   ├── stream.ts                  抄织忆 + 换事件词汇表
│   ├── projects.ts  code.ts  concepts.ts  chat.ts   新写
│   └── mock.ts                    用 fixtures/sample-index.json
├── store/
│   ├── types.ts                   新写（类型集中）
│   ├── projectStore.ts             新写
│   ├── workbenchStore.ts          新写（当前选中符号/模块/概念）
│   ├── viewStore.ts               M8：中栏标签页 + 关系图中心
│   └── chatStore.ts + chatActions.ts  新写（抄织忆 slice 拆分法）
└── components/
    ├── workbench/                 三栏布局（新写）
    ├── tree/                      文件与符号树（新写）
    ├── chat/                      抄织忆骨架 + 新事件类型
    ├── center/                    M8：中栏标签栏（对话/关系图/时间线）
    ├── graph/                     M8：React Flow 关系图（纯函数布局可单测）
    ├── timeline/                  M8：演进时间线
    ├── evidence/                  证据面板（新写）+ Monaco 只读
    ├── concept/                   ★ 概念卡 + 代码侧 concept chips（新写）
    └── common/                    复制织忆
```

#### 交互约定（已对齐）

| 项 | 决定 |
|---|---|
| 三栏之外的第 4 视图 | **不要**（关系图与时间线是 M8 的**中栏标签页**，整体仍是三栏） |
| 概念卡形态 | **右栏替换**（不弹层——弹层会挡住证据） |
| Monaco | **要**，`@monaco-editor/react` 只读 + 懒加载 |
| 暗色模式 | 要（沿用织忆 `themeStore` + `palettes.ts`） |
| 状态管理 | Zustand，一个 store 一个 slice，不用 Redux |
| 界面语言 | **中文**（README 另出英文摘要） |

### 3.4 C4 · 三栏工作台

```
┌──────────────┬─────────────────────────┬──────────────┐
│  文件 / 符号  │      对话流（SSE）        │  证据面板     │
│  树          │                          │  file:line   │
│              │                          │  + 代码片段  │
│              │                          │  + 概念 chips │
└──────────────┴─────────────────────────┴──────────────┘
```

- 点符号 → 右栏显示定义与关系。
- 点代码片段里的概念 → 弹概念卡（快速理解 / 结合项目 / 深入探索三级）。
- 概念卡里的实例 → 跳回代码。**这是双向导航。**

**左栏的两条实现约定**（M8 期间修的坑，记在这里免得再犯）：

- **符号按需拉取**：契约 §0.4 的 `limit` 上限 500，织忆有 6543 个符号——
  一次性拉全量只覆盖按字母序的前 31 个文件，其余文件展开是空的。
  改成展开文件时按 `path` 拉该文件的符号；文件树自带 `symbol_count`，
  每个文件在未展开时就显示自己的符号数。
- **页脚总数用项目详情的 `symbols`**：不能用"已加载符号的条数"——
  那是"展开了多少"不是"一共有多少"。
- **搜索同时匹配路径与符号名**：符号名搜索走后端 `q` 查询
  （前端手上永远只有已展开那几个文件的符号）；搜索态下文件旁的数字
  是**命中数**，不是该文件的总符号数。

### 3.5 C5 · Mock 开发

- 用 `fixtures/sample-index.json`（A 线本周补）做 mock 数据层，
  **不必等后端跑起来**。
- `frontend/src/api/mock.ts`：按契约返回 fixture 里的数据。

### 3.6 C6 · 测试

- Vitest（与织忆一致：**无 `vitest.config.ts`、无 jsdom**，node 环境跑纯逻辑单测）。
- SSE 解析必须有测试：复用复制过来的 `tests/helpers/http.ts` 夹具
  （`sseResponse` / `hangingSseResponse` / `silentSseResponse` / `FakeEventSource`）。
- 通用件的测试（palettes / motionTokens / presence / modalLayering / selectDropdown）
  **原样带过来**，作为"复制过来的通用件没被改坏"的证明。

---

## 4. 集成节奏

| 频率 | 动作 | 负责人 |
|---|---|---|
| 每天 | 各分支提交；A 线合 feature 分支进 main，跑全量测试 | A 线 |
| 每天 | 契约变更走 `docs/requests/`，A 线统一改并同步 | A 线 |
| 每周 | 三线对齐：各自 demo + 说清下一步依赖 | 全部 |
| 里程碑 | 跑对应阶段的验收清单（见 `roadmap.md`） | A 线汇总 |

**main 的规矩**：只有 A 线能合；合之前 `pytest` + `ruff` 必须全绿；
测试红 = main 红 = 谁都别想推。

---

## 5. 术语对照（源文档 ↔ 代码）

| 源文档 | 代码 |
|---|---|
| 项目认知 | `storage/schema.sql` 里的索引表族 |
| 符号索引 | `symbol` / `module` 表 |
| 代码关系 | `edge` 表 |
| 关键业务流程 | `flow` / `flow_step` 表 |
| 重要设计说明及其证据 | `design_decision` / `design_decision_evidence` 表 |
| 知识点关联 | `concept` / `concept_instance` 表 |
| 项目架构摘要 | `project.architecture_summary` |
| 持续项目认知 | `repo_state` + `index_run` + `staleness_report` |
| 项目历史修改和测试记录 | `change_record` / `test_record` 表 |
| Agent 任务状态 | `agent_task` / `agent_event` 表 |
