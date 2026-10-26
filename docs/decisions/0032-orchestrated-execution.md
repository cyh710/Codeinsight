# 0032. 编排执行：驱动器 Protocol + worktree 隔离 + 双重审批

- **状态**：已接受
- **日期**：2026-10-26
- **影响范围**：`src/codeinsight/execution/`（新）、`api/executions.py`（新）、
  `agent/runtime.py`（对话内识别挂 `execution` 元数据）、schema 3→4（`execution_task` 表）
- **关联**：[ADR 0008](0008-understanding-via-external-agents.md)（2026-10-26 修订）、请求 0015

## 背景

用户把开发/修补需求直接提给 CodeInsight，期望"我们调 Claude Code / Zcode 干活，
再根据产出帮用户理解与学习"。执行仍交给外部 agent（ADR 0008 内核不变），
但**发起方**变成 CodeInsight——需要定义编排层的安全与结构。

关键约束：执行 agent 改的是**用户真实的仓库**。一次跑偏的自动执行会弄脏
用户正在进行的活，这类事故的代价远高于多一次确认。

## 决策

### 1. 驱动器 Protocol，Claude Code 先行

```python
class ExecutorDriver(Protocol):
    name: str
    async def execute(self, request: ExecutionRequest, emit: ...) -> ExecutionResult: ...
```

- 第一批只实现 `ClaudeCodeDriver`（`claude -p --output-format stream-json`，
  本机已装、无头模式成熟）；**Zcode 已接入**（2026-10-26，`ZcodeDriver`：
  node + zcode.cjs 无头模式，`--mode yolo` + stdin 断开——权限等待在无头下
  会永久阻塞，隔离与审批由编排层负责）；两者真机验收通过。
- CodeInsight 对驱动器的全部假设只有一条：给它隔离检出目录与组装好的
  prompt，它把变更提交到该目录的 git 分支上并回流进度事件。
  不假设 agent 的内部状态，不解析它的会话语义之外的任何东西。

### 2. worktree 分支隔离（不是"开个分支"）

每个任务用 `git worktree add` 建**独立检出目录** + 任务分支：

- 只开分支不开 worktree 会切换用户当前检出的内容——不可接受。
- worktree 目录下用户的暂存区、未提交改动、IDE 状态零影响。
- 验收合入（第二道审批通过）后才 merge 回原分支并清理 worktree；
  拒绝/放弃则整目录删除，仓库回到原样。

### 3. 双重审批门

```
planned（计划卡）→ 用户批准 → executing（隔离 worktree 内）
→ review（diff + 变更解释）→ 用户验收 → merged（合入 + 增量索引 + 学习卡）
```

- 第一道（计划）：LLM 用项目认知生成结构化计划（意图/文件/思路/风险），
  用户不点头不 spawn 执行进程。
- 第二道（验收）：执行完成后只展示不落盘到用户分支，用户确认才 merge。
- 对话内自动识别为开发任务后，用户可一键退回普通问答（识别有误判）。

### 4. 执行后的学习闭环（为什么编排值得做）

合入后自动：增量重建索引（M6）→ 读 `change_record` 生成变更学习卡
（改了什么·带 file:line；影响谁·反向可达；涉及概念·链概念卡与教材）。
这是"编排外部 agent"相对"用户自己开 Claude Code"的差异化：
**执行完的认知增量沉淀回 CodeInsight，学习主线不断**。

## 理由

- 驱动器接口而不是深度集成：外部 agent 迭代快（claude CLI 参数常变），
  把版本差异锁在一个驱动器文件里，换 agent / 升级不动编排器。
- worktree 而非容器：零依赖、git 原生、删除即回滚；容器方案（ADR 0008
  已拒绝自建沙箱）在编排层重演同一问题。
- 双重审批而非自动执行：本项目的定位是可靠性，用户是唯一对"什么该进
  仓库"负责的人；两次确认的成本远低于一次错误合入。

## 备选方案

| 方案 | 为什么不选 |
|---|---|
| 直接在用户工作区执行 + 事后解释 | 快，但跑偏即污染用户在干的活 |
| 只开分支不开 worktree | 分支切换动用户的检出内容 |
| 免审批自动合入（执行完即 merge） | 学习闭环的价值前提是变更可信；不可信的自动合入是负资产 |
| 自建 Docker 沙箱跑执行 | 重演 ADR 0008 拒绝过的沙箱包袱 |

## 后果

- **得到的**：CodeInsight 从"理解工具箱"升级为开发任务编排者；
  执行后认知增量自动回流（学习卡）；两个方向（MCP 被调 + 编排调人）闭环。
- **失去的**：全自动（每个任务两次人工确认）；对未装 Claude Code 的环境
  该功能降级关闭（`CI_EXECUTOR=off` 或命令不存在时对话识别退回普通问答）。
- **将来要付的**：驱动器要跟随 claude CLI 的无头接口演进；
  Windows 子进程与 stream-json 的解析要有录制样本回归测试。
- **依赖**：本机装有 claude CLI；仓库是 git（非 git 仓库不出执行选项）。

## 重评条件

- Zcode 等第二个驱动器接入时，若 Protocol 表达不了它的执行模型，重评接口。
- 若 claude CLI 的 stream-json 格式破坏性变更频繁到驱动器维护成本过高，
  重评是否改用更稳的集成通道（如 MCP 客户端方向反用）。
- 若用户研究（M9）表明双重审批过重，重评是否允许"低风险任务自动过第二道"
  （第一道永远保留）。
