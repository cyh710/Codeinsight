# 三线 · 开工包

> **每个 agent 只需要打开自己那一份**，照着做。
> 详细需求在 [`../functional-spec.md`](../functional-spec.md)，
> 规矩在 [`../../AGENTS.md`](../../AGENTS.md)。

| 线 | 开工包 | 工作目录 | 分支 |
|---|---|---|---|
| A 线（索引+检索+Agent+MCP+集成） | [A-line.md](A-line.md) | `<仓库根>` | `main` |
| B 线（知识探索） | [B-line.md](B-line.md) | `<仓库根>-wt-knowledge` | `feat/knowledge` |
| C 线（前端+API） | [C-line.md](C-line.md) | `<仓库根>-wt-frontend` | `feat/frontend` |

---

## 三线总览

```
                    ┌─────────────────────────────────────────┐
                    │  契约（冻结，改动走 docs/requests/）      │
                    │  models.py · schema.sql · config.py     │
                    │  api-contract.md · types.ts             │
                    │  fixtures/sample-index.json             │
                    └───────────────┬─────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
   ┌────▼─────┐              ┌──────▼──────┐            ┌───────▼──────┐
   │  A 线     │              │   B 线      │            │   C 线       │
   │ 索引      │──符号/边──► │  知识层     │◄──概念─── │  前端 + API  │
   │ 检索      │              │  本体       │   实例    │              │
   │ Agent     │              │  检测器     │            │              │
   │ MCP       │              │  三级解释   │            │              │
   │ 评测/集成 │              └─────────────┘            └──────────────┘
   └──────────┘
```

**第 1 周三线都满负荷**，没有人在等：

| 线 | 零依赖的第一件事 |
|---|---|
| A | 写 API 契约 + TS 类型 → schema 补表 → M1 索引 |
| B | **写 20 个概念本体 YAML**（纯内容，格式已定死） |
| C | **复制织忆前端基建** + 三栏骨架 + mock 层 |

---

## 交接流程

| 情形 | 怎么办 |
|---|---|
| 需要改别人目录的东西 | 写 `docs/requests/NNNN-xxx.md`（模板见 [`../requests/README.md`](../requests/README.md)），**不要直接改** |
| 需要别人的数据 | 提需求要 **fixture 或接口**，不要直接读对方的库 |
| 发现设计与源文档冲突 | **以源文档为准**；确实要改，先写 ADR |
| 源文档没覆盖的空白 | 写 ADR 记录决策，再写代码 |
| 三个方向都不确定 | 停下来问用户，不要各自发挥 |

---

## 收工检查（每条线都要过）

```bash
uv run pytest -q        # A/B 线
uv run ruff check .     # A/B 线
cd frontend && npm run test && npm run lint   # C 线
```

- **绿了才提交。**
- 提交信息用中文，格式 `类型: 做了什么`，正文写动机与影响。
- `git commit` 可以直接做；**`git push` 必须等用户明确说。**
