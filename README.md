# CodeInsight

> **基于持续项目认知的智能代码理解与知识探索 Agent**

给一个真实仓库建索引，然后用 Agent 回答「这段逻辑在哪、怎么串起来、为什么这么写」。
每条结论都能落回 `file:line`；没有证据就明确说没找到。

![工作台](docs/images/workbench.png)

<sub>左：文件/符号树 · 中：流式问答（工具时间线 + 事实/推断分栏） · 右：证据面板（命中通道 + 概念标签）</sub>

---

## 它和「把代码丢给模型」有什么不同

1. **结论可追溯，而且是**校验**过的。**
   模型写出的每个 `[路径:行号]` 都会拿本回合工具**真正读到过**的位置去对；
   对不上的引用会被删掉，那句话降级成推断。编造的 `file:line` 到不了用户眼前。

2. **事实与推断分开。**
   回答分成 `facts[]`（每条带引用）与 `inferences[]`（显式标注为推断）——
   这是产品主张，不是 UI 风格（[ADR 0007](docs/decisions/0007-facts-vs-inferences.md)）。

3. **认知是持续的，不是一次性的快照。**
   改一个函数再索引：只有它（和受影响的那几个块）的哈希变，其余一行不动；
   能报出「这次改了什么、影响谁、哪条设计说明已经过期」（[ADR 0016](docs/decisions/0016-design-staleness-by-evidence-loss.md)）。

