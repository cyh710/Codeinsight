# CodeInsight

> **基于持续项目认知的智能代码理解与知识探索 Agent**

让 Agent **持续维护**对一个真实仓库的认知——符号、调用关系、**技术概念**、版本演进、设计说明——
并把这份认知同时用于问答、变更解释与原理讲解。

系统以**理解为主线，开发为辅助，学习按需展开**：CodeInsight 负责"读懂并讲清楚"，
实际的代码修改交给外部 agent（Claude Code / Codex 等）经 **MCP Server** 调用本系统的理解能力。

---

## 现在到哪一步

**M0 · 骨架**（当前）。仓库结构、10 个留接口、SQLite schema、FastAPI 骨架已就位。

| 阶段 | 内容 | 状态 |
|---|---|---|
| M0 | 仓库骨架 + 留接口 + schema + 健康检查 | ✅ |
| M1 | Python 解析 → 符号 / 关系 / 入口 / 依赖 / 设计说明索引 | ⏳ |
| M1.5 | 知识层：概念本体 + 自动检测 + 项目实例 | ⏳ |
| M2 | 三路检索（BM25 / 稠密 / 符号关系）+ 流程追踪 | ⏳ |
| M3 | Agent Runtime + 只读工具 + 有界上下文 + 事实/推断分离 | ⏳ |
| M4 | 工作台（符号树 / 对话 / 证据面板 / 知识探索界面） | ⏳ |
| M5 | 评测：五组对照实验 + 报告 | ⏳ |
| M6 | 持续认知：增量索引 + 变更解释 + 过期检测 | ⏳ |
| M7 | MCP Server：把理解能力暴露给外部 agent | ⏳ |
| M8 | 关系图 + 演进时间线 | ⏳ |
| M9 | 用户研究 + 公开化（README / 报告 / 演示） | ⏳ |

---

## 跑起来

需要 Python 3.13+ 与 [uv](https://astral.sh/uv/)。

```bash
uv sync
uv run pytest -q
uv run ruff check .

# 建索引库
uv run ci init-db
uv run ci where

# 起服务
uv run uvicorn codeinsight.api.app:app --port 8020
```

## 目录

```
src/codeinsight/
  agent/       Agent Runtime：工具注册、调用循环、上下文装配
  api/         FastAPI 端点
  cognitive/   认知层：parsing · indexing · retrieval · embedding · concepts · changes
  eval/        评测：基准生成、对照臂、指标、报告
  execution/   受控命令执行接口（当前不实现）
  llm/         模型 Provider 接口
  storage/     SQLite 连接工厂与 schema
knowledge/concepts/   技术概念本体（YAML，一个概念一个文件）
frontend/      React 工作台
tests/         pytest 回归
docs/          架构、接口契约、ADR
```

## 留接口（换实现不动上层）

| 接口 | 位置 | 换成 |
|---|---|---|
| `LanguageParser` | `cognitive/parsing/base.py` | Tree-sitter / 其他语言 |
| `Embedder` | `cognitive/embedding/base.py` | 本地模型 / 其他 API |
| `KeywordIndex` | `cognitive/retrieval/base.py` | Elasticsearch |
| `VectorStore` | `cognitive/retrieval/base.py` | Qdrant / Milvus |
| `ConceptDetector` | `cognitive/concepts/base.py` | 规则引擎 / 模型辅助 |
| `DiffSource` | `cognitive/changes/base.py` | 非 git 变更源 |
| `Tool` | `agent/tool.py` | 更多工具 |
| `LLMProvider` | `llm/provider.py` | 多 provider |
| `CommandRunner` | `execution/base.py` | 自建沙箱（当前交给外部 agent） |

## 文档

| 文档 | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | **作业规程**——三条线通用的硬规矩（任何 agent 开工先读这份） |
| [`docs/functional-spec.md`](docs/functional-spec.md) | **功能实现需求书**——三线并行时三条线各自的实现需求与验收 |
| [`docs/workspace.md`](docs/workspace.md) | **工作区文档**——三个 worktree 在哪、谁能动什么、怎么合 |
| [`docs/roadmap.md`](docs/roadmap.md) | **路线图**——阶段划分，逐条对应源文档章节号 |
| [`docs/interfaces.md`](docs/interfaces.md) | **接口契约**——10 个留接口的约定与依赖方向 |
| [`docs/decisions/`](docs/decisions/) | **ADR**——每个技术决策的"为什么"与"什么条件下重评" |
| [`docs/requests/`](docs/requests/) | 契约变更请求——要改别人目录的东西，在这里提 |
| [`docs/ported-from-tapestry.md`](docs/ported-from-tapestry.md) | 从织忆移植了哪些代码、改了什么、丢弃了什么 |
| [`NOTICE.md`](NOTICE.md) | 第三方归属与数据隐私声明 |

> **功能范围**记在路线图，**技术决策**记在 ADR——范围会随进度调整，
> 决策会留下"为什么当时这么选"。范围变了要改 ADR（决策的前提变了），而不是默默改代码。

## 设计原则

1. **结论必须能落回 `file:line`** —— 引用信息放在结构化字段里，不随文本截断丢失。
2. **事实与推断分开** —— `facts[]` 每条带引用，`inferences[]` 显式标注为推断。
3. **不确定就标不确定** —— 静态分析定不了的动态调用保留 `confidence < 1`，不丢弃也不假装。
4. **上下文两层设界** —— 持久化层与模型上下文层分别设上限，截断用同一份对象写两处。
5. **检索无命中就说没命中** —— 不允许模型编造 `file:line`。

## License

Apache-2.0。见 `LICENSE`（M9 补齐）与 `NOTICE.md`（M9 补齐）。
