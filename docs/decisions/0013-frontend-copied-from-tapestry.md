# 0013. 前端复制织忆基建，只重写业务组件

- **状态**：已接受
- **日期**：2026-10-24
- **影响范围**：`frontend/`、`docs/functional-spec.md` §3.3
- **源文档**：§2.1 收尾句、§3.1 第一层

## 背景

CodeInsight 要有一个工作台（源文档 §3.1 第一层：AI 对话工作台、项目文件浏览器、
代码查看界面、关系可视化、演进时间线、知识探索界面、开发变更与测试结果面板）。

单人项目，前端要从零做：选型、设计系统、组件库、SSE 客户端、状态管理、主题、暗色模式……
这些**都不是本项目的差异化**，但每一项都要花时间，且做出来还不一定好用。

而同一个作者手里已经有一个跑着的、经过千级测试的 React 前端——
`ai-companion-agent@agent-v1` 的 `frontend/`（React 19 + Vite 8 + Zustand 5 + Tailwind 4）。

## 决策

**CodeInsight 不做前端视觉设计。直接复制织忆 `frontend/` 的基建，只重写业务组件。**

具体分三类处理（完整清单见 [`functional-spec.md` §3.3](../functional-spec.md)）：

| 类别 | 处理 |
|---|---|
| ✅ **直接复制** | `vite.config.ts`（SSE proxy 段必须留）、`tsconfig*`、`eslint.config.js`、`index.html`、`public/`、`src/index.css`、`src/theme/palettes.ts`、`src/store/themeStore.ts`、`src/hooks/useDelayedFlag.ts`、`src/components/common/` **全 11 个通用件**、`tests/helpers/http.ts`、通用件自带的 5 个测试 |
| 🔁 **抄结构不抄内容** | `src/api/client.ts`（BASE 模式）、`src/api/stream.ts`（SSE 解析 + watchdog）、`src/api/agent.ts`（`jsonRequest` + 错误类）、`src/store/chat*Actions.ts`（vanilla store + slice 拆分 + 类型集中）、`src/components/chat/`（MessageBubble / ChatWindow / InputBox / agentTimeline / AgentEventCard） |
| ❌ **不要** | 桌宠（`src/pet/`、`pet.html`）、`components/{pet,creation,settings,character,sidebar,memory}/`、角色/分支/记忆/微信/语音相关的全部 `api/` 模块与 store |

新增依赖只有两个：`@monaco-editor/react`（证据面板代码查看，**懒加载**）与
`reactflow`（M8 关系图）。

## 理由

- **前端不是本项目的差异化**。差异化在知识层（§2.6）、持续认知（§2.4）和评测（§6）。
  把时间花在前端通用件上，是把最稀缺的时间花在最不稀缺的地方。
- **复制比重新设计更快也更一致**。C 线的工作从"设计 + 实现"降级为"复制 + 替换"，
  视觉与交互直接继承一个已经跑着的应用。
- **SSE 那部分尤其值得抄**。织忆的 `src/api/stream.ts` 是手写解析
  （`getReader()` + `TextDecoder` + 按 `\n` 切行）+ **watchdog**
  （首字节 120s、流中静默 30s 则 abort 并渲染超时错误卡）。
  这套东西在真实模型服务不稳定时是必需品，自己重写一遍大概率漏掉 watchdog。
- **配套的测试夹具一起带过来**：`tests/helpers/http.ts` 的
  `sseResponse` / `hangingSseResponse` / `silentSseResponse` / `FakeEventSource`
  是专门为测这些边界写的，重写是纯浪费。
- **许可兼容**：织忆与 CodeInsight 同为 Apache-2.0，出处已在
  `docs/ported-from-tapestry.md` 记录（Apache-2.0 §4(d)）。

## 备选方案

| 方案 | 为什么不选 |
|---|---|
| 从零设计前端 | 通用件不是差异化；单人做设计系统是纯浪费 |
| 用 shadcn/ui 或 MUI 等组件库 | 引入新依赖与新视觉语言；且织忆那套通用件已经够用且经过验证 |
| 只抄 `common/` 不抄其余 | SSE 解析、watchdog、store 拆分法、测试夹具才是真正省时间的部分 |
| 干脆不要前端，只做 API + CLI | 全栈岗位的说服力弱一档；且工作台是演示差异化的主要载体 |

## 后果

- **得到的**：C 线几乎不阻塞，可立即开工；视觉与交互零设计成本；
  SSE 稳定性有现成方案；两个项目观感一致。
- **失去的**：前端**长得很像织忆**。这是要接受的事实——它不影响功能，
  但面试时如果被问"前端是你自己做的吗"，要如实说明是复用的（并说明改了哪些部分）。
- **将来要付的**：织忆前端升级时，CodeInsight 这边要手动同步；
  两边的 `package.json` 会逐渐分叉。

## 重评条件

- 当 CodeInsight 需要**与织忆明显不同的交互形态**（例如必须多标签并行对比多个仓库）时，
  重评是否脱离织忆的骨架。
- 当织忆的前端通用件被重写（重大改版）时，评估是否跟进或彻底分叉。
