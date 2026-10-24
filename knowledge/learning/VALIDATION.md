# B 线学习功能交付与验证报告

- 日期：2026-10-24。
- 已验证实现：`530a6f0`（`feat/knowledge`）。本报告作为后续文档提交保存。
- 工作树：`<仓库根>-wt-knowledge`。
- 请求 0005 已获用户“临时授权跨线实现”。本次只在 B 工作树实现相关 A/C 接口与页面；
  没有修改另外两处工作树，没有由 B 合入 main，没有推送远程。

## 交付结果

学习功能在 B 分支已贯通：代码三栏工作台 → AI 回答的有效知识链接 → 右栏完整教材 →
有证据的项目实例 → 代码阅读 → 携带当前阅读目标继续追问。
目录、搜索和教材阅读本身不调用模型。

### 知识内容

- 66 个主题：Python 10、Web 6、JavaScript 8、TypeScript 6、React 8、SQL 8、工程概念 20。
- 20 个 YAML 概念本体；13 个来源记录及对应许可文件。
- 章节具有稳定 ID、锚点、标题/别名、摘要、前置知识、相关知识、内容版本和来源。
- 正文包含定义、用途、原理、逐步教学示例、误区及适用条件；SQL 标明方言。
- 原文地址、作者、来源版本/哈希、许可和修改记录保留于 `sources.json` 及各篇文章。
  CC-BY/CC-BY-SA 等教材沿用各自许可，不统一改标 Apache-2.0。

可直接审阅：

- [SQL 是什么](articles/sql/sql-database.md)
- [Python 函数与参数](articles/python/python-functions.md)
- [React 组件与 JSX](articles/react/react-components.md)

### 服务与项目关联

- 本地 FTS5 章节检索复用中文/标识符分词器；不依赖在线 Embedding。
- 目录、正文和 Agent 片段共用同一内容版本。教材整节按现有上下文预算注入，
  未能进入上下文的材料不冒充已引用来源。
- 完成目录、主题详情、章节搜索、主题关联项目实例与冻结代码阅读 API。
- Agent 注册知识工具，非流式与 SSE 最终答案携带知识来源、有效目标和最多 3 个推荐入口。
- “SQL 是什么”有教材支持即可回答；“这个项目哪里用了 SQL”仍需项目证据。
- 教材来源不伪造 `file:line`；项目位置读取真实索引/冻结 Git 源码并校验哈希。
- 检测实例保存命中证据、去重及置信度；普通同名调用、导入、动态调用和字符串不升级为确定事实。
- quick/project 不调用模型；deep 使用有界教材与项目证据，Provider 失败保留可解释结果与教材。
- schema 1→2 原地迁移，检测指纹独立编号；教材文字更新不触发概念重检。
- 提供 M5 待审核样本/计分工具和 M6 概念 claims 查询能力；不代表完整 M5/M6 已验收。

### 工作台交互

- 保留文件/符号树、AI 对话和右栏三栏结构及现有主题。
- 回答正文术语首次出现可链接已存在知识；代码块不加链接，错误目标退回文字。
- 流式增量中的知识链接暂不启用，最终经过服务端校验后显示为站内超链接。
- 右栏支持目录、搜索、完整章节、表格/代码、来源许可、相关知识及项目实例。
- 支持返回/前进/回到代码、阅读位置恢复；续问发送当前章节或代码目标，服务端重读实际内容。
- 切换项目隔离对话、阅读上下文和旧流回调；返回原项目保留该项目对话。
- Monaco 本地加载 worker 与 Python/JS/TS/SQL 定义，不依赖外部 CDN。
- 默认连接真实后端；`VITE_CI_MOCK=1` 才启用旧快照模式。

## 最终验证结果

