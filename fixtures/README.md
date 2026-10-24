# fixtures · 开发用样例数据

> 目的是**让 B 线和 C 线不必等后端跑起来就能开工**。

## `sample-index.json`

织忆 `ai-companion-agent@agent-v1` 的**真实索引快照**——由真正的扫描器 + 真正的解析器产出，
不是手写 mock（手写 mock 会骗人，形状对不上是常有的事）。

**重新生成**：

```bash
ci dump-fixture --repo "D:/path/to/some-repo" --ref agent-v1 \
                --name tapestry --out fixtures/sample-index.json
```

`--max-modules N` 控制符号与边覆盖多少个模块（默认 40，分层取样）。
`--max-modules 0` = 全量（约 17 MB，不适合入库）。

### 结构

```json
{
  "project": { "id": 1, "name": "tapestry",
               "root_path": "https://github.com/cyh710/Tapestry.git",
               "head_commit": "e5532a84...", "head_branch": "agent-v1" },
  "files":     [ { "path": "backend/core/chat_orchestrator.py", "language": "python",
                   "role": "source", "content_sha256": "...",
                   "size_bytes": 96213, "line_count": 2229, "in_chunk_index": true } ],
  "modules":   [ { "qualname": "backend.core.chat_orchestrator",
                   "path": "backend/core/chat_orchestrator.py", "docstring": "..." } ],
  "symbols":   [ { "qualname": "backend.core.chat_orchestrator.prepare_chat_stream",
                   "name": "prepare_chat_stream", "kind": "function",
                   "path": "backend/core/chat_orchestrator.py",
                   "lineno": 1180, "end_lineno": 2180,
                   "header": "async def prepare_chat_stream(...) -> ...:",
                   "docstring": "...", "n_lines": 1000,
                   "is_async": true, "is_private": false } ],
  "edges":     [ { "src_qualname": "backend.core.chat_orchestrator",
                   "dst_name": "redis.Redis", "dst_qualname": null,
                   "kind": "call", "path": "backend/core/chat_orchestrator.py",
                   "lineno": 1201, "confidence": 1.0 } ],
  "concepts":  [ ],
  "flows":     [ ]
}
```

### 当前这份快照里有什么

| | 数量 |
|---|---|
| `files` | 688（全量文件树，含 frontend / docs / tests / mobile_sam） |
| `modules` | 389（全量 Python 模块） |
| `symbols` | 790（分层取样覆盖 40 个模块） |
| `edges` | 5109（同上） |

分布（保证每种 kind 都能被 B/C 线看到）：

| `symbols.kind` | | `edges.kind` | |
|---|---|---|---|
| `function` | 484 | `call` | 4020 |
| `method` | 119 | `references` | 685 |
| `constant` | 79 | `imports` | 324 |
| `class` | 61 | `decorator` | 60 |
| `module` | 44 | `inherits` | 20 |
| `property` | 3 | | |

`files.role`：`source` 359 · `test` 185 · `doc` 123 · `vendored` 16 · `config` 5。
`edges` 里有 34 条 `confidence < 1`（动态调用），B 线要能区分得开。

`symbols` / `edges` 是**分层取样**的结果——按顶层目录（`backend` `tests` `scripts`
`mobile_sam` `tools` …）各取一部分，保证每种 `role`、每种符号 kind、每种边 kind 都能看到。
全量是 6543 个符号 + 43k 条边，17 MB，入库不合适；要全量自己跑上面的命令。

### `concepts` 与 `flows` 为什么是空的

- `concepts` 要等 **B 线**的概念检测器落地（`knowledge/concepts/*.yaml` 写完），
  届时重跑一次 `ci dump-fixture` 就会自动带上。
- `flows` 要等 **A 线 M2** 的流程检测（A5）。

在它们到位之前，C 线的概念卡界面可以先按契约 `docs/api-contract.md` §6 的形状做 mock。

### `dst_name` 的匹配规则（**B 线必读**）

边的 `dst_name` 存的是**完整点号路径**，不是最后一个标识符。原因见规格 §1.2 A2：
只存最后一段分不清 `jwt.decode` 和 `os.decode`，只存顶层包名又会把
`backend.config` 和 `backend.services` 混成一个。

所以本体里的检测规则按下面这张表匹配（规格 §2.1 有同一张表）：

| 规则键 | 匹配规则 | 例子 |
|---|---|---|
| `import_names` | 整串相等 **或** 前缀相等 | `jwt` 命中 `jwt`、`jwt.algorithms` |
| `call_names` | 整串相等 **或** 末段相等 | `jwt.decode` 命中 `jwt.decode`、`decode` |
| `attribute_names` | 末段相等 | `redis` 命中 `self.redis`（记成 `redis`） |
| `decorator_names` | 末段相等 | `get` 命中 `app.get` |
| `base_classes` | 整串相等 | `Base` 命中 `Base` |
| `string_markers` | 精确包含 | — |

### 用法

- **C 线**：`frontend/src/api/mock.ts` 按这个形状返回假数据。
- **B 线**：detector 的单元测试直接拿 `symbols` / `edges` 构造 `SymbolView` / `EdgeView`。
- 这份数据是**真实仓库的真实结果**，所以 B/C 看到的形状和线上一致。
- 它由 A 线的 `ci dump-fixture` 导出，**不要手改**。

## 其它 fixture

| 文件 | 用途 | 谁维护 |
|---|---|---|
| `sample-index.json` | 索引快照 | A 线 |
| `sample-queries.json` | 评测题样例 | A 线（M5） |
