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
| `POST` | `/projects` | 导入项目并建索引 | ✅ M1 |
| `GET` | `/projects/{id}` | 项目详情 | ✅ M1 |
| `GET` | `/projects/{id}/overview` | 项目概览 | ✅ M2 |
| `GET` | `/projects/{id}/files` | 文件树 | ✅ M1 |
| `GET` | `/projects/{id}/symbols` | 符号列表 | ✅ M1 |
| `GET` | `/projects/{id}/symbols/{qualname}` | 符号详情 | ✅ M2 |
| `GET` | `/projects/{id}/symbols/{qualname}/callers` | 调用者 | ✅ M2 |
| `GET` | `/projects/{id}/symbols/{qualname}/callees` | 被调者 | ✅ M2 |
| `GET` | `/projects/{id}/graph` | 符号邻域关系图（可选 `qualname`） | ✅ M8 |
| `GET` | `/projects/{id}/flows` | 关键业务流程 | ✅ M2 |
| `GET` | `/projects/{id}/concepts` | 概念列表 | ✅ M1.5 |
| `GET` | `/projects/{id}/concepts/{concept_id}` | 概念详情 | ✅ M1.5 |
| `GET` | `/projects/{id}/concepts/{concept_id}/instances` | 概念实例 | ✅ M1.5 |
| `POST` | `/projects/{id}/concepts/{concept_id}/explain` | 三级深度解释 | ✅ M1.5 |
| `GET` | `/projects/{id}/changes` | 变更说明 | ✅ M6 |
| `GET` | `/projects/{id}/timeline` | 索引与变更的时间轴 | ✅ M8 |
| `POST` | `/query` | 非流式问答 | ✅ M3 |
| `POST` | `/query/stream` | **SSE** 流式问答 | ✅ M3 |
| `GET` | `/knowledge/tree` | 内置教材目录（不依赖项目库） | ✅ M3 |
| `GET` | `/knowledge/topics/{topic_id}` | 教材主题正文与章节 | ✅ M3 |
| `GET` | `/knowledge/search` | 教材检索（`q` / `limit`） | ✅ M3 |

---

## 3. 项目与索引

### 3.1 `GET /health`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "db_path": "D:/path/to/CodeInsight/.ci/codeinsight.db",
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
    "root_path": "D:/path/to/some-repo",
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
  "root_path": "D:/path/to/some-repo",
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
  "root_path": "D:/path/to/some-repo",
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

受理时先预留运行记录，重复导入也会立即进入 `indexing`，不会把旧 `ready` 当作新任务完成。
该记录由后台索引事务收尾，失败保留旧索引；重启中断标为失败。前端状态读取失败仅代表
检查中断，不能推断索引失败或自动重复提交。

---

### 3.4 `GET /projects/{id}` — 项目详情

源码目录迁移或失效时，可调用 `POST /projects/{id}/relocate`，请求体为
`{"root_path":"D:/new/repo"}`，响应 202 复用 §3.3 的导入响应。所选路径须为有有效 HEAD 的
Git 仓库根目录。保留项目 ID、名称和会话；轮询本接口观察重建结果。
索引或回答进行中返回 409 `index_running`。后台成功时在同一事务内提交源码路径和完整
索引；失败回滚，原索引与路径保留。重启中断后标为失败并允许重新定位重试。
详情增加可选 `index_error: string | null`，包含最新一次索引失败说明。

