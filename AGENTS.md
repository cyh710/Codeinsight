# AGENTS.md · CodeInsight 作业规程

> 任何在这个仓库里干活的 agent（人或模型）都适用。三条线并行，规矩一样。
>
> 协作细则见 [`docs/workspace.md`](docs/workspace.md)；
> 功能需求见 [`docs/functional-spec.md`](docs/functional-spec.md)。

---

## 1. 项目是什么

**CodeInsight** —— 基于持续项目认知的智能代码理解与知识探索 Agent。

让 Agent 持续维护对一个真实仓库的认知（符号、调用关系、**技术概念**、版本演进、设计说明），
并把这份认知同时用于问答、变更解释与原理讲解。

系统以**理解为主线，开发为辅助，学习按需展开**：实际的代码修改交给外部 agent
（Claude Code / Codex 等）经 **MCP Server** 调用本系统的理解能力。

源文档：《CodeInsight 项目完整概览》（12 页）。
**源文档是需求的最终依据**——本仓所有功能都能回指它的章节号。

---

## 2. 读文档的顺序

1. **本文件**（AGENTS.md）—— 规矩
2. [`docs/functional-spec.md`](docs/functional-spec.md) —— **你要实现的东西**（只看自己那一节）
3. [`docs/decisions/`](docs/decisions/) —— 与你相关的 ADR（每条都写了"为什么"和"什么条件下重评"）
4. [`docs/workspace.md`](docs/workspace.md) —— 三线怎么协作
5. [`docs/interfaces.md`](docs/interfaces.md) —— 接口契约

---

## 3. 硬规矩

### 3.1 不越界

**一个目录只有一个 agent 能写。** 车道表见 [`docs/workspace.md` §3](docs/workspace.md)。

越界了**不要直接改**——写 `docs/requests/NNNN-<简述>.md` 提给 A 线（集成方）。

### 3.2 不改契约

以下文件是**冻结的契约**，任何改动都必须先走 `docs/requests/`：

`src/codeinsight/models.py` · `src/codeinsight/storage/schema.sql` ·
`src/codeinsight/config.py` · `docs/api-contract.md` · `frontend/src/api/types.ts`

### 3.3 不推 main

- **`git commit` 可以直接做。**
- **`git push` 必须等用户明确说。** 尤其 `main`。
- `main` 只有 A 线能合，合之前全量测试必须绿。

### 3.4 不留烂摊子

- 失败**降级**不要抛异常：工具/解析器失败要返回可解释的错误，让上层能自我修正
  （[ADR 0012](docs/decisions/0012-tool-failure-degrades-not-raises.md)）。
- 检索无命中就**说没命中**，不允许编造 `file:line`
  （[ADR 0007](docs/decisions/0007-facts-vs-inferences.md)）。
- 静态分析定不了的动态调用**保留不确定标记**，不丢弃也不假装确定。
- 引用信息放**结构化字段**，不随文本截断丢失
  （[ADR 0006](docs/decisions/0006-citation-outside-content.md)）。

### 3.5 不隐藏不确定性

写代码时如果发现某个设计"其实不太对但先这么做了"，**写进 ADR**，
不要留成代码里的隐含假设。

---

## 4. 三条线

| 线 | 分支 | 目录 | 做什么 |
|---|---|---|---|
| **A** | `main` | `cognitive/{parsing,indexing,retrieval,embedding}/` `agent/` `llm/` `storage/` `eval/` `models.py` `config.py` `cli.py` `docs/` | 索引 · 检索 · Agent Runtime · MCP Server · 评测 · 集成 |
| **B** | `feat/knowledge` | `cognitive/concepts/` `knowledge/concepts/` | 概念本体 · 检测器 · 三级深度解释 |
| **C** | `feat/frontend` | `frontend/` `src/codeinsight/api/` | 前端工作台 · API 实现 |

---

## 5. 代码风格

- **注释与文档用中文**（与织忆项目一致）；代码标识符用英文。
- **注释解释"为什么"，不解释"是什么"。** 是什么看函数名。
- 类型注解齐全；公开函数写 docstring，**写清约定与不变量**（不只是描述）。
- 行宽 100，`ruff format` 统一格式。
- 不写"防御性"的空 `except:`；确需吞异常时写明为什么吞。
- **不引入新依赖**除非：标准库做不到、且已在 `docs/requests/` 里说明理由。

---

## 6. 命令

```bash
uv sync --extra dev                # 安装依赖
uv run pytest -q                   # 全量测试
uv run pytest tests/xxx -q         # 只跑某目录
uv run ruff check .                # lint
uv run ruff format .               # 格式化

uv run ci init-db                  # 建索引库
uv run ci where                    # 看本地路径

cd frontend && npm install && npm run test   # 前端测试
```

---

## 7. 验收

改动要能自证：

| 类型 | 怎么验 |
|---|---|
| 解析器 | 对真实仓库解析，抽查符号数量与行号正确；**语法错误文件不炸整次索引** |
| 切块 | 超大符号正确二次切分，`symbol_id` 仍指向原符号 |
| 检索 | top-k 命中已知 ground truth |
| 概念检测 | 每个实例有 `evidence`；人工核对准确率 ≥ 0.8 |
| Agent | 截断不破坏 `file:line`；事实与推断分栏；无命中时明确弃答 |
| 增量索引 | 改一个文件后，只有相关 chunk 的 `source_sha256` 变化 |
| 前端 | Vitest 过；SSE 解析有测试 |

阶段级验收清单在 [`docs/roadmap.md`](docs/roadmap.md)。

---

## 8. 一句话总结

> 三个 agent 写出来的代码，最终署同一个名。
> 宁可多写一条 ADR 说明为什么这么做，也不要留一段"只有自己看得懂"的代码。
