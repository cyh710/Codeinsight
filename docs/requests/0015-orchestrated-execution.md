# 0015. 编排执行：对话内驱动 Claude Code 完成开发任务

- 日期：2026-10-26；状态：用户已批准完整计划（四项决策：Claude Code 先行、
  worktree 隔离 + 双重审批、对话内自动识别、自动变更学习卡）。
- 基线：`main@997b90d`；分支 `feat/orchestrated-execution`；独立 worktree
  `D:\yy2\CodeInsight-exec`（主工作区有 0014 在飞改动，不共用）。
  本地提交、不合并、不推送。
- 架构决策：[ADR 0032](../decisions/0032-orchestrated-execution.md)；
  [ADR 0008](../decisions/0008-understanding-via-external-agents.md) 已原地修订。

## 契约增量

- **schema 3→4** 原地新增 `execution_task`（project_id、conversation_id、question、
  plan_json、status、driver、branch、worktree、commit_before/after、result_json、
  created/finished）；迁移为空步骤（新表由 apply_schema 补建，先例 `2: ()`）。
  ⚠️ 在飞的 0014 也动 schema：若 0014 先合入（其版本 4→5），本计划顺延为 5→6，
  迁移键同步平移。
- 新端点：`GET /projects/{id}/executions/{task_id}`（含计划/进度/结果/学习卡）、
  `POST .../executions/{task_id}/approve|reject|abort|merge`；错误统一走 §0.3。
- `/query/stream` 与 `/query`：前置轻量分类（一次小 LLM 调用判 `answer | dev_task`，
  判为 dev_task 且执行器可用时进入编排）；最终 `answer` 事件/响应新增**可选
  `execution` 元数据**（照 §13 exploration 先例：旧客户端忽略）：
  `{task_id, status, plan, progress[], diff_summary, change_card}`，
  其中 `change_card` 为合入后生成（facts 带 file:line、impact、concept_ids）。
- `meta` 事件加 `execution_enabled: bool`（执行器可用性，供前端决定是否展示
  开发任务相关 UI）。
- 配置（config.py 走本单）：`CI_EXECUTOR`（默认 `claude-code`，`off` 关闭）、
  `CI_EXECUTOR_COMMAND`（缺省 `claude`）、`CI_EXECUTOR_TIMEOUT_S`（默认 1800）。
- 前端类型（types.ts）：`ExecutionPlan / ExecutionProgress / DiffSummary /
  ChangeLearningCard / SseAnswerEvent.execution`。

## 兼容与实施所有权

- 识别为 dev_task 但执行器关闭/未装 claude/非 git 仓库：**降级为普通问答**，
  answer 不带 execution 字段，正文说明原因——不报错不白屏。
- 执行 agent 只在隔离 worktree 分支上工作（ADR 0032）；两次人工确认
  （计划批准、验收合入）之间 CodeInsight 不碰用户分支；拒绝/放弃即删
  worktree，仓库回原样。
- 合入后自动增量索引（复用 `index_project(incremental=True)`）+ 学习卡
  组装（读 `change_record`，不重复分析）；失败降级为"无学习卡"，不影响
  merge 结果本身。
- `agent_event` 账本扩展 `execution.*` 事件类型（仅追加，不改旧值）；
  会话轮次（conversation_turn）照常记录带 execution 元数据的 answer。
- 不改既有 SSE 七事件词汇表的语义；不新增 SSE 事件类型（进度经
  `GET executions/{task_id}` 轮询，复用会话 running 轮询机制）。
- MCP Server（被调方向）原样不动。

## 验收

计划卡→批准→隔离 worktree 执行（用户检出零影响）→diff+变更解释→验收合入→
学习卡自动出现（事实带 file:line、概念可跳转教材）→追问上下文延续；
识别错误可退回普通问答；abort/reject/超时/执行失败各路径状态如实；
pytest + vitest + ruff + build 全绿；离线 Provider，真实模型调用 0
（真机验收另记：fixture 仓 + 真 `claude -p` 走一遍全流程，记录于本单）。

## 真机验收记录（2026-10-26，branch feat/orchestrated-execution）

fixture：`e2e/repo`（单文件 calc.py，add 函数故意写成减法）+ 真 deepseek-chat +
真 `claude` CLI（2.1.218），后端 8030，数据目录 e2e/data。

| 步骤 | 结果 |
|---|---|
| 提问「帮我修复 calc.py 里 add 函数的 bug…」 | SSE 事件流 `meta → answer → done`；LLM 判定 dev_task，计划准确命中 calc.py 与「减法应为加法」，answer.execution.status=planned |
| approve | 202 转 executing；真 `claude -p` 在隔离 worktree 执行 30s；进度 11 帧（Read/Bash/Edit 带 file 路径）回流 |
| 执行细节 | claude 改了代码但其 `git commit` 被权限拦截；**驱动器 git 兜底提交接住**（ci-exec 分支 commit c2e44d0）→ review |
| 隔离不变量 | 用户检出 calc.py 仍是 bug 版、`git status` 干净；改动只在 worktree |
| diff_summary | 1 文件 +1/−1，status=modified，来自 git numstat 事实 |
| merge | `merge --no-ff` 合入用户分支（3a37b6c）；用户检出的 calc.py 变为正确加法 |
| 学习卡 | 后台增量索引自动跑完，change_card 出现：calc/calc.add 的 body_changed（带 calc.py:1 引用）；concept_ids 空（该仓无概念命中，如实） |
| 清理 | worktree 目录删除，worktree list 无残留 |

发现与处置：claude CLI 的 `--permission-mode acceptEdits` 在无头模式下允许编辑
但默认拦 `git commit`——已由驱动器的 ensure_committed 兜底覆盖（本就是按
"不可信 agent 会不提交"设计的）。无需代码变更。