```json
{
  "id": 1,
  "name": "tapestry",
  "root_path": "D:/path/to/some-repo",
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
| `path` | `string` | — | 按文件过滤（精确路径或目录前缀；`_` 与 `%` 按**普通字符**处理，不当通配符） |
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
>
> **`limit` 上限 500 意味着"符号全量"拿不到**：织忆这类项目有 6543 个符号。
> 前端左栏因此改成**展开文件时按 `path` 拉该文件的符号**，不一次性拉全量
> （一次性拉只会覆盖按字母序的前 31 个文件，其余文件展开是空的）。
> 文件树 `GET /projects/{id}/files` 自带每个文件的 `symbol_count`，
> 页脚总数用项目详情的 `symbols`，不用已加载符号的长度。

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

### 4.5 `GET /projects/{id}/graph` — 符号邻域关系图

**查询参数**

| 参数 | 默认 | 说明 |
|---|---|---|
| `qualname` | 无 | 中心符号。不给时返回「高连接度符号」的概览图 |
| `depth` | `2` | 1–3 跳 |
| `max_nodes` | `80` | 节点上限，最大 200 |
| `kinds` | `call,inherits,decorator,references` | 逗号分隔；`imports` 默认不展开 |

```json
{
  "mode": "focus",
  "center": { "qualname": "backend.api.chat.stream_chat", "path": "backend/api/chat.py", "lineno": 42 },
  "depth": 2,
  "kinds": ["call", "inherits", "decorator", "references"],
  "nodes": [
    {
      "id": 1832, "qualname": "backend.api.chat.stream_chat", "name": "stream_chat",
      "kind": "function", "path": "backend/api/chat.py", "lineno": 42, "end_lineno": 88,
      "is_async": false, "is_private": false,
      "in_degree": 3, "out_degree": 12, "concept_ids": ["sse"], "depth": 0
    }
  ],
  "edges": [
    { "src": 1832, "dst": 1900, "kind": "call", "lineno": 51, "confidence": 0.6, "uncertain": true }
  ],
  "truncated": false
}
```

| 字段 | 说明 |
|---|---|
| `mode` | `focus`（有中心）或 `overview`（无 `qualname`） |
| `nodes[].depth` | 距中心的跳数；概览图为 `null` |
| `nodes[].concept_ids` | 该符号命中的概念——源文档 §2.2 的「登录接口 → 身份验证/数据库/Token」靠它 |
| `edges[].uncertain` | `confidence < 1`：动态调用等静态分析定不了的关系 |
| `truncated` | **有节点因上限没返回**。前端必须显示，不能把截断的图当完整图 |

> 只有 `dst_symbol_id` 非空的关系会进图：画不出位置的边不画，不留悬空节点。
> `qualname` 不存在 → 404 `symbol_not_found`；`depth` / `kinds` 越界 → 400。

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

> ✅ M6 已实装。数据来自增量索引写下的 `change_record` 与 `staleness_report`；
> 没有任何变更记录时返回**同形状的空壳**，前端不需要为此写分支。
> `since` 取这次索引的基准 commit（`index_run.base_commit`）。
> `stale_design_decisions` 只在**增量**索引时产生——全量重建没有「上一次」可比。

---

### 7.2 `GET /projects/{id}/timeline` — 索引与变更时间轴

**查询参数**：`limit`（默认 30，最大 100）。

```json
{
  "head": "c1d2e3f...",
  "total": 2,
  "items": [
    {
      "id": "run-12",
      "kind": "index",
      "mode": "incremental",
      "ok": true,
      "at": "2026-10-24T09:12:03Z",
      "base_commit": "9b5ad71b...",
      "head_commit": "c1d2e3f...",
      "summary": "新增队列与背压，拆分 prepare/stream 两段。",
      "files": { "added": 76, "modified": 68, "deleted": 80, "total": 224 },
      "symbols_changed": 1036,
      "symbols_added": 210,
      "symbols_removed": 180,
      "files_total": 688,
      "source": "git",
      "stale_design_decisions": [
        { "doc_id": "0012", "title": "使用文件锁保护缓存刷新" }
      ]
    },
    {
      "id": "change-3",
      "kind": "change",
      "mode": null,
      "ok": true,
      "at": "2026-10-23T18:02:00Z",
      "base_commit": null,
      "head_commit": "aa11bb22",
      "summary": "外部 agent 记账",
      "files": { "added": 1, "modified": 0, "deleted": 0, "total": 1 },
      "symbols_changed": 1,
      "symbols_added": null,
      "symbols_removed": null,
      "files_total": null,
      "source": "external_agent",
      "stale_design_decisions": []
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `kind` | `index`（`index_run`）或 `change`（没有对应索引 run 的 `change_record`，例如 MCP 侧记账） |
| `mode` | `full` / `incremental`；`change` 为 `null` |
| `files.added/modified/deleted` | 全量索引不知道逐状态数量时为 `null`，不要当 0 显示 |
| `files.total` | 增量 = 逐状态之和；全量 = 本次扫描的文件数 |
| `symbols_changed` | 来自 `change_record`；缺失时退到 `index_run.stats_json`，仍没有则为 `null` |
| `at` | ISO-8601 UTC；无法确定时为 `null` |

> 只读库、不重算：读侧若重新推导，必然与写侧漂移。
> 「这次改了哪些文件」的明细仍走 §7.1 `/changes`（可用该条的 `head_commit` 作为 `since`）。

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
  "incomplete": false,
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
| `incomplete` | `true` = 走满轮次/工具上限仍未收尾。**与 `abstained` 是两回事**：一个是「没找到」，一个是「没做完」，界面提示不能混用 |
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
  "reason": "",
  "incomplete": false
}
```

> `incomplete` 与 `abstained` 同 §8.1：前者是「没做完」，后者是「没找到」，不能合并提示。

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

## 8.4 知识扩展（请求 0001 / 0005）

**教材与项目代码是两类独立来源**：教材命中可以支撑「SQL 是什么」这类纯知识问题，
但**不能**当作「这个项目用了 SQL」的证据。响应里两者分开放。

请求可以多带一个阅读目标（用户正在看某一节教材或某一段代码）：

```json
{
  "project_id": 1,
  "question": "这里是什么意思？",
  "conversation_id": "conv-1",
  "reading_context": { "kind": "knowledge", "topic_id": "async", "section_id": "mechanism", "version": "…" }
}
```

| `reading_context.kind` | 字段 | 行为 |
|---|---|---|
| `knowledge` | `topic_id` / `section_id?` / `version` | 服务端按版本重读该章节；版本过期 → `reading_status="stale"` |
| `code` | `project_id` / `path` / `lineno` / `end_lineno?` | 服务端校验后自行发起一次 `read_file`，把这一屏代码变成可引用证据 |

`/query` 响应与 `/query/stream` 的 `answer` 事件额外带这些字段（都可缺省）：

| 字段 | 含义 |
|---|---|
| `knowledge_sources` | 本回合用到的教材章节（含 `target` 与来源清单），**不是** `citations` |
| `learning_entries` / `learning_targets` | 可继续学习的入口（最多 3 个） |
| `reading_status` | `none` / `ok` / `missing` / `invalid` / `stale` / `not_found` / `outside_budget` |
| `knowledge_error` | 阅读目标不可用时的可读原因（其余情况为 `null`） |
| `text`（仅 SSE `answer`） | 最终正文（教材链接已注入）。增量仍走 `delta`；这里给一次完整串，方便收尾对齐 |

> `answer` 事件里出现 `text` 不改变事件顺序与次数：仍然恰好一次。

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
| 2026-10-24 | M3：`/query` 与 `/query/stream` 实装；`incomplete` 字段加入 §8.1 响应与 §8.3 `answer` 事件（区分「没做完」与 `abstained`「没找到」）。前端 `types.ts` 已同步 |
| 2026-10-24 | 请求 0001/0003/0005 落地：§8.4 知识扩展——`reading_context` 入参、`knowledge_sources` / `learning_*` / `reading_status` / `knowledge_error` 出参、`answer` 事件带最终 `text`；新增 `/knowledge/*` 三个端点。教材来源与项目 `citations` **永不混用** |
| 2026-10-24 | M8：新增 §4.5 `/projects/{id}/graph`（BFS 邻域、概念标签、`truncated`）与 §7.2 `/projects/{id}/timeline`。`index_run.started_at` 改存墙钟 ISO 时间（此前误存 `time.monotonic()`） |
| 2026-10-24 | 左栏按需拉符号：`/projects/{id}/symbols` 的 `path` / `q` 过滤转义 LIKE 通配符（`_` 是普通字符），`path` 同时支持精确路径 OR 目录前缀 |
| 2026-10-26 | 请求 0018 落地：新增 §16 编排执行——`meta.execution_enabled`、answer 可选 `execution` 元数据、`/projects/{id}/executions/*` 五个端点、`execution_task` 表（schema 3→4）、`CI_EXECUTOR*` 配置。执行经双重审批与 worktree 隔离（ADR 0035） |
| 2026-10-26 | 执行请求增补（主线编号 0018，独立分支原编号 0015）：第二执行器 `zcode`（node + zcode.cjs 无头模式）；`CI_EXECUTOR_COMMAND` 改空缺省按执行器取值，新增 `CI_EXECUTOR_EXTRA_ARGS`。两驱动器真机验收通过 |

## 11. 内置知识与阅读上下文

全局教材与项目库分开，浏览不要求已导入项目，也不需要模型密钥。

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/knowledge/tree` | `{groups:[{title,topics:[{id,title,summary,version,href}]}],version}` |
| GET | `/knowledge/topics/{topic_id}` | 文章及稳定章节、版本、来源、前置/关联目标与已解析正文目标 |
| GET | `/knowledge/search?q=&limit=` | `{items:KnowledgeHit[],total,version,knowledge_sources}`；limit 1–50，默认 8。**limit 是章节数**——同一篇文章的多个章节都会命中，界面按文章合并展示 |
| GET | `/projects/{id}/knowledge/topics/{topic_id}/instances` | 当前项目关联概念实例、head_commit、index_epoch、status；最多 50 项，非完整召回证明 |
| GET | `/projects/{id}/code?path=&start_line=&end_line=` | 索引对应源码窗口 `{path,start_line,end_line,content,head_commit}`，最多 200 行 |

`LearningTarget` 为 `{topic_id,section_id:null|string,section_title:null|string,title,version,href}`。
`section_title` 是章节的可读标题（如「跟着例子理解」）——`section_id` 是内部锚点，
直接显示给用户读不懂。`section_id` 为空时 `section_title` 也为空。
站内地址固定 `/learn/{topic_id}#{section_id}`（章节可省略）；不可解析时保持普通文字。
`KnowledgeHit` 为 `{target,snippet,summary,score,sources}`。搜索的 `snippet` 是**章节原文**；
实际注入的 `knowledge_sources.snippet` 为纳入上下文的文字，图文章节将图片引用替换为
受维护资源的图意（请求 0011）。精确选区仍保持原文片段。`summary` 是给界面卡片显示的
**纯文本摘要**（无 Markdown 标记，长度截断）。source 包含作者、原始 URL、来源版本、
许可/许可 URL、获取时间、快照 SHA256 和修改说明。知识引用不能转换成项目 Citation。

文章包含 `id/title/group/summary/body/sections[{id,title,content}]/version/dialect/concept_ids`，
以及 `sources/prerequisite_targets/related_targets/learning_targets`。
Markdown `{#section_id}` 是内部锚点标记，前端按 sections 渲染，不显示该标记。
未知主题返回 404；未知/旧章节的历史链接打开当前文章并提示更新。

`POST /query` 与 `/query/stream` 增加可选 `reading_context`：

```json
{"kind":"knowledge","topic_id":"python-functions","section_id":"example","version":"文章SHA256"}
```

或代码目标：

```json
{"kind":"code","project_id":1,"path":"store.py","lineno":3,"end_lineno":6}
```

代码目标必须绑定本次项目。服务端重读目标，忽略客户端 snippet/body 等说明。
知识旧版本/删除章节/预算不足用 `reading_status` 和 `knowledge_error` 明确降级，
其中 `none/ok/missing/invalid/not_found/stale/outside_budget` 表示相应状态。

普通问答响应及 SSE 最终 `answer` 增加以下字段，其他字段保持原约定：

- `knowledge_sources: KnowledgeHit[]`：实际纳入本回合上下文的教材章节。
- `learning_targets: LearningTarget[]`：正文可点击的已解析目标，数量不受推荐上限限制。
- `learning_entries: LearningTarget[]`：末尾推荐，至多三项。
- `reading_status: string`、`knowledge_error: null|string`：阅读目标处理状态，软错误不丢弃教材。
- SSE 最终 `text`：校验后的完整正文，前端替换增量正文，恢复站内链接可点击状态。

"SQL 是什么"有教材时不因无代码位置弃答；"这个项目哪里用了 SQL"仍须真实项目证据。
quick/project 不访问 Provider；deep 无配置/失败时 200 返回已有教材与证据，
`error` 写明降级原因、`llm_used=false`。概念详情的 `learning_targets` 指向相关教材。

## 12. 工作台会话与精确选区（请求 0007）

兼容原问答和 SSE 事件词汇。会话记录以服务端 SQLite 为准；浏览器工作区存储不冒充模型记忆。

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/conversations?project_id=&q=&archived=false&cursor=0&limit=30` | 标题/可见消息关键词匹配；project_id 缺省查全部项目；按置顶、更新时间排序；`{items,next_cursor}`，limit 1–100 |
| POST | `/projects/{id}/conversations` | 201 创建空会话，无模型调用；标题初始“新对话” |
| GET | `/projects/{id}/conversations/{cid}` | 会话详情与最新任务状态 |
| PATCH | `/projects/{id}/conversations/{cid}` | 可选 title/pinned/archived/mark_read；title 非空且最多 120 字符 |
| GET | `/projects/{id}/conversations/{cid}/turns?cursor=0&limit=50` | 回合分页，页内时间正序；cursor 为服务端给出的不透明整数，不能自行计算；新回合不改变已有游标边界 |
| POST | `/projects/{id}/tasks/{task_id}/cancel` | 当前项目运行任务取消；已结束任务幂等返回 cancelled=false |

会话项：`id,project_id,project_name,title,pinned,archived,unread,status,task_id,created_at,updated_at,last_read_at`；
搜索结果补充 `snippet,match_request_id`。页签和草稿不放入此接口。

回合项：`request_id,task_id,question,reading_context,answer,status,legacy,created_at,updated_at`。
`answer` 保存实际最终投影，包含 text/facts/inferences/citations/knowledge_sources/learning_targets/
learning_entries/reading_status/knowledge_error/tools/evidence/error 等；未生成的字段可缺省。
`status` 为 running/completed/abstained/failed/interrupted；legacy=true 表示账本回填，缺少的来源不补造。

问答请求增加可选 `request_id`（1–128 字符），缺省时服务端分配。
同项目、同会话、同请求 ID 只能对应同一问题和阅读目标；已完成请求重放，不再次调用模型。
问题或目标不同返回 400；同会话有运行回合返回 409 conversation_busy。
非流式结果增加 conversation_id/request_id/source_head_commit；SSE meta 增加 request_id，
最终 answer 可增加 source_head_commit/tools_used/evidence。原字段保留。
增量与最终投影持久化后再发出；停止、断线、重启中断保留已保存文字，不自动重试。
失败和中断回合不进入最近六轮模型问答历史；展示历史分页保留。

知识目标可增加 `selection:{ranges:[{section_id,start_offset,end_offset}]}`；范围必须按文章章节顺序连续。
offset 为章节 content 原文中零起点、右开的 UTF-16 代码单元偏移，不是渲染后字符串偏移。
代码目标可增加 `head_commit,content_sha256,selection:{start_column,end_column}`；原 lineno/end_lineno
是选区的首尾行，列号为一基 UTF-16，结束列右开。服务端重读版本并拒绝切断字符的范围。
两类目标均可附带 title/section_title/preview 供界面展示；这些说明不能成为事实来源。
显式选区过期、损坏或预算不足时 error.code=reading_invalid、附 reading_status，且不调用 Provider。

源码窗口仍最多 200 行，返回补充 `total_lines,head_commit,content_sha256`。
项目详情补充 `source_available`（源码目录是否仍存在）；不因此禁止历史或教材阅读。

客户端界面错误新增 conversation_busy/reading_invalid/aborted/not_found；错误仍使用 §0.3 形状。
旧 `/learn/{id}#章节` 可继续访问；工作台位置附带 project/conversation/view/material 查询参数。
布局偏好使用 `ci.layout.v1`；草稿/页签/来路使用 IndexedDB `codeinsight-workbench`，存储失败明确提示。

## 11. 本机文件夹选择（请求 0008）

`POST /local/select-folder` 无请求体。在后端所在电脑打开系统文件夹选择框，
选中后返回 `{root_path: string}`，用户取消返回 `{root_path: null}`（200）。
不上传文件、不创建项目；前端随后使用现有 `POST /projects` 明确提交导入。

仅允许 loopback 客户端及本机 Origin；远程来源返回 403 `bad_request`。
选择框已打开返回 409 `bad_request`；五分钟未完成返回 504 `timeout`；
桌面不可用或系统调用失败返回 503 `internal_error`，均遵循 §0.3 错误形状。
Windows 使用系统 PowerShell/Windows Forms，其他桌面使用 Python tkinter；不增加依赖。

## 12. 教材图文资源（请求 0011）

`GET /knowledge/topics/{id}` 增加 `assets` 数组，兼容缺省为空。元素包含
`id,topic_id,section_id,title,description,width,height,author,license,source_ids,sha256,href,media_type`。
href 为 `/knowledge/assets/{id}/{sha256}`，浏览器通过既有 `/api` 前缀访问。
不公开资源的服务器路径。正文用 `![图注](/knowledge/assets/{id})` 引用，只能解析为当前文章清单中的资源。

`GET /knowledge/assets/{id}/{sha256}` 成功返回图片原始字节及正确 Content-Type，
使用内容哈希 ETag 与 immutable 缓存。未知、旧哈希、缺失或损坏资源返回 404 `not_found`；
章节文字仍可读取。资源本身的错误不把文章判为空。

图示及图意参与所属文章版本，正文与图示必须匹配。教材选区仍以 UTF-16 原文为准；
可选择图片 Markdown 中的图注，图内 SVG 标签不作为正文选区。模型依据正文及受维护图意，
不假定具有图片识别能力，不将图示视为项目代码证据。

## 13. 项目探索（请求 0012，ADR 0029）

### 项目导览

`GET /projects/{id}/overview` 保留原字段，增加：

- `project_id,head_commit,index_epoch`：当前索引身份；无 Git 项目也通过 epoch 失效。
- `project_intro`：`null` 或 `{text,source,kind:"indexed_document_excerpt"}`。摘录来自索引文档块，
  或与索引哈希一致的文档原文；Git 项目按索引提交读取。`source` 为下述代码目标。
- `exploration_entries`：最多四个已校验动作。依据程序入口、成功索引变更、可靠概念证据、
  设计说明生成；证据不足的类别省略，没有自动模型任务。

### 最终答案与内部工具

非流式结果和 SSE 最终 `answer` 新增可选 `exploration`，同时保存进回合 `answer`：

```json
{
  "project_id": 1,
  "head_commit": "已索引提交或 null",
  "index_epoch": 1,
  "takeaways": ["实际已在本回合正文展示的要点"],
  "flow": null,
  "actions": [{
    "id": "规范化内容的稳定标识",
    "kind": "follow_up",
    "label": "如果不提交会怎样",
    "reason": "比较写入与持久化的边界",
    "question": "如果不提交事务会怎样？",
    "target": {"kind":"code","project_id":1,"path":"store.py","lineno":3,"end_lineno":3,
               "qualname":"store.save","head_commit":"已索引提交","content_sha256":"源码哈希"}
  }]
}
```

`actions` 最多三项，`kind` 仅 `follow_up/code/knowledge/graph/timeline`。
代码目标沿用阅读上下文，附可选 `qualname`；知识目标为 `kind:"knowledge"` 加 `LearningTarget`。
追问必须有非空 question，可带已校验目标；code/graph 要求真实代码目标，graph 还需符号；
knowledge 要求真实文章及版本；timeline 无目标。其余动作 question 为空。
动作不能包含脚本或执行命令；前端只映射到对应阅读与提问操作。

`flow` 为 `null` 或 `{title,nodes,edges}`：

- nodes 最多八项，`{id,label,role,target}`，target 必须对应同项目、同版本的代码位置。
- edges 为 `{source,target,kind,uncertain}`；仅核对已有索引 call/imports/inherits 边或真实 contains
  包含关系，候选最多十六条。置信不足标 uncertain，不绘制无法核对的连接和孤立节点。
- 这是静态关系，不代表运行时执行顺序；行号合法也不证明角色说明和设计解释正确。

内部只读工具 `propose_exploration` 接收 takeaways/actions/flow，不将 JSON 放入正文。
服务端逐项校验，最终答案发布前再次核对索引版本；非法附加项移除，保留可用正文。
takeaways 仅保留实际显示文字，最多十二项；无建议时可从实际教材推荐派生知识动作。
只有最终 answer 完成后动作可用；存在新动作时前端不重复显示旧 learning_entries。
旧客户端可忽略 exploration；旧答案缺该字段时沿用原展示。

正文引用仍保留真实 `[path:line]` 和独立 citations；前端只把普通正文中已解析引用显示为
`[1]` 等按钮。代码块、行内代码、既有链接不自动改写；来源区和复制内容保留原位置。

### 直接追问与恢复

`POST /query` 和 `/query/stream` 可增加 `action_origin`：

```json
{"kind":"answer","request_id":"来源回答请求ID","action_id":"来源动作ID","index_epoch":1}
```

或 `{kind:"overview",action_id,index_epoch}`。answer 动作只允许来自本项目、本会话保存的回答；
overview 从当前索引重建。服务端重读规范问题和目标，客户端 question/说明不能替换来源内容。
无动作或跨会话返回 400 bad_request；旧索引返回 409 reading_invalid，要求刷新入口。
同 request_id 已完成动作仍按已有幂等结果重放，不重新调用模型，即使之后索引更新。
动作来源另存 `exploration.origin`。同会话互斥、其他会话独立生成的规则不变。

前端直接追问绑定该动作的阅读快照，只影响该请求；成功、失败、中断、刷新恢复均不能覆盖
已有草稿及其关联目标。同会话生成中禁用追问，不排队。

新增 `GET /projects/{id}/conversations/{cid}/turns/{request_id}`，返回完整单回合（同分页元素），
不存在或项目/会话不匹配返回 404。局部知识材料通过此接口恢复来源答案；文章正文仍从知识
接口读取，校验版本和与来源回合的关联。材料身份绑定 project/cid/request_id/文章章节版本；
完整教材继续按文章版本复用。旧 `/learn/{id}#章节` 仍直接打开全文。

### 探索脉络与迁移

会话详情增加 `exploration_state`：`{current_question?,target?,head_commit?,index_epoch?,stale,items?}`。
items 最多十二条 `{text,request_id,target}`，仅表示已展示内容，不表示用户已掌握。
`PATCH /projects/{id}/conversations/{cid}` 可传 `clear_exploration:true`，只清脉络，不清聊天。

SQLite schema 3→4 原地增加 `conversation.exploration_json TEXT NOT NULL DEFAULT '{}'`，
保留索引和全部回合。仅完整成功回合更新脉络；失败、中断和 incomplete 不加入。
模型仍读取最近六个有效问答对；脉络最多 4096 UTF-8 字节并计入原上下文总预算。
裁剪优先保留当前问题与目标。索引更新后旧脉络标 stale，旧要点不作为新版依据，继续提问须重新取证。

## 14. 正文保留与续问取证（请求 0013，ADR 0030）

非流式结果、SSE 最终 answer 及持久化 answer_json 增加可选字段：

- `raw_text`：最终生成原文。只供回看，不能成为可点击引用、检索证据或直接模型记忆。
  中断前的增量原文也随 delta 持久化；成功时以最终原文替换。
- `response_kind`：answer/rephrase/clarification，分别为正常回答、接续解释及无前文时的澄清。
- `evidence_review`：`{status,message,checks,unverified_citations,source_version,followup_from?}`。
  source_version 沿用 project_id/head_commit/index_epoch，followup_from 为同会话来源请求 ID。

| status | 含义 |
|---|---|
| verified | 正文主张有已校验代码引用，仍不证明角色、设计解释的语义正确性 |
| partial | 有已校验引用，同时存在未核实说明或引用；不能将整段自动升级为事实 |
| knowledge | 基于本轮教材解释，不授予项目事实资格 |
| unverified | 没有取得有效引用；可能尚未检索或未将已读取代码对应到正文，不能称为查无实现 |
| no_match | 本轮真实定位操作均未取得可引用位置，不证明整个项目不存在相关机制 |
| unavailable | 检索或源码读取未完成，区别于实际无命中 |

checks 随本轮已有工具预算产生，元素 `{tool,status,target}`；status 为 matched/no_match/unavailable。
只记录真实定位、检索与源码读取，不把结构建议当作取证。unverified_citations 是未通过位置的
纯文字列表；正文将对应 `[path:line]` 改为不可点击的“未核实位置”标记，保留解释。
同一句混合有效/无效引用时整体按未核实说明处理，合法位置仍可单独查看，不给整句事实资格。

`abstained/reason` 等旧字段保持兼容；前端不能因为 abstained 为真隐藏正文，或要求用户先点开
才能阅读解释。核查细节和生成原文默认折叠。旧记录没有 raw_text 时不补造原文。

短续问从同项目、同会话上一完整回合取来路，最多重新读取两份同版本代码来源；
教材经现有服务按文章版本重新读取。历史来源不直接加入 grounding，旧版本不能静默重绑定。
明确的阅读目标优先；内部取证不改客户端草稿或关联，也不增加额外模型轮次与预算。
无前文且无明确阅读目标时简短澄清。首版保守识别明确的“听不懂/换种说法/举个例子”等请求，
不声称覆盖所有自然语言指代。

未核实历史注入模型时标明不可直接当作项目事实；未核实回合不写入可靠探索脉络。
部分有据的回答也仅将实际显示且能对应到已校验事实的要点写入。原有索引、历史与 schema 4 保留，
本次不新增数据库列、不重建用户索引、不追溯恢复过去已覆盖且未保存的生成原文。

## 15. 左栏项目移除（请求 0014，ADR 0031）

`DELETE /projects/{id}` 成功返回 200：

```json
{"project_id":1,"removed":true,"source_deleted":false}
```

只移除 CodeInsight 中该项目的索引、会话、回合、任务账本及其级联数据，
不删除磁盘源码、不清理其他项目和全局教材。前端显式确认后调用；未知项目返回 404。
同一事务内若发现该项目有未结束索引、运行问答或 Agent 任务，返回 409 index_running，
保留全部数据，提示等待或停止任务后再操作。删除不负责自动停止或重跑任务。

schema 4→5 原地新增 project_id_counter，保留全部现有数据；项目 ID 由持久化高水位分配，
API 与 CLI 一致，移除后即使同名导入也不复用旧 ID，避免旧 URL 和其他浏览器缓存串台。
浏览器只清理相应项目的 workspace/draft/pending 记录和活动会话选择；保留其他项目及布局。
当前项目移除后选择剩余项目；无项目时清空项目上下文并提供导入入口。缓存清理失败明确提示，
不把服务端移除失败表现为成功，也不因为移除当前项目清掉其他项目草稿。

## 16. 编排执行（请求 0018，ADR 0035）

对话内识别为开发任务（`dev_task`）时，CodeInsight 编排外部执行 agent
（Claude Code 先行）完成：**计划 → 用户批准 → 隔离 worktree 执行 →
用户验收 → 合入 + 增量索引 + 变更学习卡**。两道审批之间 CodeInsight
不碰用户分支（ADR 0035）。

### 16.1 可用性与降级

`meta` 事件新增 `execution_enabled: boolean`（执行器已配置、命令可执行、
且项目根是 git 仓库时为 true）。不可用时识别器不工作，一律按普通问答，
answer 不带 `execution` 字段——不报错不白屏。

### 16.2 识别与计划

- `/query` 与 `/query/stream` 前置一次轻量分类调用（判 `answer | dev_task`）；
  判为 `dev_task` 且可用时进入编排，最终 `answer` 携带**可选 `execution` 元数据**
  （照 §13 exploration 先例，旧客户端忽略）：

```json
"execution": {
  "task_id": "exec-1a2b",
  "status": "planned",
  "plan": { "intent": "…", "files": ["backend/a.py"], "approach": "…", "risks": ["…"] },
  "progress": [],
  "diff_summary": null,
  "change_card": null
}
```

- `status`：`planned → executing → review → merged`；拒绝/放弃/失败为终态
  `rejected / aborted / failed`。
- 识别误判：前端提供"转为普通问答"（原问题重发，不带执行语义）。

### 16.3 端点

| 方法 | 路径 | 语义 |
|---|---|---|
| `GET` | `/projects/{id}/executions/{task_id}` | 详情：计划、进度、diff 摘要、学习卡 |
| `POST` | `/projects/{id}/executions/{task_id}/approve` | 批准计划 → 进入 executing |
| `POST` | `/projects/{id}/executions/{task_id}/reject` | 拒绝计划（终态，删隔离 worktree） |
| `POST` | `/projects/{id}/executions/{task_id}/abort` | 执行中中止（终态，删 worktree） |
| `POST` | `/projects/{id}/executions/{task_id}/merge` | 验收合入：merge 回原分支 → 增量索引 → 学习卡 |

- 非法迁移（如 planned 直接 merge）返回 409 `bad_request`；
  task 不存在返回 404 `project_not_found` 语义的 `bad_request`（detail 注明）。
- `diff_summary`：`{files_changed, insertions, deletions, files: [{path, status, add, del}]}`。
- `change_card`（仅 merged 后有值）：
  `{facts: [{text, citation}], impacted: {modules[], symbols[]}, concept_ids: []}`——
  全部来自增量索引写入的 `change_record`，不重复分析（ADR 0007 事实口径）。

### 16.4 配置

`CI_EXECUTOR`（`claude-code` 默认；`zcode` 第二执行器；`off` 关闭）·
`CI_EXECUTOR_COMMAND`（空 = 按执行器取缺省：claude-code→`claude`，zcode→`node`）·
`CI_EXECUTOR_EXTRA_ARGS`（逗号分隔附加 argv；zcode 桌面版无 PATH shim 时填
其 `resources/glm/zcode.cjs` 路径）· `CI_EXECUTOR_TIMEOUT_S`（默认 1800）。

### 16.5 主线集成迁移（请求 0017）

集成 schema 版本为 6：保留 3→4 的探索脉络列及 4→5 的项目身份高水位，
5→6 原地补建 execution_task。独立执行分支曾以版本 4 保存数据库但缺少探索列，
升级时按实际列结构补齐，保留执行记录、会话和索引，不要求重新索引。
项目移除的忙碌保护同时包含 planned、executing、review 执行任务，返回原有 409
index_running；完成或放弃后才能移除，避免删除任务记录后遗留隔离 worktree。

## 17. 问答持续分析（请求 0020，ADR 0037）

`CI_MAX_MODEL_TURNS` 默认 0，表示不限制一次问题的总模型轮次；正数仅在调用方主动
配置时启用。正常分析持续到最终答案、用户停止、断线或真实错误，不因达到 10 轮结束。
单次模型输出、上下文及单轮工具调用预算保持原值。

`/query/stream` 等待运行结果时可每 15 秒发送 SSE 注释 `: keep-alive`，不增加事件名，
不纳入工具步骤、消息或账本。浏览器按实际流字节更新连接活动，保留真正无网络活动时
的 watchdog。停止与断线仍取消后台任务，不自动重跑请求。

旧 `incomplete` 字段保持兼容：表示没有生成完整最终答案，可用于显式轮次限额或模型
空输出；前端不再把每一种 incomplete 都解释为“模型轮次达到上限”。


## 理解优先兼容约定（请求 0023 / ADR 0040，2026-10-27）

本节替代历史章节中强制事实/推断分栏、无引用即推断及无引用即弃答的规定。
接口和 SSE 事件形状不变，无 schema 迁移或新增端点：

- `text` 为完整主正文；`raw_text` 仍保存原始生成文本。
- `citations` 仅表示对应本回合查阅范围的可定位位置，不保证解释的语义正确性。
- `facts` 为对应有效位置的原文片段；`inferences` 保留旧形状但不再自动容纳无引用文字。
- 新普通回答不因缺少引用设置 `abstained`。失败、中断与未完成仍由错误、任务状态和 `incomplete` 表达。
- `evidence_review` 保留 checks、无法定位的位置及 source_version。旧状态仅供兼容，不决定整篇展示、历史资格或探索脉络；`verified` 仅指引用能定位，`partial` 仅指部分引用无法定位。
- `evidence` 同时保留检索命中与成功 read_file 的位置。读取项无检索分数；正文引用与本轮查阅分别展示，不能把检索命中列表视为全部结论的依据。
- 未匹配的正文引用移入详情，解释保留；代码示例和已有链接不按正文引用处理。
- 完整历史最近六对继续受预算约束；探索脉络表示讨论来路，不表示用户掌握或项目事实。旧正文不批量改写。

旧版 `verified/partial/abstained` 与新版统计不可直接比较。来源不足的解释不再呈现整篇核查警告，真实操作失败和版本问题继续提供可操作提示。


## 源码快照与运行版本（请求 0024 / ADR 0041，2026-10-27）

- `GET /`、`GET /health` 增加可选 `runtime_revision: string`（启动时加载的后端代码指纹）、`restart_required: boolean`。指纹不含密钥、配置值或用户源码；旧客户端可忽略。新版启动器不静默复用缺少指纹或版本不匹配的已有服务。
- `GET /projects/{id}/code` 保持最多200行，新增可选 `index_epoch`、`head_commit`、`content_sha256` 查询参数。缺省读取当前索引快照；指定历史版本时必须核对项目/路径/版本归属，缺少快照明确报错，不静默切新版。返回原字段及可选 `index_epoch`、`workspace_changed`（按需检测本地文件实质变化，非实时扫描）。
- 答案 citations 及代码阅读目标可携带可选 `index_epoch`。材料页签、URL、分页与来源点击保留该值，历史快照不因重建索引而被替换；旧记录缺少版本时不能补造身份。选区提问仍检查当前索引身份，旧选区需重新选择。
- 内容哈希保持原始字节身份；换行转换只是恢复原始字节的候选，最后仍须完全命中原哈希。AI、代码 API 与代码选区共用同一读取服务。
- `file_snapshot` 复用现有结构，内部 `commit_sha` 的 `source:<hash>` / `epoch:<n>` 命名空间分别记录项目归属及版本映射，不参与 Git 提交或过期率比较，不迁移 schema。字节快照按哈希去重并保留，不自动清理。
- 工具确定失败按本回合文件版本记忆；连续三轮无新材料后，以 tools=[] / tool_choice=none 调用一次整理回答，未遵守工具关闭的 Provider 不继续执行工具。有新材料的分析保持总轮次不限。模型故障与取消仍走原 error/done 流程，不能把工具失败包装为项目不存在。

## 当前工作区优先（请求0025 / ADR0042，2026-10-28）

本节替代0024中“缺省读取当前索引”和“只能读取已索引文件”的规定；旧索引链接仍可用，无schema迁移。

- `GET /projects/{id}/code` 未指定版本时读取当前工作区，不要求文件入索引或Git提交。增加可选 `source_kind=workspace|index`；显式epoch/commit或仅hash且未指定source_kind的旧请求仍按index解释。workspace历史请求使用source_kind=workspace和content_sha256，必须已登记本项目/路径的读取归属。响应增加source_kind；workspace返回head_commit=null、无index_epoch，content_sha256为真实原始字节哈希。
- Citation和CodeReadingContext增加可选source_kind、content_sha256；索引来源保留index_epoch/head_commit，工作区来源不得由整回合索引状态补造版本。SSE和非流式来源、完整回合存储保持相同身份。旧字段source_head_commit和evidence_review.source_version仍指索引基线，不代表workspace材料的版本。
- `GET /projects/{id}/files`默认保持旧索引裸数组；source_kind=workspace返回实际目录清单，允许未提交及未索引文本。可选字段workspace_scan_truncated表示受扫描限额影响，workspace_unavailable表示回退已索引清单；此时source_kind=index。工作区树不提供尚未读取的内容哈希/行数（空串/0），symbol_count仍指索引中的符号数量。
- 增加只读list_files/search_files工具（可指定path子目录、pattern路径筛选），read_file默认workspace，显式source_kind=index恢复索引版本。工作区搜索不依赖Embedding；索引检索与结构工具仍可辅助定位，须明确其版本。
- 工作区范围仅项目根内，排除缓存/密钥/二进制及符号链接。默认列举最多2000个文件、遍历10000个条目，目录工具展示100项、搜索展示20项，单文件2MB、搜索读取约8MB；截断和不可读范围显式呈现，path可缩小扫描目录。每次read_file及代码API仍最多200行。
- 读取的workspace原始字节即时保存，使用file_snapshot中的workspace:<hash>记录项目/路径归属；索引更新不删除它。每请求同路径首次读取固定；不同文件不承诺同一时刻的原子工作区快照。保存失败不返回假来源，workspace源码API错误复用reading_invalid并给具体原因。
- 工作区选区按已登记内容哈希重读UTF-16行列，不受无关索引更新影响；客户端preview不作证据。明确续讲重读上轮工作区快照并说明来路，新问题默认读取当前文件。索引更新只使本回合旧索引工具失效，不阻止工作区取证；失败记忆按源码类型隔离。
