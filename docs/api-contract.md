# API + SSE 契约 · 冻结

> **状态**：✅ 已冻结（A 线，M1）
> **配套**：[`frontend/src/api/types.ts`](../frontend/src/api/types.ts)（与本文一一对应）
> **适用范围**：C 线写 `src/codeinsight/api/` 与 `frontend/src/api/` 时**照本文实现，不要自己加字段**。
>
> 需要改动 → 走 [`requests/`](requests/README.md) 流程，A 线统一改。

---

## 0. 通用约定

### 0.1 前缀与端口

前端通过 vite proxy 访问，**浏览器侧一律带 `/api` 前缀**；后端路由本身不带前缀。

| 层 | 地址 |
|---|---|
| 浏览器 → 前端 dev server | `/api/*` |
| 前端 dev server → 后端 | `http://127.0.0.1:8020/*` |
| 后端自身 | `http://127.0.0.1:8020/*`（**无 `/api`**） |

`vite.config.ts` 的 proxy **必须**把 `/api` 前缀剥掉再转发（与织忆一致）。

### 0.2 内容类型

- 请求：`Content-Type: application/json`（`GET` 无 body 时不带）。
- 响应：除 SSE 外一律 `application/json; charset=utf-8`。
- SSE：`Content-Type: text/event-stream; charset=utf-8`。

### 0.3 错误响应

**所有**非 2xx 响应的 body 都是这个形状（**只有这一个**，不要自定义变体）：

