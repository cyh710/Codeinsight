# AGENTS.md · CodeInsight 作业规程

> 任何在这个仓库里干活的 agent（人或模型）都适用。
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
2. [`docs/functional-spec.md`](docs/functional-spec.md) —— 功能需求（历史文档，写于三线并行期）
3. [`docs/api-contract.md`](docs/api-contract.md) —— **API/SSE 契约（冻结）**，端点变更看它的变更历史
4. [`docs/decisions/`](docs/decisions/) —— 与你相关的 ADR（每条都写了"为什么"和"什么条件下重评"）
5. [`docs/workspace.md`](docs/workspace.md) —— 怎么协作（分支、请求单、对齐）
6. [`docs/roadmap.md`](docs/roadmap.md) —— 里程碑与验收

---

## 3. 硬规矩

### 3.1 有事走请求单

跨范围的改动（动到别人的模块、动契约、动 schema）**先写
`docs/requests/NNNN-<简述>.md`**，写清：要什么、为什么、影响的调用点、
契约增量。用户批准后再动工。历史先例：0004（问答端点）、0012（项目探索）。

### 3.2 不改契约

以下文件是**冻结的契约**，任何改动都必须先走 `docs/requests/`
（`schema.sql` 的版本号原地递增，见 0012/0014 的先例）：

`src/codeinsight/models.py` · `src/codeinsight/storage/schema.sql` ·
`src/codeinsight/config.py` · `docs/api-contract.md` · `frontend/src/api/types.ts`

### 3.3 分支与推送

- 作业在**特性分支**上做（如 `codex/xxx`、`feat/xxx`），一个授权任务一条分支；
  请求单里写明"本地提交、不合并、不推送"就照办。
- **`git commit` 可以直接做。**
- **`git push` 必须等用户明确说。** 合进 `main` 也是。
- 合 `main` 前全量测试必须绿：`pytest` + `ruff` + 前端 `test/lint/build`。

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

### 3.6 不自己拍板

**需求边界、取舍、观感这三类，必须找用户对齐，不能自己定。**

- **要问的**：功能要不要做 / 做到什么程度、两条路都可行时选哪条、
  文案措辞 / 布局 / 配色 / 信息密度、发现原计划做不到或有更好的做法。
- **不用问的**：实现细节、规格里已写死的、有唯一正确答案的技术问题、风格格式。
  这些自己定，写进 ADR 就行。

**提问要给选项和推荐**，不要开放式甩问题回去：

```
要做什么 · 2~3 个选项 · 我的推荐 + 理由 · 各自的代价
```

**问不到用户时**（无人值守）：查规格 → 查默认值 → 按默认值做 →
写 ADR 标注"未与用户确认" → 提交信息里写 `决策：X（未对齐，默认值，理由：…）`。

> 可以自己定默认值，**不可以自己定边界和观感**——
> 边界和观感错了，返工成本远高于问一句。

完整规则见 [`docs/workspace.md` §9](docs/workspace.md)。

---

## 4. 当前的协作模式

> 早期是"三条线三个 worktree 并行"（A 索引/检索/Agent、B 知识探索、C 前端），
> M1–M5 全部完成后收拢为**单仓单工作区**。历史作业包在
> [`docs/lines/`](docs/lines/)（已归档，仅供追溯）。

- **一次一个授权任务**：用户批准一份请求单（或口头指定）→ 一条特性分支 →
  本地提交 → 用户验收后合入 `main`。
- **在飞的活不要碰**：开工前 `git status` 看有没有别人未提交的改动；
  有就只读巡检，别动文件、别杀进程（可能有并行会话）。
- 目录归属按"谁在写谁负责"：当前没有按目录划的车道，但**契约文件**仍是红线（§3.2）。

---

## 5. 代码风格

- **注释与文档用中文**；代码标识符用英文。
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

uv run ci index --repo <路径>      # 对仓库建索引
uv run ci ask --project <名> "问题"  # 命令行问答
uv run ci mcp --project <名>       # MCP Server（stdio）→ 见 docs/mcp.md

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
| Agent | 保留完整解释与可定位来源；缺口具体说明、不编造；旧分栏与弃答要求由 ADR 0040 替代 |
| 增量索引 | 改一个文件后，只有相关 chunk 的 `source_sha256` 变化 |
| 前端 | Vitest 过；SSE 解析有测试 |
| MCP | 外部 agent 真机调通（见 `docs/mcp.md` 与 `tests/test_mcp.py`） |

阶段级验收清单在 [`docs/roadmap.md`](docs/roadmap.md)。

---

## 8. 找用户对齐

**你不在用户现场，所以要主动把决策点摆出来。**

| 时机 | 对齐什么 |
|---|---|
| 开工前 | 本次任务的取舍（写进请求单或当面问） |
| 每完成一个任务 | 下一个任务的取舍 |
| 发现范围变化 | **立刻问**，不要做完再说 |
| 阶段验收 | 产出满不满意、下一步优先级 |

提问格式：**要做什么 · 2~3 个选项 · 我的推荐 + 理由 · 各自代价。**

规则细节见 [`docs/workspace.md` §9](docs/workspace.md)。

---

## 9. 一句话总结

> 所有 agent 写出来的代码，最终署同一个名。
> 宁可多写一条 ADR 说明为什么这么做，也不要留一段"只有自己看得懂"的代码。
