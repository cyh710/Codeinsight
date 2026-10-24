# ADR · 架构决策记录

> 每条 ADR 记录一个**已经做出的技术决策**：当时的背景、为什么这么选、放弃了哪些方案、
> 以及**什么条件下应该重新考虑**。

## 与路线图的关系

| | 记什么 | 位置 |
|---|---|---|
| **功能范围** | 这个阶段做哪些功能、砍哪些、为什么 | [`../roadmap.md`](../roadmap.md) |
| **技术决策** | 这件事**怎么实现**、为什么不用别的 | 本目录 |

范围会随进度调整；决策会留下"为什么当时这么选"。**范围变了要改 ADR**（决策的前提变了），
而不是默默改代码。

## 状态取值

| 状态 | 含义 |
|---|---|
| `提议中` | 还没决定，只是候选方案 |
| `已接受` | 定了，正在或已经按它做 |
| `已废弃` | 不再适用（保留记录，注明被哪条取代） |
| `被取代` | 由另一条 ADR 取代（注明编号） |

## 命名

```
NNNN-简短英文短语.md
```

编号**连续、不复用**。废弃的条目保留原编号，**不删除**。

## 模板

见 [`template.md`](template.md)。新建时复制一份，编号递增。

## 索引

| 编号 | 标题 | 状态 |
|---|---|---|
| [0001](0001-stdlib-ast-parser.md) | 用标准库 `ast` 而非 Tree-sitter | 已接受 |
| [0002](0002-sqlite-numpy-vector-store.md) | 向量存储用 SQLite + numpy 而非向量数据库 | 已接受 |
| [0003](0003-sqlite-fts5-pretokenized.md) | 关键词检索用 SQLite FTS5 + 入库预分词 | 已接受 |
| [0004](0004-dual-layer-staleness.md) | 过期判定用符号级 + 文件级双层哈希 | 已接受 |
| [0005](0005-symbol-boundary-chunking.md) | 切块按符号边界，超大符号二次切分 | 已接受 |
| [0006](0006-citation-outside-content.md) | 引用信息与文本内容分离 | 已接受 |
| [0007](0007-facts-vs-inferences.md) | 事实与推断分开存放 | 已接受 |
| [0008](0008-understanding-via-external-agents.md) | 执行侧交给外部 agent，CodeInsight 只做理解层 | 已接受 |
| [0009](0009-single-agent-multi-tool.md) | 单 Agent + 多工具，不做多 Agent 协作 | 已接受 |
| [0010](0010-two-layer-context-bounds.md) | 上下文两层分别设界 | 已接受 |
| [0011](0011-concept-ontology-is-curated.md) | 概念本体是人工策展的 YAML，不是自动生成的知识图谱 | 已接受 |
| [0012](0012-tool-failure-degrades-not-raises.md) | 工具失败降级为可解释的错误，不抛异常 | 已接受 |
| [0013](0013-frontend-copied-from-tapestry.md) | 前端复制织忆基建，只重写业务组件 | 已接受 |
| [0014](0014-file-role-taxonomy.md) | 文件分类用单列 `role`，不用三个布尔列 | 已接受 |
| [0015](0015-index-scope.md) | 索引范围分三档，检索层不引入打分系数 | 已接受 |
| [0016](0016-design-staleness-by-evidence-loss.md) | 设计说明过期按「证据消失」判定 | 已接受 |
| [0017](0017-graph-projection-and-layout.md) | 关系图只画可定位的边，布局确定性分列 | 已接受 |
| [0018](0018-timeline-read-only.md) | 时间线只读索引当时写下的数字 | 已接受 |
| [0019](0019-learning-sources-and-reading-context.md) | 教材来源独立于代码证据，阅读目标由服务端重读 | 已接受 |