```json
{
  "error": {
    "code": "project_not_found",
    "title": "项目不存在",
    "hint": "先 POST /projects 建索引，再使用返回的 id",
    "detail": "project_id=7 not found"
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | `string` | 机器可读的稳定标识，**前端可以 switch 它**，不要改 |
| `title` | `string` | 一句话中文说明，给人看 |
| `hint` | `string` | 下一步该做什么（可空串 `""`） |
| `detail` | `string` | 原始错误信息（可空串 `""`） |

**错误码表**（`code` 的取值全集）：

| code | HTTP | 含义 |
|---|---|---|
| `bad_request` | 400 | 参数不合法 |
| `project_not_found` | 404 | `project_id` 不存在 |
| `symbol_not_found` | 404 | 符号不存在 |
| `concept_not_found` | 404 | 概念不存在 |
| `not_indexed` | 409 | 项目还没建好索引 |
| `index_running` | 409 | 索引正在跑，重复提交 |
| `upstream_error` | 502 | 上游 LLM / embedding 服务出错 |
| `timeout` | 504 | 上游超时 |
| `internal_error` | 500 | 其它 |

> 前端**兜底**：遇到未知 `code` 一律按 `internal_error` 处理，不要白屏。

### 0.4 列表响应的分页

列表类端点统一：

- 查询参数 `limit`（默认 `50`，上限 `500`）、`offset`（默认 `0`）。
- 响应形状固定为 **`{items: [...], total: N}`**——`total` 是过滤后的总数，与 `items` 长度无关。

> 例外：`GET /projects`、`GET /projects/{id}/files` 返回**裸数组**（文件树是一次性拉全的，不需要分页）。
> 这两个例外在下面各自的章节里写明。

### 0.5 时间与标识符

- 所有时间戳是 **ISO 8601 UTC 字符串**（`2026-10-24T08:31:05Z`），不带时区偏移的本地时间。
- 所有 `id` 是**正整数**（SQLite 自增主键）。项目 id 在前端**持久化到 localStorage**（`ci.projectId`）。
- `qualname` 用点号分层：`backend.core.chunk_bm25.split_identifiers`。
  路径参数里**必须 URL 编码**（前端用 `encodeURIComponent`）。

### 0.6 命名

- JSON 字段一律 `snake_case`（与 Python 侧一致，避免两边各转一次）。
- 前端 TS 接口沿用 `snake_case` 字段名，**不做 camelCase 转换**——少一层映射，少一处错。

---

## 1. 枚举（全局共用）

这些取值在多个端点里出现，`types.ts` 里都有对应 union。

| 枚举 | 取值 |
|---|---|
| `SymbolKind` | `module` `class` `function` `method` `property` `constant` |
| `EdgeKind` | `call` `inherits` `imports` `decorator` `references` `returns` |
| `ConceptDepth` | `quick` `project` `deep` |
| `FileRole` | `source` `test` `vendored` `generated` `config` `doc` |
| `ConceptCategory` | `auth` `cache` `db` `concurrency` `async` `http` `config` `pattern` `data-structure` `security` `observability` `testing` `build` `other` |
| `RetrievalLane` | `bm25` `dense` `symbol` `concept` `neighbor` |
| `ToolStatus` | `running` `ok` `error` |
| `IndexMode` | `full` `incremental` |

> `RetrievalLane` 是**命中通道**，一条证据可以同时命中多路（`lanes` 是数组）。

---

## 2. 端点清单速查

| 方法 | 路径 | 用途 | 状态 |
|---|---|---|---|
| `GET` | `/health` | 存活 + 索引库状态 | ✅ 已实现 |
| `GET` | `/projects` | 已索引项目列表 | ✅ 已实现 |
| `POST` | `/projects` | 导入项目并建索引 | ⬜ M1 |
| `GET` | `/projects/{id}` | 项目详情 | ⬜ M1 |
| `GET` | `/projects/{id}/overview` | 项目概览 | ⬜ M2 |
| `GET` | `/projects/{id}/files` | 文件树 | ⬜ M1 |
| `GET` | `/projects/{id}/symbols` | 符号列表 | ⬜ M1 |
| `GET` | `/projects/{id}/symbols/{qualname}` | 符号详情 | ⬜ M2 |
| `GET` | `/projects/{id}/symbols/{qualname}/callers` | 调用者 | ⬜ M2 |
| `GET` | `/projects/{id}/symbols/{qualname}/callees` | 被调者 | ⬜ M2 |
| `GET` | `/projects/{id}/flows` | 关键业务流程 | ⬜ M2 |
| `GET` | `/projects/{id}/concepts` | 概念列表 | ⬜ M1.5 |
| `GET` | `/projects/{id}/concepts/{concept_id}` | 概念详情 | ⬜ M1.5 |
| `GET` | `/projects/{id}/concepts/{concept_id}/instances` | 概念实例 | ⬜ M1.5 |
| `POST` | `/projects/{id}/concepts/{concept_id}/explain` | 三级深度解释 | ⬜ M1.5 |
| `GET` | `/projects/{id}/changes` | 变更说明 | ⬜ M6 |
| `POST` | `/query` | 非流式问答 | ⬜ M3 |
| `POST` | `/query/stream` | **SSE** 流式问答 | ⬜ M3 |

---

## 3. 项目与索引

### 3.1 `GET /health`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "db_path": "<仓库根>/.ci/codeinsight.db",
  "db_exists": true,
  "schema_applied": true,
  "projects": 1
}
```

**已实现，前端可以直接用**（前端启动时探测后端是否就绪）。

---

### 3.2 `GET /projects`

返回**裸数组**（不分页——项目数量个位数）。

```json
[
  {
    "id": 1,
    "name": "tapestry",
    "root_path": "<被测仓库>",
    "head_commit": "9b5ad71b...",
    "head_branch": "agent-v1",
    "indexed_at": "2026-10-24T08:31:05Z",
    "index_epoch": 3,
    "files": 696,
    "symbols": 4210,
    "chunks": 5180
  }
]
```

> `files` / `symbols` / `chunks` 是三个计数（`COUNT(*)`），前端用来显示"索引规模"。

---

### 3.3 `POST /projects` — 导入并建索引

**请求**：

