# 契约变更请求

> 当前按授权任务使用特性分支。跨范围、契约、schema 或新依赖变更先在这里记录，
> 用户批准后实施；不再由固定的 A 线代改。协作规则见 [`../workspace.md`](../workspace.md)。

早期三线请求单在 [`../archive/three-lines/`](../archive/three-lines/README.md)，
后续请求保留在本目录。两套历史编号曾重叠，引用时应带文件路径，不能只凭编号判断。

## 为什么要这个目录

请求单记录范围、理由、调用点与兼容性，避免后续会话按旧假设修改接口。

口头说"你把那个改成 X"是不可靠的——消息会丢、会被误解、事后没人记得。
写下来才有痕迹。

## 怎么提

1. 核对本目录已有编号，在任务分支新建 `docs/requests/NNNN-<简述>.md`；编号递增、不复用。
2. 模板：

```markdown
# NNNN. <一句话说清要什么>

- **任务／分支**：任务名称与特性分支
- **日期**：YYYY-MM-DD
- **授权状态**：待确认／用户已批准（注明授权范围）
- **交付约定**：本地提交、合并与推送策略

## 要什么

具体到函数签名 / 字段 / 端点。

## 为什么

不这么做会卡住什么？有没有已经试过的替代方案？

## 影响

- 哪些文件要改
- 哪些调用点受影响
- 是否需要改契约文件（models.py / schema.sql / api-contract.md / types.ts）
- 是否破坏向后兼容
```

3. 未获授权先不修改契约。用户已明确批准的范围可直接实施，不因历史三线分工重复请求代改。
   代码、文档与类型同步，新增选择或范围变化再按作业规程对齐。

## 历史三线请求

| 编号 | 标题 | 提出方 | 状态 |
|---|---|---|---|
| 0001 | 内置学习知识库、阅读目标与接口 | B | 依 0005 临时授权完成本分支接入 |
| 0002 | 索引引擎入口 | C | A 已交付 |
| 0003 | 学习流程收尾与置信度修正 | B | 依 0005 完成，独立人工验收另计 |
| 0004 | 问答端点 | C | A 已交付 |
| 0005 | 学习接入与临时跨线授权 | B | 已合入（A 线侧记录：合入方式与踩坑） |
| 0006 | 内置学习流程接入实现与临时跨线授权 | B | B 线实施记录（与 0005 同一件事的两面） |
| [0007](0007-workbench-conversations-and-selection.md) | 工作台会话、材料与精确选区 | 统一实施 | 用户批准完整计划，已同步实现和契约 |

上表 0001–0006 的原文见三线归档；0007 为收拢后的请求。后续请求如下，
具体授权、验收和阶段结果以各文件及关联报告为准：

| 请求 | 范围 |
|---|---|
| [0008](0008-native-project-folder-picker.md) | 原生项目目录选择 |
| [0009](0009-project-relocation-and-modern-folder-picker.md) | 项目重新定位与现代目录窗口 |
| [0010](0010-project-index-loading-feedback.md) | 导入与索引状态反馈 |
| [0011](0011-learning-visual-assets.md) | 教材图文资产 |
| [0012](0012-project-exploration.md) | 项目导览与探索结果 |
| [0013](0013-answer-preservation-and-followup.md) | 回答保留与续讲 |
| [0014](0014-sidebar-and-project-removal.md) | 左栏与项目移除 |
| [0015](0015-workbench-clarity.md) | 工作台信息精简 |
| [0016](0016-learning-replies.md) | 学习讲解策略 |
| [0017](0017-integrate-executors.md) | 执行分支集成与历史兼容 |
| [0018](0018-orchestrated-execution.md) | 外部 agent 编排执行 |
| [0019](0019-index-read-recovery.md) | 索引读取恢复 |
| [0020](0020-continuous-analysis.md) | 持续分析与心跳 |
| [0021](0021-preserve-answer-body.md) | 完整回答正文 |
| [0022](0022-reply-typography.md) | 回复排版与范围链接 |
| [0023](0023-understanding-first.md) | 理解优先与兼容字段语义 |
| [0024](0024-source-snapshots-and-tool-recovery.md) | 源码快照与工具恢复 |
| [0025](0025-workspace-first.md) | 当前工作区优先 |
| [0026](0026-exploration-consistency.md) | 核心探索链路一致性 |
| [0027](0027-debug-core-consistency.md) | 并发与版本边界修复 |
| [0028](0028-current-behavior-docs.md) | 同步当前实现与文档描述 |
