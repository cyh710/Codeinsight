# C 线 · 前端 + API · 开工包

> **源文档 §3.1 第一层「交互展示层」/ §2.1 收尾句 / §2.3 智能问答的界面出口**
>
> 关键决策：**前端不做视觉设计**，直接复制织忆的基建（[ADR 0013](../decisions/0013-frontend-copied-from-tapestry.md)）。

---

## 0. 开工前

```bash
cd <仓库根>-wt-frontend
git branch --show-current     # 必须是 feat/frontend
git log --oneline -1
```

**按顺序读**（别跳）：

1. [`../../AGENTS.md`](../../AGENTS.md) —— 作业规程
2. [`../functional-spec.md`](../functional-spec.md) 的 **「## 3. C 线」** —— 你的实现需求
3. [`../decisions/0013-frontend-copied-from-tapestry.md`](../decisions/0013-frontend-copied-from-tapestry.md) —— 为什么复制而不设计
4. [`../workspace.md`](../workspace.md) —— 三线怎么协作

---

## 1. 你的车道（只有你能写）

```
frontend/                      整个前端
src/codeinsight/api/           API 路由实现
```

**其他所有目录只读。** 要改 → 写 `docs/requests/NNNN-xxx.md` 提给主线。

---

## 1.5 开工前要跟用户对齐的事

**这些不要自己拍板。** 开工时把下列问题摆给用户，给出你的推荐和理由。

| # | 要对齐的 | 为什么必须问 |
|---|---|---|
| **C-Q1** | **三栏各放什么**（左栏是文件树还是只有符号树？右栏证据面板要不要拆成两个 tab？） | 布局与信息密度是观感问题，用户天天看，返工代价高 |
| **C-Q2** | **Monaco 要不要** | 体积 ~5MB（要懒加载）；不要的话证据面板只剩纯文本+行号 |
| **C-Q3** | 概念卡是**右栏替换**还是弹层 | 弹层会挡住证据面板；替换会丢失对话上下文 |
| **C-Q4** | 暗色模式 | 沿用织忆的 `themeStore` + `palettes.ts`（工作量小），还是只做浅色（省事） |
| **C-Q5** | **界面语言** | 默认中文（源文档与目标用户是国内开发者）。README 另出英文摘要 |
| **C-Q6** | 项目切换器放左栏顶部还是顶栏 | — |

> **推荐**：C-Q1 / C-Q3 是最该先问的（影响后面所有组件）；
> C-Q2~Q6 可以带着默认值开工。

**问不到用户时**：按开工包「交互约定」表的默认执行，
在 ADR 里标注"未与用户确认"，提交信息写 `决策：X（未对齐，默认值，理由：…）`。

---

## 2. 今天的第一件事：复制织忆前端基建

**零依赖，现在就能干完。**

源：`<被测仓库>` 的 `agent-v1` 分支
取法：`git show agent-v1:frontend/<path>`

**清单与"不要哪些"全在规格 §3.3**，分三类：

| 类别 | 内容 |
|---|---|
| ✅ **直接复制** | `vite.config.ts`（**SSE proxy 段必留**）· `tsconfig*` · `eslint.config.js` · `index.html` · `public/` · `src/index.css` · `src/theme/palettes.ts` · `src/store/themeStore.ts` · `src/hooks/useDelayedFlag.ts` · `src/components/common/` **全 11 个** · `tests/helpers/http.ts` · 通用件自带的 5 个测试 |
| 🔁 **抄结构不抄内容** | `src/api/client.ts` · `src/api/stream.ts`（SSE 解析 + watchdog）· `src/api/agent.ts`（`jsonRequest` + 错误类）· `src/store/chat*Actions.ts`（vanilla store + slice 拆分 + 类型集中）· `src/components/chat/`（MessageBubble / ChatWindow / InputBox / agentTimeline / AgentEventCard） |
| ❌ **不要** | `src/pet/` · `pet.html` · `components/{pet,creation,settings,character,sidebar,memory}/` · 角色/分支/记忆/微信/语音相关的全部 `api/` 模块与 store |

### 依赖

与织忆完全一致，**只多两个**：

```json
"@monaco-editor/react": "^4.6.0",   // 证据面板代码查看
"reactflow": "^11.11.0"              // M8 关系图
```

### 五个不能忘的点

1. `vite.config.ts` 的 SSE proxy 段——`text/event-stream` 响应要注入
   `X-Accel-Buffering: no` 与 `Cache-Control: no-cache`。