```json
{
  "root_path": "<被测仓库>",
  "ref": "agent-v1",
  "name": "tapestry"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `root_path` | `string` | ✅ | 本地仓库根目录（绝对路径） |
| `ref` | `string` | ❌ | git ref（分支/tag/commit）。缺省 = 当前 HEAD |
| `name` | `string` | ❌ | 项目显示名。缺省 = 目录名 |

**响应 `202 Accepted`**（建索引是异步的，不能同步阻塞）：

```json
{
  "id": 1,
  "name": "tapestry",
  "root_path": "<被测仓库>",
  "status": "indexing",
  "head_commit": "9b5ad71b...",
  "head_branch": "agent-v1"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | `"indexing"` | 建索引中。**轮询 `GET /projects/{id}` 直到 `status !== "indexing"`** |

**错误**：
- `bad_request` — `root_path` 不存在 / 不是 git 仓库
- `index_running` — 该项目已在索引中

> **索引进度**：本期不提供进度端点。前端 `GET /projects/{id}` 轮询即可（见 3.4）。

---

### 3.4 `GET /projects/{id}` — 项目详情

```json
{
  "id": 1,
  "name": "tapestry",
  "root_path": "<被测仓库>",
  "status": "ready",
  "head_commit": "9b5ad71b...",
  "head_branch": "agent-v1",
  "indexed_at": "2026-10-24T08:31:05Z",
  "index_epoch": 3,
  "files": 696,
  "symbols": 4210,
  "chunks": 5180,
  "edges": 15320,
  "concepts": 18,
  "concept_instances": 233
}
```

`status` 取值：`indexing` `ready` `failed` `stale`

> `stale` = 代码已变但还没重建索引（`repo_state.head_commit` ≠ 当前 HEAD）。
> 前端可以在顶栏显示一个"索引已过期，点击重建"的小提示。

---

### 3.5 `GET /projects/{id}/overview` — 项目概览

源文档 §2.1-5/6/7：**"用户不需要逐个打开文件阅读，即可先了解整个项目的基本构成"**。

```json
{
  "project_id": 1,
  "architecture_summary": "织忆是一个基于 FastAPI 的桌面伴侣服务……（一段话，从真实数据生成）",
  "languages": [
    { "language": "python", "files": 389, "lines": 42800 }
  ],
  "frameworks": ["fastapi", "uvicorn", "pydantic", "httpx"],
  "entry_points": [
    { "kind": "console_script", "target": "ai_companion:main", "source_path": "pyproject.toml", "doc": "桌面端启动入口" },
    { "kind": "file", "target": "backend/main.py:app", "source_path": "backend/main.py", "doc": null }
  ],
  "core_modules": [
    {
      "qualname": "backend.core.chat_orchestrator",
      "path": "backend/core/chat_orchestrator.py",
      "responsibility": "对话编排：意图识别 → 工具选择 → 流式响应",
      "docstring": "对话主循环……",
      "is_core": true,
      "out_degree": 42,
      "in_degree": 17
    }
  ],
  "dependencies": [
    { "name": "fastapi", "version": ">=0.115", "source": "pyproject" },
    { "name": "httpx", "version": "", "source": "import", "declared": false }
  ],
  "stats": {
    "files": 696,
    "python_files": 389,
    "symbols": 4210,
    "edges": 15320,
    "concepts": 18,
    "flows": 6
  }
}
```

| 字段 | 说明 |
|---|---|
| `core_modules` | 按重要性排序，最多 **20** 个 |
| `dependencies[].source` | `pyproject` \| `requirements` \| `import`（声明了但没在依赖表里的，标 `declared: false`） |
| `architecture_summary` | **从真实数据生成**，不是模型编的（可以是模板拼接，但每个数字都来自索引） |

---

### 3.6 `GET /projects/{id}/files` — 文件树

返回**裸数组**（一次拉全；696 个文件 ≈ 60KB，可接受）。

```json
[
  {
    "path": "backend/core/chat_orchestrator.py",
    "language": "python",
    "role": "source",
    "content_sha256": "3f8a...",
    "size_bytes": 96213,
    "line_count": 2229,
    "symbol_count": 31
  }
]
```

`role` 取值见 §1 的 `FileRole`：

| role | 含义 |
|---|---|
| `source` | 正常业务代码 |
| `test` | 测试文件（`tests/`、`test_*.py`、`*_test.py`） |
| `vendored` | 第三方代码（如 `mobile_sam/`、`build_cache/`）——**默认不索引** |
| `generated` | 生成代码（`__init__.py` 里的 re-export、`*.pb.go`） |
| `config` | 配置文件（`pyproject.toml`、`*.yaml`） |
| `doc` | 文档（`*.md`） |

> **前端必须把 `vendored` / `generated` 折叠或弱化显示**——它们不是项目自己的代码。

---

## 4. 符号

### 4.1 `GET /projects/{id}/symbols` — 符号列表

**查询参数**：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `q` | `string` | — | 模糊匹配 `qualname` / `name` / `docstring` |
| `kind` | `SymbolKind` | — | 按种类过滤 |
| `path` | `string` | — | 按文件过滤（精确路径或目录前缀） |
| `limit` | `int` | `50` | |
| `offset` | `int` | `0` | |

**响应**：

```json
{
  "items": [
    {
      "id": 1832,
      "qualname": "backend.core.chunk_bm25.split_identifiers",
      "name": "split_identifiers",
      "kind": "function",
      "path": "backend/core/chunk_bm25.py",
      "lineno": 29,
      "end_lineno": 61,
      "header": "def split_identifiers(text: str) -> list[str]:",
      "docstring": "把标识符拆成检索用的 token……",
      "n_lines": 33,
      "is_async": false,
      "is_private": false,
      "is_dunder": false,
      "in_degree": 12,
      "out_degree": 3,
      "concept_ids": ["db-transaction"]
    }
  ],
  "total": 4210
}
```

> `in_degree` / `out_degree` 是**关系图的度**——用来判断"重要符号"（源文档 §2.1-4）。
> `concept_ids` 让前端能在符号树上直接挂概念标签（§2.2-7）。

---

### 4.2 `GET /projects/{id}/symbols/{qualname}` — 符号详情

```json
{
  "id": 1832,
  "qualname": "backend.core.chunk_bm25.split_identifiers",
  "name": "split_identifiers",
  "kind": "function",
  "path": "backend/core/chunk_bm25.py",
  "lineno": 29,
  "end_lineno": 61,
  "header": "def split_identifiers(text: str) -> list[str]:",
  "docstring": "把标识符拆成检索用的 token……",
  "n_lines": 33,
  "is_async": false,
  "is_private": false,
  "is_dunder": false,
  "in_degree": 12,
  "out_degree": 3,
  "concept_ids": ["db-transaction"],
  "callers": [
    { "qualname": "backend.retrieval.bm25.build_query", "path": "backend/retrieval/bm25.py", "lineno": 88, "confidence": 1.0 }
  ],
  "callees": [
    { "qualname": "backend.core.tokenizer.jieba_cut", "path": "backend/core/tokenizer.py", "lineno": 12, "confidence": 1.0 }
  ],
  "references": [
    { "qualname": "backend.indexing.chunker.chunk_symbol", "path": "backend/indexing/chunker.py", "lineno": 120, "confidence": 1.0 }
  ],
  "source": "def split_identifiers(text: str) -> list[str]:\n    ...（带行号的原文）"
}
```

| 字段 | 说明 |
|---|---|
| `callers` / `callees` / `references` | 每项是 `{qualname, path, lineno, confidence}`；`confidence < 1` = **动态调用等静态分析定不了的**，前端要标"不确定" |
| `source` | 符号的完整源码（带行号前缀，便于直接显示） |

> 若同名符号有多个（`main` 在织忆里定义了 33 次），本端点返回**第一个**，
> 且响应里附 `"ambiguous": true` + `"alternatives": [同名的其它符号]`。
> 前端要能提示"该名字有 N 处定义"。

---

### 4.3 `GET /projects/{id}/symbols/{qualname}/callers`

```json
{
  "items": [
    {
      "src_qualname": "backend.retrieval.bm25.build_query",
      "src_path": "backend/retrieval/bm25.py",
      "lineno": 88,
      "confidence": 1.0,
      "uncertain": false,
      "note": null
    }
  ],
  "total": 12
}
```

| 字段 | 说明 |
|---|---|
| `uncertain` | `confidence < 1` 时为 `true`；前端显示"⚠ 可能" |
| `note` | 例如 `"动态调用 getattr 解析，静态分析不确定"` |

### 4.4 `GET /projects/{id}/symbols/{qualname}/callees`

形状与 4.3 相同，方向相反（src 是本符号）。

---

## 5. 关键业务流程

### 5.1 `GET /projects/{id}/flows`

```json
{
  "items": [
    {
      "id": 3,
      "name": "对话消息处理主链路",
      "description": "从 HTTP 入口到流式响应落地的完整链路",
      "entry_qualname": "backend.api.chat.stream_chat",
      "steps": [
        { "ordinal": 1, "qualname": "backend.api.chat.stream_chat", "path": "backend/api/chat.py", "lineno": 42, "note": "入口" },
        { "ordinal": 2, "qualname": "backend.core.chat_orchestrator.prepare_chat_stream", "path": "backend/core/chat_orchestrator.py", "lineno": 1180, "note": "组装上下文" },
        { "ordinal": 3, "qualname": "backend.core.chat_orchestrator._dispatch_tool", "path": "backend/core/chat_orchestrator.py", "lineno": 1402, "note": "外部副作用：调用工具" }
      ]
    }
  ],
  "total": 6
}
```

> `steps` 是**有序**的（`ordinal`），前端画流程条直接用。
> `note` 标出"有外部副作用"的节点（写文件 / 发请求 / 落库）——这是源文档 §2.1-6 的定义。

---

## 6. 知识层（源文档 §2.6）

### 6.1 `GET /projects/{id}/concepts` — 概念列表

**查询参数**：`q`（按 name / id / summary 过滤）、`category`

**响应**：

```json
{
  "items": [
    {
      "concept_id": "redis-cache",
      "name": "缓存机制",
      "category": "cache",
      "summary": "用 Redis 做分布式缓存，把重复计算与热点查询挡在数据库之前。",
      "instance_count": 7,
      "first_instance_path": "backend/core/cache.py"
    }
  ],
  "total": 18
}
```

### 6.2 `GET /projects/{id}/concepts/{concept_id}` — 概念详情

```json
{
  "concept_id": "redis-cache",
  "name": "缓存机制",
  "category": "cache",
  "summary": "……",
  "principles": "……",
  "tradeoffs": "……",
  "alternatives": "……",
  "references": ["https://redis.io/docs/…"],
  "instance_count": 7,
  "instance_paths": ["backend/core/cache.py", "backend/core/llm_cache.py"]
}
```

> `summary` / `principles` / `tradeoffs` / `alternatives` 直接来自**本体 YAML**（`knowledge/concepts/<id>.yaml`），
> **不是模型生成的**——所以 `quick` 级解释不调 LLM（源文档 §2.6）。

### 6.3 `GET /projects/{id}/concepts/{concept_id}/instances` — 概念实例

```json
{
  "items": [
    {
      "id": 41,
      "concept_id": "redis-cache",
      "path": "backend/core/cache.py",
      "lineno": 88,
      "qualname": "backend.core.cache.get_or_set",
      "symbol_id": 2103,
      "evidence": "call redis.Redis",
      "confidence": 1.0,
      "snippet": "def get_or_set(key: str, ...):\n    ...（该行附近的源码）"
    }
  ],
  "total": 7
}
```

> `evidence` 是**命中了哪条规则**（`import redis` / `call redis.Redis` / `decorator @app.get` / `inherits Base`）。
> 前端**必须显示它**——这是"结论可追溯"的界面体现（源文档 §2.6）。

### 6.4 `POST /projects/{id}/concepts/{concept_id}/explain` — 三级深度解释

**请求**：

```json
{ "depth": "project" }
```

`depth` ∈ `quick` | `project` | `deep`（`ConceptDepth`）。

**响应**：

```json
{
  "concept_id": "redis-cache",
  "depth": "project",
  "summary": "……",
  "facts": [
    { "text": "本项目在 backend/core/cache.py 使用 Redis 做 LLM 响应缓存", "citation": { "path": "backend/core/cache.py", "lineno": 88, "end_lineno": 120, "qualname": "backend.core.cache.get_or_set" } }
  ],
  "inferences": [
    { "text": "缓存键似乎包含模型名与 prompt 摘要", "confidence": 0.6 }
  ],
  "instances": [ /* 同 6.3 的项 */ ],
  "llm_used": false
}
```

| 字段 | 说明 |
|---|---|
| `depth=quick` | **不调 LLM**，`llm_used` 恒为 `false`，`facts` 为空，只有 `summary` |
| `depth=project` | 位置/调用关系**全部从索引自动派生**，不进 `inferences`；只做轻量串场 |
| `depth=deep` | 调 LLM，`facts` 必须带 `citation`（`file:line`），`inferences` 显式标注 |

> **前端必须分开渲染 `facts` 和 `inferences`**（ADR 0007）。
> `facts` 是可验证的（带 `file:line`），`inferences` 是模型的。

---

## 7. 变更（源文档 §2.5）

### 7.1 `GET /projects/{id}/changes`

**查询参数**：`since`（commit sha 或分支名；缺省 = 上次索引的 commit）

```json
{
  "since": "9b5ad71b...",
  "head": "c1d2e3f...",
  "summary": "本次更新新增了 3 个文件，修改了 12 个；核心影响集中在聊天编排与缓存层。",
  "files": {
    "added":   [ { "path": "backend/core/new_tool.py", "status": "A" } ],
    "modified":[ { "path": "backend/core/chat_orchestrator.py", "status": "M", "changed_symbols": 6 } ],
    "deleted": [ { "path": "backend/legacy/old.py", "status": "D" } ]
  },
  "changed_symbols": [
    { "qualname": "backend.core.chat_orchestrator.prepare_chat_stream", "path": "backend/core/chat_orchestrator.py", "lineno": 1180, "change": "signature_changed" }
  ],
  "impacted": {
    "modules": ["backend.core.chat_orchestrator"],
    "symbols": [ { "qualname": "backend.api.chat.stream_chat", "path": "backend/api/chat.py", "lineno": 42 } ],
    "concept_ids": ["redis-cache"]
  },
  "tests": [
    { "nodeid": "tests/test_chat.py::test_stream", "outcome": "passed", "duration_s": 0.42 }
  ],
  "stale_design_decisions": [
    { "doc_id": "ADR-0012", "title": "使用文件锁保护缓存刷新", "reason": "声称的 file-lock 机制在当前代码中未找到实例" }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `changed_symbols[].change` | `added` `removed` `signature_changed` `body_changed` `docstring_changed` `moved` |
| `impacted.symbols` | **反向可达**集合——改这些函数会影响谁（源文档 §2.2-5） |
| `stale_design_decisions` | **设计说明过期**（源文档 §2.4 第 5 问）——"哪些历史设计说明已不再适用" |

> 这一端点是 M6 的。**M1–M5 期间返回 `{"files": {"added": [], "modified": [], "deleted": []}, ...}` 空壳**，字段不删不改。
> 前端现在就按完整形状写，之后不用改。

---

## 8. 问答

### 8.1 `POST /query` — 非流式

**请求**：

```json
{
  "project_id": 1,
  "question": "这个项目的对话流程是怎么走的？",
  "conversation_id": "conv-20261024-001"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `project_id` | `int` | ✅ | |
| `question` | `string` | ✅ | |
| `conversation_id` | `string` | ❌ | 缺省 = 新会话；带同一个值 = **连续追问**（源文档 §2.3-5） |

**响应**：

```json
{
  "text": "……面向用户的回答……",
  "facts": [
    { "text": "入口是 backend/api/chat.py 的 stream_chat", "citation": { "path": "backend/api/chat.py", "lineno": 42, "end_lineno": 60, "qualname": "backend.api.chat.stream_chat", "snippet": "def stream_chat(...)" } }
  ],
  "inferences": [
    { "text": "整体是单请求内的同步编排，没有引入队列", "confidence": 0.7 }
  ],
  "citations": [
    { "path": "backend/api/chat.py", "lineno": 42, "end_lineno": 60, "qualname": "backend.api.chat.stream_chat", "snippet": "def stream_chat(...)" }
  ],
  "tools_used": ["search_code", "get_callers", "get_flow"],
  "abstained": false,
  "abstention_reason": "",
  "evidence": [
    { "chunk_id": 512, "path": "backend/api/chat.py", "lineno": 42, "end_lineno": 60, "qualname": "backend.api.chat.stream_chat", "snippet": "...", "score": 0.87, "lanes": ["bm25", "symbol"], "concept_ids": [] }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `facts[].citation` | **每条 fact 必须有 citation**（源文档 §2.3-4）。缺了就说明这条是推断 |
| `inferences[]` | `{text, confidence}`——**模型推断，显式标注** |
| `abstained` | `true` = 检索无命中，**明确弃答** |
| `abstention_reason` | `abstained=true` 时必填，其它情况为空串 |
| `evidence` | 本次用到的证据（前端右栏渲染） |

> **`abstained=true` 时 `text` 也要写清楚"没找到"**，不能是空的。

---

### 8.2 `POST /query/stream` — SSE 流式

**请求**：与 8.1 完全相同。

**响应**：`Content-Type: text/event-stream`，事件序列见 §8.3。

> **代理层注意**（C 线 `vite.config.ts` 必看）：
> SSE 响应必须注入 `X-Accel-Buffering: no` 与 `Cache-Control: no-cache`，
> 否则 nginx / 某些代理会把流缓冲住，前端收不到增量。

---

### 8.3 SSE 事件词汇表（冻结）

**帧格式**（标准 SSE）：

```
event: <name>
data: <json>

```

`data` 永远是**单行 JSON**（不含裸换行）。**每个事件都以空行结尾**。

#### 事件清单

| event | 何时发 | data 形状 |
|---|---|---|
| `meta` | **第一个**，紧接着连接建立 | `{task_id, conversation_id, model, tools[]}` |
| `delta` | 文本增量，可多次 | `{text}` |
| `tool` | 工具调用开始/结束 | `{name, status, summary}` |
| `evidence` | 检索到证据，可多次 | `{path, lineno, end_lineno, qualname, snippet, lanes[], concepts[]}` |
| `answer` | 最终答案，**一次** | `{facts[], inferences[], citations[], abstained, reason}` |
| `error` | 出错，可多次 | `{code, title, hint}` |
| `done` | **最后一个**，流结束 | `{abstained, reason}` |

#### 逐个说明

**`meta`**

```json
{ "task_id": "task-018f", "conversation_id": "conv-001", "model": "deepseek-chat", "tools": ["search_code", "find_symbol", "read_file", "get_callers", "get_callees", "list_concepts", "explain_concept", "find_concept_instances", "get_flow", "get_changes", "get_design_decisions", "get_module_overview"] }
```

> `tools` 是**本次可用工具的名字列表**（不是 schema）。前端用它显示"这次能调什么"。

**`delta`**

```json
{ "text": "这个项目的对话流" }
```

**`tool`**

```json
{ "name": "search_code", "status": "running", "summary": "搜索 \"对话流程\"" }
```

`status` ∈ `running` `ok` `error`。`running` → 后续还有一个 `status: "ok"` 或 `"error"` 的同名事件。
`summary` 是**中文短句**（≤ 40 字），直接显示在时间线上。

**`evidence`**

```json
{ "path": "backend/api/chat.py", "lineno": 42, "end_lineno": 60, "qualname": "backend.api.chat.stream_chat", "snippet": "def stream_chat(...)", "lanes": ["bm25", "symbol"], "concepts": ["async"] }
```

> `lanes` 是 `RetrievalLane[]`；`concepts` 是概念 id 数组（**代码侧 concept chips 的数据源**，源文档 §2.6 双向导航）。
> **前端要边流边渲染证据面板**，不必等 `answer`。

**`answer`**

```json
{
  "facts": [ { "text": "入口是 stream_chat", "citation": { "path": "backend/api/chat.py", "lineno": 42, "end_lineno": 60, "qualname": "backend.api.chat.stream_chat", "snippet": "..." } } ],
  "inferences": [ { "text": "整体是同步编排", "confidence": 0.7 } ],
  "citations": [ { "path": "backend/api/chat.py", "lineno": 42, "end_lineno": 60, "qualname": "backend.api.chat.stream_chat", "snippet": "..." } ],
  "abstained": false,
  "reason": ""
}
```

> `facts` 与 `inferences` **必须分开显示**（ADR 0007）。
> `facts[].citation` **必须有**——没有 `file:line` 的 fact 不该出现在 `facts` 里。
> `reason` = 弃答原因（`abstained=true` 时填，其余空串）。

**`error`**

```json
{ "code": "upstream_error", "title": "模型服务返回 502", "hint": "检查 CI_LLM_API_KEY 与 CI_LLM_BASE_URL" }
```

> `code` 取值同 §0.3 错误码表。**流中途出错后仍然会发 `done`**（前端据此收尾）。

**`done`**

```json
{ "abstained": false, "reason": "" }
```

> **`done` 一定会发**，哪怕前面发了 `error`。前端的 `finally` 必须能收尾。

#### 事件顺序

```
meta
  ├─ tool(running) → tool(ok)      ← 可重复、交错
  ├─ evidence                       ← 可重复
  ├─ delta                          ← 可重复、可与上面交错
  └─ answer                         ← 恰好一次
done                                ← 恰好一次，最后
```

**约束**：
- `meta` 恰好一次，且是第一个。
- `answer` 与 `done` 各恰好一次。
- `error` 可以有 0 次或多次，但**不影响 `done` 必发**。

---

## 9. C 线对接清单

写代码时对着这张表：

| 你要写的 | 照哪里 |
|---|---|
| 类型定义 | `frontend/src/api/types.ts`（**已提供**，一一对应本文） |
| 请求 URL | 本文 §2 速查表 |
| 响应字段 | 本文各章节的 JSON 示例 |
| 错误处理 | §0.3（**只有 `error` 这一个变体**） |
| SSE 解析 | §8.3 事件词汇表 + 织忆 `tests/helpers/http.ts` 夹具 |
| 分页 | §0.4（`{items, total}`） |
| mock 数据 | `fixtures/sample-index.json` |

**三处最容易写错的地方**：

1. **`facts` 和 `inferences` 不能合到一起渲染**（ADR 0007）——这是本项目的主张之一，不是风格问题。
2. **SSE 的 `done` 事件必发**——`error` 之后也要发，否则前端挂死。
3. **`citation` 在结构化字段里，不在 `text` 里**——截断 `text` 不能丢引用（ADR 0006）。

---

## 10. 变更历史

| 日期 | 变更 |
|---|---|
| 2026-10-24 | 初版，M1 冻结 |
