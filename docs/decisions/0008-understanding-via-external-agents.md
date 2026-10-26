# 0008. 执行侧交给外部 agent，CodeInsight 只做理解层

- **状态**：已接受（2026-10-26 修订：补入"主动编排"方向，见文末修订节与 [ADR 0032](0032-orchestrated-execution.md)）
- **日期**：2026-10-23（修订 2026-10-26）
- **影响范围**：`execution/`（驱动器接口，原先只留 Protocol 不实现）、`agent/tool.py`（Agent 工具全部只读）、
  M7 的 MCP Server、0015 的编排执行
- **源文档**：§2.7 基础开发、测试与调试能力；§1.2「系统以理解为主线，开发为辅助」

## 背景

源文档 §2.7 定义了一个内置的轻量 Coding Agent：
创建/修改代码、读写文件、执行受控命令、生成并运行测试、分析失败、尝试修复。
§3.2 相应地列了 **Docker 沙箱**作为执行隔离。

但 §2.7 自己也写了两句定位：

> 「这一模块主要服务于项目理解场景，**不追求复杂大型工程的全自动开发**。」
> 「它的核心作用是将代码理解、实际操作、变更验证和认知更新**连接成完整工作流**。」

关键在第二句：这个模块的价值是**闭环**，不是"能写代码"。
闭环有四段——代码理解 / 实际操作 / 变更验证 / 认知更新——
CodeInsight 天然占住三段（它就是理解层），只有"实际操作"一段是执行侧的。

而"实际操作"恰好是当前生态里最成熟、最不该重造的部分：
Claude Code / Codex / Cursor 自带沙箱、审批、diff、测试集成。

单人项目若同时自建理解层与执行侧，两条主线都做不深。

## 决策

**CodeInsight 不实现写文件与命令执行。**

- `execution/` 保留驱动器 Protocol；**执行的发起见 2026-10-26 修订节**，
  但"写文件/跑命令"始终由外部 agent 的子进程完成，CodeInsight 自身代码不落一行文件编辑。
- Agent 工具**全部只读**（`mutating=False`）。
- M7 实现 **MCP Server**，把理解能力暴露出去：

```
codeinsight.search_code(query, top_k)
codeinsight.find_symbol(name)
codeinsight.get_callers / get_callees(symbol)
codeinsight.explain_concept(concept_id, depth)
codeinsight.get_changes(since)
codeinsight.get_module_overview(path)
```

外部 agent（Claude Code / Codex）作为 **MCP 客户端**调用这些能力，
拿到的是结构化的符号、关系、概念与原理，**不是一堆 grep 结果**。
改代码由外部 agent 做，改完把变更同步回 CodeInsight（→ M6 持续认知）。

源文档 §9 边界写的是「**不依赖**外部 Coding Agent 运行，可按需导入外部开发记录」——
集成 ≠ 依赖，不冲突；而"可按需导入外部开发记录"正好对应
`change_record.source = 'external_agent'`。

## 理由

- **闭环四段我们拿三段**，不丢任何一环：
  代码理解（本项目）→ 实际操作（外部 agent）→ 变更验证（本项目，M6 关联测试记录）
  → 认知更新（本项目，增量索引）。
- **沙箱是重资产且高风险**。Docker 沙箱 + 命令白名单 + 审批 + 超时 + 日志收集，
  单人做很容易翻车，而翻车的是"安全"——本项目的技术定位恰恰是可靠性。
- **外部 agent 已经在用户的实际工作流里**。让 CodeInsight 做它们的"项目记忆层"，
  是每天都能用上的，而不是演示时才跑。
- **MCP 正好在 JD 上**（米哈游 Agent 岗"前沿方向探索"里点名了 MCP、Agent Eval；
  加分项③点名 Code Agent / GUI Agent / Browser Agent / Computer Use）。
- 保留驱动器 Protocol 与 `mutating` 标记，将来要收回执行侧，接口已就位。

## 备选方案

| 方案 | 为什么不选 |
|---|---|
| 自建轻量 Coding Agent（照搬 §2.7） | 沙箱 + 审批 + 修复循环，单人做两头都不深 |
| Docker 沙箱 + 白名单命令 | 重资产；且沙箱做不好反而是安全负债 |
| 完全不做执行能力，也不暴露 MCP | 那 CodeInsight 只是个查询工具，与外部 agent 无集成，失去 §2.7 的闭环 |
| 直接用 Codex / Claude Code 的内置检索 | 它们不理解"持续项目认知"与"技术概念关联"，正是本项目的差异化 |

## 后果

- **得到的**：主线聚焦；不背沙箱这个包袱；与外部 agent 形成闭环；
  命中 JD 的 MCP / Code Agent 方向。
- **失去的**：源文档 §2.7-1/2/4/5/6/7（写代码、编辑文件、跑命令、跑测试、
  分析失败、自动修复）不由本项目提供。
- **将来要付的**：MCP Server 的接口设计要**外部 agent 用得顺手**——
  工具描述要写清、返回要结构化、错误要可读。这是 M7 的主要工作量。
- **依赖**：外部 agent 的可用性。本项目自身**不依赖**它也能独立运行
  （问答、知识探索、评测都不需要）。

## 修订（2026-10-26）：从"被动被调"补齐为"双向"

M7 落地的形态是**被动方向**：外部 agent 经 MCP 来查我们的认知。
用户方向（请求 0015）要求补上**主动方向**：用户把开发需求交给 CodeInsight，
由我们带着项目认知**编排**外部执行 agent（Claude Code 先行）完成任务，
再回到理解-学习主线。

本决策的内核不变——**CodeInsight 自身代码仍然不写文件、不跑任意命令**；
变化只在集成方向：

- `execution/` 从"只留 Protocol"变为实现**驱动器**（`ExecutorDriver`），
  它以子进程方式调用外部 agent 的无头模式（`claude -p`），编排与状态机见
  [ADR 0032](0032-orchestrated-execution.md)。
- 沙箱/审批/diff/测试集成仍由外部 agent 自带；CodeInsight 额外加的
  worktree 分支隔离与双重审批是**编排层防线**，不是自建沙箱。
- MCP Server 原样保留，两个方向组合成完整闭环：
  我们编排它干活，它干活时反过来查我们的认知。

## 重评条件

- 当出现"必须在 CodeInsight 内部闭环"的需求（例如要评测"辅助开发能力：
  基础任务完成率、测试通过率"这项指标）时，重评是否收回一个**极小的**执行侧
  （如"只跑 pytest"）。
- 当外部 agent 的 MCP 生态出现更好的标准时，重评 MCP Server 的接口形态。
- 当编排执行暴露出外部 agent 无头模式的可靠性问题（进度流断裂、Windows
  子进程行为差异）时，重评驱动器实现（ADR 0032 的重评条件）。