4. **检索是结构化的。**
   BM25 / 稠密 / 符号关系 / 概念实例四路通道，通道开关就是实验的臂——
   没有需要拍脑袋的融合权重（[评测](#评测)）。

5. **不自己做执行。**
   写代码、跑命令、跑测试交给外部 agent；CodeInsight 通过 **MCP** 把理解能力递过去，
   闭环四段（理解 / 操作 / 变更验证 / 认知更新）一段不丢。

## 数字

被测仓库：织忆（Tapestry，作者另一个项目）@ `agent-v1`（`e5532a84`），
688 个文件 / 389 个 Python 模块。所有数字都能用下面「复现」里的命令重跑。

| 指标 | 数值 | 怎么来的 |
|---|---|---|
| 符号 / 边 | 6543 个符号，43135 条边（12832 条解析到仓库内符号） | [SQL 可查](#复现) |
| 块 | 6400 块（超大符号按语句递归切分） | `chunk` 表 |
| 入口 / 流程 / 设计说明 / 概念 | 4 / 9 / 43 / 20（3605 处实例） | 各表 `COUNT(*)` |
| 全量索引 | 约 31 秒（含中文分词；不含 embedding） | `ci index` |
| 增量索引 | 40 个 commit → 1036 个符号变化，20.7 秒 | `ci index --incremental` |
| 测试 | 353（后端）+ 79（前端） | `pytest` · `npm test` |

## 评测

同一批题（从索引自动生成，不手工标），只改检索通道开关：

| 臂 | 命中@8 | MRR | Top-1 |
|---|---|---|---|
| `none`（不检索） | 0% | 0.000 | 0% |
| `bm25` | 81% | 0.691 [0.581, 0.793] | 63% |
| `hybrid`（+ 稠密） | 89% | 0.729 [0.632, 0.819] | 63% |
| `symbol` | 42% | 0.288 [0.193, 0.392] | 19% |
| `concept` | 18% | 0.177 [0.081, 0.274] | 18% |
| **`full`（产品配置）** | **98%** | **0.823 [0.744, 0.895]** | **73%** |

n=62，k=8，seed=7，括号内为 95% bootstrap 区间。完整报告：
[`eval/reports/run-f97b4c0d1f33-s7/report.md`](eval/reports/run-f97b4c0d1f33-s7/report.md)。

**最重要的发现是「每个通道只在自己的题型上强」**：

| 题型 | 最强单通道 | 说明 |
|---|---|---|
| 知道名字找实现 | `symbol` 0.702 | 结构化索引的价值 |
| 只知道描述 | `bm25` 0.980 | 语义通道反而略降（0.940） |
| 用了哪个概念 | `concept` 0.917 | 词面检索只有 0.042 |

> 这些数字的边界写在报告里：题目自动生成、没有人工复核；n 小、区间宽；
> 臂间差值小于区间重叠时**不构成结论**。这里不放没测过的指标。

## 快速开始

需要 Python 3.13+ 与 [uv](https://astral.sh/uv/)；前端需要 Node 20+。

```bash
uv sync --extra dev

# 1) 索引一个仓库（缺 key 也能跑，只是没有语义检索）
uv run ci index --repo /path/to/repo --name demo --concepts knowledge/concepts

# 2) 命令行提问（需要 CI_LLM_API_KEY）
uv run ci ask "对话消息是怎么从 HTTP 入口流到前端的？" --project demo

# 3) 起服务 + 前端工作台
uv run uvicorn codeinsight.api.app:app --port 8020
cd frontend && npm install && VITE_CI_MOCK=0 npm run dev    # http://localhost:5173

# 4) 接到 Claude Code（见 docs/mcp.md）
uv run ci mcp --project demo
```

配置只走环境变量（复制 `.env.example` 为 `.env`）：

| 变量 | 用途 |
|---|---|
| `CI_LLM_API_KEY` / `CI_LLM_BASE_URL` / `CI_LLM_MODEL` | 问答用的 OpenAI 兼容模型 |
| `CI_EMBEDDING_API_KEY` / `..._BASE_URL` / `..._MODEL` / `..._DIM` | 语义检索（缺省硅基流动 bge-m3） |

## 它长什么样

![概念面板](docs/images/concept-panel.png)

<sub>代码 → 概念：证据面板上的概念标签点进去，就是「这个项目里这个概念在哪、怎么用的」。</sub>

## 架构

```
git tree ──▶ 解析(ast) ──▶ 符号/边/块 ──▶ SQLite(FTS5 + 向量)
                              │                   │
                   概念检测(B 线本体)         四路检索 + RRF
                              └────────┬──────────┘
                                       ▼
                       Agent Runtime（≤10 轮 · 有界上下文 · 工具循环）
                          │ 事实校验：引用必须命中本回合读过的位置
                          ├──▶ SSE（/query/stream）──▶ React 工作台
                          └──▶ MCP（stdio）──────────▶ Claude Code / Codex
```

| 层 | 关键决定 |
|---|---|
| 扫描 | 用 `git ls-tree` 读**某个 commit**，不扫工作区；索引绑定版本 |
| 解析 | 标准库 `ast`；能唯一解析才连边，判不了就留空并标 `confidence<1` |
| 切块 | 符号是原子；超大符号按语句边界递归切分，`symbol_id` 不变 |
| 检索 | BM25(FTS5) + 稠密 + 符号关系 + 概念实例，RRF 融合（只看名次） |
| 回答 | 事实 / 推断分离；引用逐条校验；无证据则弃答 |
| 增量 | 只重算变了的文件；删除符号前快照调用者；设计说明按「证据消失」判过期 |

更细的决策见 [`docs/decisions/`](docs/decisions/)，接口约定见 [`docs/interfaces.md`](docs/interfaces.md)。

## 复现

```bash
# 索引规模
sqlite3 .ci/codeinsight.db "SELECT COUNT(*) FROM symbol;"
sqlite3 .ci/codeinsight.db "SELECT COUNT(*) FROM edge WHERE dst_symbol_id IS NOT NULL;"

# 检索对照（会写 eval/reports/<run_id>/）
uv run ci eval --project demo -n 25

# 增量索引（先提交一次改动）
uv run ci index --repo /path/to/repo --name demo --incremental
uv run ci changes --project demo
```

## 已知限制

- **只支持 Python**。`LanguageParser` 留了口，换 tree-sitter 不动上层。
- **增量只重解析变了的文件**：如果某文件本身没变、但它 import 的目标被改坏，
  它指向旧目标的边会随级联删除消失，不会自动重解析（宁可少一条边，不留假边）。
- **评测题自动生成**，没有人工标注与复核；样本量小，只在这个仓库上验证过。
- **用户研究还没做**：协议与记录模板在 [`docs/studies/user-study.md`](docs/studies/user-study.md)，
  结果出来后才会写进这里。**不做假数据**。
- 问答质量依赖所配模型；`facts` 的**位置**经过校验，但「这句话说得对不对」仍需人工核对。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/roadmap.md`](docs/roadmap.md) | 阶段划分 + 每阶段的真实数字 |
| [`docs/api-contract.md`](docs/api-contract.md) | HTTP / SSE 契约（已冻结） |
| [`docs/mcp.md`](docs/mcp.md) | MCP Server 接入与工具清单 |
| [`docs/decisions/`](docs/decisions/) | ADR：每个技术决策的「为什么」与「什么条件下重评」 |
| [`docs/functional-spec.md`](docs/functional-spec.md) | 功能实现需求书（逐条对应源文档章节） |
| [`docs/ported-from-tapestry.md`](docs/ported-from-tapestry.md) | 从作者另一个项目移植了什么、改了什么 |
| [`NOTICE.md`](NOTICE.md) | 第三方归属（代码 / 教材来源 / 数据隐私） |

## License

Apache-2.0，见 [`LICENSE`](LICENSE)；第三方归属与数据隐私说明见 [`NOTICE.md`](NOTICE.md)。
