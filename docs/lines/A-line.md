# A 线 · 索引 + 检索 + Agent + MCP + 集成 · 开工包

> **源文档 §2.1 §2.2 §2.3 §2.4 §2.5 §5 §6**
>
> A 线是**主线**：M0/M1/M2/M3/M5/M6/M7/M9 都归它，同时负责三条线的契约与集成。

---

## 0. 开工前

```bash
cd <仓库根>
git branch --show-current     # main
uv sync --extra dev
```

**读**：[`../../AGENTS.md`](../../AGENTS.md) · [`../functional-spec.md`](../functional-spec.md) 的
**「## 1. A 线」** · [`../workspace.md`](../workspace.md)

---

## 1. 你的车道

```
src/codeinsight/cognitive/{parsing,indexing,retrieval,embedding}/
src/codeinsight/{agent,llm,storage,execution,eval}/
src/codeinsight/{models,config,cli}.py
docs/          fixtures/      前端类型 frontend/src/api/types.ts
```

---

## 2. 今天的顺序（关键路径）

| # | 做什么 | 卡住谁 |
|---|---|---|
| 1 | **`docs/api-contract.md`** —— 端点 + 请求/响应体 + SSE 词汇表 | **C 线** |
| 2 | **`frontend/src/api/types.ts`** —— 与契约一一对应 | **C 线** |
| 3 | `schema.sql` 补 `dependency` 表 + `file.role` 列 | 无 |
| 4 | **`fixtures/sample-index.json`** —— 对织忆 `agent-v1` 做一次粗 AST dump | **B/C** |
| 5 | **M1 索引** 全流程 | 无 |

> **1、2 是 C 线解锁的前提**，先做。4 做完 B 线的检测器能跑真实数据。

### 4 的做法

不必等完整索引器。写个一次性脚本：对织忆 `agent-v1` 用标准库 `ast` 粗扫一遍，
按 [`../../fixtures/README.md`](../../fixtures/README.md) 里写死的结构导出 JSON。
数据是真的，够 B/C 开发用。

---

## 3. M1 之后

```
M1 索引 → M2 检索 → M3 Agent → M7 MCP
            └─ 与 B/C 并行 ─┘
```

详细规格见 [`../functional-spec.md`](../functional-spec.md) §1。
关键点：

- **扫描用 `git ls-tree`，不扫工作区**（带 `-c core.quotepath=false`）。
- **解析用标准库 `ast`**，五类边（call / inherits / decorator / imports / references）。
- **动态调用保留 `confidence < 1`**，不丢弃也不假装确定。
- **切块按符号边界**，超大符号二次切分但 `symbol_id` 不变。
- **分词器入库与查询共用一个函数**，中文走 jieba。

---

## 4. 每天的集成职责

| 时机 | 动作 |
|---|---|
| 开工 | 交付契约（1、2、4） |
| 收工 | 把 `feat/knowledge` / `feat/frontend` 合进 `main`，跑全量测试 |
| 契约变更 | 处理 `docs/requests/` 里的请求，统一改并同步三条线 |
| 合完 main | **合回各 feature 分支**，否则它们会落后并覆盖别人的改动 |

```bash
cd <仓库根>
git checkout main && git merge feat/knowledge && git merge feat/frontend
cd <仓库根>-wt-knowledge && git merge main
cd <仓库根>-wt-frontend  && git merge main
```

---

## 5. 验收

见 [`../roadmap.md`](../roadmap.md) 的「每阶段的验收」表。A 线自己的关键几条：

- [ ] M1：真实仓库建索引成功；符号数与 AST 抽查一致；超大符号正确二次切分
- [ ] M2：10 个"在哪里实现"的问题全部给出正确 `file:line`
- [ ] M3：截断不破坏 `file:line`；事实与推断分栏；无命中时明确弃答
- [ ] M5：`ci eval` 一条命令产出对照报告，含 95% CI 与样本量 n
- [ ] M6：改一个函数后只有相关 chunk 的 `source_sha256` 变化（SQL 断言）
- [ ] M7：外部 agent（Claude Code）能真的调通 `search_code` / `explain_concept`