| 检查 | 结果 | 验证边界 |
|---|---|---|
| 后端全套 pytest | **331 通过** | 当前 B 实现的生产装配、API、工具、迁移、知识及既有回归 |
| ruff check | **通过** | B 工作树全仓 |
| B 知识源码/测试及新增 Python 文件格式 | **通过** | 定向 `ruff format --check`，未重写其他线无关文件 |
| 前端 Vitest | **83 通过 / 13 文件** | 含 SSE、知识目标、历史、项目隔离等 |
| 前端 ESLint | **通过** | 当前前端 |
| TypeScript 与 Vite 生产构建 | **通过** | Monaco 延迟加载块较大，存在 Vite 体积提示 |
| Edge 实际浏览器 | **3 场景通过** | 真实 API/Git/SQLite；使用假 Provider |
| 全部教材加载/锚点/前置与关联链接 | **通过** | 加载器校验与知识测试；不代替逐篇人工审校 |
| 干净环境 wheel 安装 | **通过** | 从 site-packages 读取 66 主题、20 本体、13 许可；API 与 Runtime 冒烟通过 |
| 织忆固定版本实际索引 | **通过** | 688 文件、389 Python 模块、6543 符号、43135 边、6400 chunk；0 解析跳过 |
| 实例证据字段 | **3605 候选，0 空/非法证据记录** | 结构检查不等于语义准确率 |
| 人工精确率 ≥0.8 | **待独立人工验收** | 30 条分层样本尚无独立人工标签 |
| 完整召回率 | **未测** | 尚无完整 gold set；抽样快照不能证明召回率 |
| 真实模型效果、教材阅读体验 | **待验收** | 本轮真实 Provider 调用数为 0 |

浏览器三个场景实际覆盖：

1. SQL 对话 → 有效正文链接 → 完整章节 → 当前章节续问 → 相关章节 → 返回并恢复滚动位置 →
   回到代码续问 → 切换项目隔离并恢复对话。
2. 旧章节锚点提示 → Provider 故障 → 教材仍可阅读 → 目录搜索 React state。
3. 项目实例 → 符号/Monaco → 代码概念标签 → deep 故障降级 → 完整教材 → 返回代码；
   没有外部资源请求。

最终画面：本地 `.ci/browser/learning-workbench.png`。
该画面使用测试项目与固定假回答，不能作为真实模型生成质量的证明。

构建主 JS 约 464 KB（gzip 142 KB）；Monaco 延迟块约 2.72 MB（gzip 700 KB）。
后者触发 Vite 体积提示，首次打开代码编辑器需要加载该块。
安装包 TestClient 冒烟有现有 Starlette/httpx 弃用提示，无失败。

## 版本与证据

- 知识库版本：`eaad0882f7e72097d3041d354d4459ae70578044662c98a9f8d2c9dd3d6bed46`。
- 检测规则指纹：`1dcb393e610b511c6c23593afacfe8fb1ba56479a958452c224c4dec77304319`。
- 被测仓库：`<被测仓库>`。
- 固定引用：`agent-v1` → `e5532a8466381d22156c3eb9accb1bf5a0669f28`。
- 本轮实际索引报告：`.ci/tapestry-learning-index.json`；数据库：
  `.ci/learning-tapestry-52e9f03b.db`。报告另存执行源码哈希，区分未提交时执行的准确文件版本。
- 原 30 条待人工审核样本：`reviews/tapestry-agent-v1.json`。它保留历史检测快照，
  不改写成此次完整索引的数量或版本；计分工具对未审核数据输出 precision/recall/F1 为 null。
- 后端 wheel：`.ci/dist/codeinsight-0.1.0-py3-none-any.whl`；独立环境：`.ci/wheel-env`；
  安装检查及最终包 SHA256：`.ci/wheel-smoke.json`。
- `.ci/` 是本地验收产物，不进入 Git；可复现测试、浏览器脚本及固定样本随代码提交。

## 复核命令

在 B 工作树执行；下列 Python 路径是当前共享开发环境，也可先 `uv sync --extra dev`：

```powershell
& '<仓库根>/.venv/Scripts/python.exe' -m pytest -q
& '<仓库根>/.venv/Scripts/python.exe' -m ruff check .
Set-Location frontend
npm.cmd ci
npm.cmd test
npm.cmd run lint
npm.cmd run build
$env:CI_TEST_PYTHON='<仓库根>/.venv/Scripts/python.exe'
npm.cmd run test:browser
```

浏览器脚本使用已安装的 Edge，自动建立/清理临时测试项目并管理专用 18021/15174 端口，
不占用主线开发服务的 8020 端口。离线数据演示仍可使用
`python -m codeinsight.cognitive.concepts.examples.offline_demo`。

## 交接边界

原报告中的“知识 API 未接通”“页面待 C”“无 jieba”“依赖/打包未完成”等，
已被本次实际实现与验证替代，不再是 B 分支的代码缺口。
main 集成由 A 线完成，需在其最新主线上重新运行全量检查；本报告不替其他分支或未来合并结果背书。
尚未完成的验收是独立人工精确率、完整 gold set、逐篇人工阅读及真实 Provider 效果，
不能把自动化通过写成这些验收已经通过。