2. `tests/helpers/http.ts` 是专门为测 SSE 边界写的
   （`sseResponse` / `hangingSseResponse` / `silentSseResponse` / `FakeEventSource`），
   **一定要一起复制**。
3. `common/` 的 11 个通用件和它们自带的 5 个测试一起带过来——
   这既是省事，也是"通用件没被改坏"的证明。
4. **Monaco 必须懒加载**（`React.lazy`）。它有 ~5 MB，
   不懒加载会让首屏白屏，违背 §2.1 收尾句「用户不需要逐个打开文件阅读」。
5. `src/main.tsx` 和 `src/App.tsx` 要重写（织忆的挂了两个入口，含桌宠）。

---

## 3. 今天的第一件事（并行）：三栏骨架 + mock 层

```
┌──────────────┬─────────────────────────┬──────────────┐
│  文件 / 符号  │      对话流（SSE）        │  证据面板     │
│  树          │                          │  file:line   │
│              │                          │  + 代码片段  │
│              │                          │  + 概念 chips │
└──────────────┴─────────────────────────┴──────────────┘
```

**mock 数据形状看 [`../../fixtures/README.md`](../../fixtures/README.md)**——
里面写死了 `sample-index.json` 的结构，**不必等主线的真实数据**。

`frontend/src/api/mock.ts`：按契约返回 fixture 里的数据。

---

## 4. API 契约（主线提供，可能一小时后到）

| 文件 | 内容 | 谁写 |
|---|---|---|
| `docs/api-contract.md` | 端点 + 请求/响应体 + SSE 事件词汇表 | 主线 |
| `frontend/src/api/types.ts` | 与契约一一对应的 TS 类型 | 主线 |

**在它到之前**：先做不依赖精确类型的部分——布局、通用件、mock 层、状态管理骨架。
**拿到之后**再写 `src/api/{projects,code,concepts,chat}.ts` 和真实的数据层。

端点清单在规格 §3.1，SSE 事件词汇表在 §3.2，可以先照着规划。

### SSE 事件（已知）

```
event: meta     data: {task_id, conversation_id, model, tools[]}
event: delta    data: {text}
event: tool     data: {name, status, summary}
event: evidence data: {path, lineno, end_lineno, qualname, snippet, lanes[], concepts[]}
event: answer   data: {facts[], inferences[], citations[], abstained, reason}
event: error    data: {code, title, hint}
event: done     data: {abstained, reason}
```

- `evidence` 让前端**边流边渲染证据面板**，不必等最终答案。
- `answer` 的 `facts[]` 与 `inferences[]` 前端**必须分开显示**（ADR 0007）。

---

## 5. 交互约定（已定，不要自己改）

| 项 | 决定 |
|---|---|
| 三栏之外的第 4 视图 | **不要**（关系图放 M8，先不加 tab） |
| 概念卡形态 | **右栏替换**（不弹层——弹层会挡住证据） |
| Monaco | **要**，`@monaco-editor/react` 只读 + 懒加载 |
| 暗色模式 | 要（沿用织忆 `themeStore` + `palettes.ts`） |
| 状态管理 | Zustand，一个 store 一个 slice，不用 Redux |
| 界面语言 | **中文**（README 另出英文摘要） |

---

## 6. 后续任务

| 顺序 | 任务 | 规格位置 |
|---|---|---|
| 6 | API 路由实现（`src/codeinsight/api/`） | §3.1 |
| 7 | 对话流 + 工具调用卡片 + 事实/推断双栏 | §3.3 |
| 8 | 符号树 | §3.3 |
| 9 | 证据面板（Monaco 只读） | §3.3 |
| 10 | **概念卡 + 代码侧 concept chips**（双向导航） | §3.3 |
| 11 | M8：React Flow 调用图 + 演进时间线 | §3.3 |

---

## 7. 验收

- [ ] `npm run test`（Vitest）绿，SSE 解析有测试
- [ ] `npm run lint` 绿
- [ ] `npm run build` 通过
- [ ] mock 模式下三栏能跑起来：点符号 → 右栏出定义；点代码片段的概念 → 出概念卡
- [ ] 概念卡在**右栏替换**，不是弹层
- [ ] Monaco 是**懒加载**（首屏不加载它）

---

## 8. 交回主线

- 提交信息用中文，格式 `feat: 做了什么`，正文写动机。
- `git commit` 可以直接做；**`git push` 必须等用户明确说。**
- 主线会每天把 `main` 合回你的分支——**合之前先 `git status` 确认干净**。
