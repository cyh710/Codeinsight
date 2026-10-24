# 0005. 知识层接入 Agent 运行时

- **提出方**：B 线
- **日期**：2026-10-24
- **状态**：✅ 已合入（2026-10-24）
- **附件**：[`0005-learning-runtime.patch`](0005-learning-runtime.patch)（A 线文件的最小改动）、
  [`0005-learning-runtime.proposal.json`](0005-learning-runtime.proposal.json)（整文件提案 + base sha）

## 请求内容

把内置教材接进问答链路，让「SQL 是什么」这类纯知识问题不因为项目代码
没命中就被弃答，同时保证教材命中**不会**变成项目事实。

跨线改动只落在 A 线文件：`models.py`（Answer 知识字段）、`agent/runtime.py`
（`LearningBridge`、`reading_context`、知识真值判定）、`agent/service.py`
（装配桥）、`api/query.py`（入参/出参）、`api/app.py`、`pyproject.toml`
（知识资产打包 + PyYAML）、`frontend/src/api/types.ts`。

## A 线的处理

1. **全部合入**，并保留 B 线的判定口径（`answer_policy.can_answer_from_knowledge` 是
   唯一的放行开关）。
2. **注册两个知识工具**（B 线注明由 A 做）：`search_knowledge` /
   `read_knowledge_topic`。注册表从 12 个变 14 个；教材工具的 `data` 里
   **没有** `citations`，所以它们不可能变成项目事实。
3. **修复一条误判**：模型在结尾写「独立示例，不是本项目代码」时，旧策略把
   「本项目」当成项目断言，导致每条教材回答都被判弃答。现在先剥掉否定短语
   再判定，「提议去查」的句子也不算断言（见 `test_answer_policy.py`）。
4. **补可观测性**：`Answer.dropped_citations` 记录「模型写过、校验拦下」的位置，
   CLI 会单独打印——这是审计信息，不给用户看。
5. **改了两个 C 线遗留断言**（`tests/test_api.py`）：`project` 深度现在多一条
   关系事实（3 条）；`deep` 在上游不可用时**降级**为教材 + 已有证据（200），
   不再 502。502 只留给「请求本身没法完成」。

## 合并时踩到的坑（供以后参考）

- 两条 feature 分支都改了 `frontend/src/api/mock.ts` 的同一个映射：C 写死
  `incomplete: false`，A 从事件透传。取透传——回放将来出现「未完成」样例时，
  非流式与流式必须一致。
- `feat/frontend` 给 `ChatStore` 加了 `switchProject`，但实现落在
  B 线的 `store/types.ts` 上，两边合并后类型要求一个没人实现的成员。
  补的实现顺带把「切项目 = 清空会话 + 重置工作台」接上——
  后端会话键本来就是 `project_id:conversation_id`。
- `api/indexing.py` 两边各写了一份「默认本体目录」：C 版带降级、B 版直接抛。
  合并结果：用 B 的 `knowledge_directory()` 定位，用 C 的 `None` 降级。

## 第二次合并（2026-10-24，三线收敛）

B 线收敛后合回 main（落后 12 个 commit、67 个文件），又碰到同一类问题的变体：

- **`switchProject` 签名又分叉了**：main 是无参「一刀切清空」，
  B 线是 `switchProject(projectId)`「按项目分别保存会话、切回来恢复」。
  取 B 线——它更符合后端会话键 `project_id:conversation_id` 的隔离语义。
  `store/types.ts` 里的签名同步改成带参。
- **两处 `switchProject` 调用重复**：main 和 B 线各自在 `selectProject` 里加了一遍，
  合并后变成连着调两次。删掉 main 那遍，保留 B 线的带参版本。
- **`mock.ts` 出现重复对象键**：`incomplete` 在同一对象字面量里出现两次
  （C 线的 `incomplete: false` 与 A 线的透传撞在一起）。
  `tsc --noEmit` **不报**这个错，`tsc -b`（build 用的）才报——
  所以「类型检查过了」不等于「能构建」。
- **`service.py` 出现两份 `ToolServices` 构造**：B 线那份不含 `learning=` 参数，
  在 learning 块之前；main 那份在之后、带 `learning=`。
  取 B 线的位置（`refresh_project_concepts` 要先跑），
  但参数用 main 的 `learning=learning`。
- **`ruff format` 一次性要重排 27 个文件**：B 线没跑过 formatter。
  全量格式化是安全的，但注意 `knowledge/` 下的教材 markdown 是 B 线资产，
  格式化范围要避开（`ruff format src tests`）。
- **新增依赖需要 `npm install`**：`remark-gfm`（教材里的 GFM 表格）与
  `@playwright/test`（浏览器验证）是 B 线声明的，main 的 node_modules 里没有。
  Python 侧无外网（不能动 `pyproject.toml`），npm 侧有——两边的规矩不一样。
