# 0003. 学习库接入收尾与现有概念解释的置信度修正

> 状态更新（2026-10-24）：下文是提出请求时的缺口快照，现已依请求 0005 完成本分支
> 接入及置信度修正；不再代表当前 API/前端状态。验收证据见 knowledge/learning/VALIDATION.md。

- 提出方：B 线；日期：2026-10-24。
- 补充请求 0001；不改变已确认需求，不修改 A/C 所有文件或冻结契约。
- 已读集成基线：`3734c1e`，包含 A 的索引/设计说明和 C 的三栏/API。

## B 已提供的统一适配

`cognitive/concepts/integration.py` 的 `LearningBridge(KnowledgeService(library))`：

| 接入位置 | B 侧调用 |
|---|---|
| GET /knowledge/tree | `bridge.tree().data` |
| GET /knowledge/topics/{id} | `bridge.topic(id)`；error=topic_not_found 时 C 映射 404 |
| GET /knowledge/search | `bridge.search(q, limit).data` |
| Agent 知识通道 | `prepared = bridge.prepare_turn(question, reading_context=..., max_bytes=剩余预算)`，注入 `prepared.as_tool_result()` |
| 非流式 / 最终 SSE | `bridge.finalize_answer(text, prepared)` 返回相同知识来源、有效学习目标与最多三个入口 |

正式 API 字段仍以 A 冻结结果为准；适配不自动注册新端点，不把新模型伪装成旧契约。
同一回合必须保留 prepared，不能最终回答时重新检索导致来源版本或预算口径改变。
阅读目标过期、章节删除、参数错误或预算不足均有 reading_status 与可解释 error。
代码 reading_context 由 A 代码读取通道处理；B 不读取或信任客户端代码正文。
知识上下文与代码检索评测分离，正文学习目标与实际引用来源分离。
纯指代续问不按“是什么意思”等通用词检索；缺少阅读目标标记 missing。
正文同名术语按当前教材语言消歧，不把 React 的函数跳转到 Python，
也不把“请求重新渲染”里的普通动词当作 HTTP 知识来源。

## 当前实际缺口与责任

1. A：冻结请求 0001 的 API/问答类型增量，声明 YAML 依赖和资产打包。
2. A：Agent 的普通知识问答不能因代码检索空而弃答；接入上表知识通道，
   并在最终普通答案/SSE 中透传 metadata；按 frozen sources/confidence 运行检测并落库。
3. C：注册三个全局知识端点；右栏增加目录/搜索/正文/锚点；拦截已解析链接；
   保留导航来路和阅读位置、给续问携带目标、项目切换隔离代码上下文。
4. C：验证分段 SSE 链接完成后才可点击、旧目标降级和上下文恢复。

## 现有 API 解释逻辑需要复用 B 服务

`api/knowledge.py::explain_concept` 当前 project 把每个 concept_instance 都直接放入
facts，**未检查 confidence**，会把 B 正确保留的低置信导入/动态候选升级为项目事实。
应改为复用 B 的异步 `explain(..., depth=ConceptDepth.PROJECT)`：
confidence < 0.8 的候选进入 inferences，证据与未知标记保留，零模型调用。

deep 也应复用 B `explain`：Provider 未配置/失败时返回本体教材与已有证据的可解释降级，
当前 API 直接 502 会丢失 B 已实现的阅读 fallback。事实与关系必须由真实索引提供，
不能为了接线构造项目实例。

## 验证与后续验收

B 新增三线共用适配测试，包括 66 主题序列化、浏览/搜索同版本、阅读重读与失效、
预算不足、普通/SSE 最终共用投影、错误链接和来源隔离；不冒充已完成浏览器验收。
M5 30 条真实仓库待人工审核样本及计分 CLI 已就绪；没有人工标签不宣称准确率达标。
M6 `compare_claims` 已提供支持/不确定/未观察到查询，缺少命中不是设计必然失效。
