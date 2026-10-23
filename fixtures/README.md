# fixtures · 开发用样例数据

> 目的是**让 B 线和 C 线不必等后端跑起来就能开工**。

## `sample-index.json`（A 线本周补）

织忆 `ai-companion-agent@agent-v1` 的**真实索引快照**：

```json
{
  "project": { "id": 1, "name": "tapestry", "root_path": "...", "head_commit": "..." },
  "files":     [ { "path": "...", "language": "python", "content_sha256": "...", "role": "source" } ],
  "modules":   [ { "qualname": "backend.services.agent_tasks", "path": "...", "docstring": "..." } ],
  "symbols":   [ { "qualname": "...", "name": "...", "kind": "function",
                   "path": "...", "lineno": 29, "end_lineno": 61,
                   "header": "...", "docstring": "...", "n_lines": 33 } ],
  "edges":     [ { "src_qualname": "...", "dst_name": "...",
                   "dst_qualname": "...", "kind": "call",
                   "path": "...", "lineno": 40, "confidence": 1.0 } ],
  "concepts":  [ { "concept_id": "jwt", "path": "...", "lineno": 3,
                   "qualname": "...", "evidence": "import jwt", "confidence": 1.0 } ],
  "flows":     [ { "name": "...", "steps": [ { "qualname": "...", "path": "...", "lineno": 1 } ] } ]
}
```

- 用法：
  - **C 线**：`frontend/src/api/mock.ts` 按这个形状返回假数据。
  - **B 线**：detector 的单元测试直接拿 `symbols` / `edges` 构造 `SymbolView` / `EdgeView`。
- 这份数据是**真实仓库的真实结果**，所以 B/C 看到的形状和线上一致。
- 它由 A 线的 `ci import` 导出，**不要手改**。

## 其它 fixture

| 文件 | 用途 | 谁维护 |
|---|---|---|
| `sample-index.json` | 索引快照 | A 线 |
| `sample-queries.json` | 评测题样例 | A 线（M5） |
