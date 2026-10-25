# 三线协作请求单（归档）

2026-10-24 至 10-25，仓库按 A（集成与 Agent）、B（知识层）、C（前端）三条线并行推进。
跨线要改接口时，提出方在 `docs/requests/` 写一份请求单，由 A 线统一改契约并同步。

这些请求全部落地后，请求单移到这里保存；`docs/requests/` 只留提出流程本身。

| 编号 | 内容 | 提出方 | 状态 |
|---|---|---|---|
| [0001](0001-built-in-learning-library.md) | 内置学习知识库、学习链接与阅读上下文 | B 线 | 已接入（依 0005 的跨线授权） |
| [0002](0002-index-engine-entry.md) | 索引引擎入口 `cognitive/indexing.index_project` | C 线 | 已合入 |
| [0003](0003-learning-integration-handoff.md) | 学习库接入收尾与概念解释置信度修正 | B 线 | 已完成（依 0005） |
| [0004](0004-query-endpoint.md) | 问答端点接线 `POST /query`、`POST /query/stream` | A 线 | 已解决 |
| [0005](0005-learning-runtime.md) | 知识层接入 Agent 运行时 | B 线 | 已合入 |
| [0006](0006-learning-loop-implementation.md) | 内置学习流程接入实施与临时跨线授权 | B 线 | 实施记录 |

0007（前端接手与截图风格恢复）还在 `codex/frontend-refinement` 分支上，尚未并入主线；
前端这条线收尾时一并挪到这里。

请求单里保留了当时的缺口描述和验收口径，不代表当前代码状态。
当前状态以 `knowledge/learning/VALIDATION.md` 和 `pytest` 为准。
