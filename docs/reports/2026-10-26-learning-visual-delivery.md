# 教材图文闭环与三篇样章交付

日期：2026-10-26。分支：`codex/learning-visuals`。

## 本轮范围与进度

用户要求先提交当前工作区，再按已对齐计划实施。此前启动器、项目重新定位、索引反馈、
侧栏状态及紧凑布局等工作，已在 `main` 本地提交为 `997b90d`，53 个文件；未推送。
提交前后端 422 项、前端 123 项测试及 Ruff/ESLint/构建通过。

随后创建本分支，完成计划阶段 1–3：内容纠错、资源契约与版本、图文阅读闭环、三篇样章。
现有知识库为 **67 个主题、4 张原创 SVG 图**。12 个候选主题及完整学习路线属于样章评审后的批次，
本轮没有把它们报告成已完成，也没有批量给其余文章配同一套图文模板。

## 三篇实际样章

| 内容 | 本轮完成 | 实际工作台截图 |
|---|---|---|
| [Python 函数](D:/yy2/CodeInsight/knowledge/learning/articles/python/python-functions.md) | 从 print/return 的实际输出展开，加入执行图；修正默认参数、None、局部结果及接口兼容解释 | [截图](D:/yy2/CodeInsight/.ci/browser/learning-python-visuals.png) |
| [SQL 入门](D:/yy2/CodeInsight/knowledge/learning/articles/sql/sql-database.md) | 明确 SQLite 3；展示商品与订单、外键引用图、JOIN 结果；修正折扣与改名，保留原锚点 | [截图](D:/yy2/CodeInsight/.ci/browser/learning-sql-visuals.png) |
| [状态生命周期](D:/yy2/CodeInsight/knowledge/learning/articles/engineering/state-lifecycle.md) | 新增事故复盘；通过数据证据、状态归属树、HMR 身份图与存储对照区分两种空列表原因 | [截图](D:/yy2/CodeInsight/.ci/browser/learning-state-visuals.png) |

三篇按正则粗计汉字分别约为 2237、1946、2235（含资料尾部），仅用于说明保留长文，
不作为学习质量指标。写法分别围绕机制、数据观察和故障证据，练习没有统一数量。
样章使用适合问题的列表、表格及树/流程图。本批没有需要额外辨认的工具界面，未为凑数量插入截图；
这里的工作台截图是验收证据。资源通路同时支持 PNG/WebP，后续工具教程可加入真实截图。

## 图文能力

- 资源清单、SVG 与可编辑生成脚本归知识资产管理，随 wheel 分发，离线可读，无新运行依赖。
- 图有尺寸、图注、图意、作者、许可及内容哈希；图片实际字节参与所属文章版本，不让其他文章无谓过期。
- 图片只从当前教材清单解析，API 按 ID/哈希提供字节。未知、旧 URL、缺失或损坏明确降级，正文仍可阅读。
- 预留图片高度，提供放大、Esc/按钮关闭、焦点返回；关闭不改变提问目标与阅读位置。
- 图注映射 Markdown 原文 UTF-16 偏移，可精确选择提问。SVG 标签不伪装成原文选区。
- 文字模型读取正文及维护的图意，不假定具备视觉能力，不把教学图当成项目事实。
- 复用未变化的 Markdown 渲染，修复滚动保存导致图片组件重建、失败状态丢失的缺陷。

契约与取舍见 [请求 0011](D:/yy2/CodeInsight/docs/requests/0011-learning-visual-assets.md) 和
[ADR 0028](D:/yy2/CodeInsight/docs/decisions/0028-learning-visual-assets.md)。
作者规范见 [AUTHORING.md](D:/yy2/CodeInsight/knowledge/learning/AUTHORING.md)。

## 验证结果

| 检查 | 结果 |
|---|---|
| 后端全量 pytest | **431 通过** |
| 前端 Vitest | **125 通过** |
| Playwright / Edge 全量 | **41 通过** |
| Ruff、修改 Python 文件格式、ESLint、TypeScript/Vite 构建 | **通过** |
| 图片生成器 `--check`、SVG 内容与哈希 | **通过**，4 图可重建，不依赖网络字体/外部图源/脚本 |
| wheel 离线构建、独立目录加载与资源校验 | **通过**，67 主题、4 图 |
| 示例行为 | **通过**，提取文章 Python/SQL 执行，核对 None、默认参数、折扣、JOIN、外键失败与表改名 |
| 知识入口探测 | SQL、函数参数、React state、HMR、状态丢失均进入对应主题；这是诊断探测，不计正式准确率 |

浏览器新增场景覆盖真实图加载、放大关闭、焦点与位置、图注经服务端重读、缺图/重试、返回材料、
360/480/720px 材料宽度，以及 900/1024/1280/1440px 视口。旧工作台回归同时通过。
旧菜单测试原先把“整节可见”视为“章首到达阅读起点”，文章长度变化暴露了该假设；
测试已改为明确滚到章首，不为迎合测试改变当前阅读目标的判定规则。

一次开发中发现 Windows `write_text` 的换行转换会使生成时哈希与实际 SVG 字节不符。
生成器现固定 UTF-8/LF 字节，测试核对真实字节，并覆盖资源损坏后的正文可读性。

测试使用临时项目与脚本化 Provider；**真实模型调用为 0**。
浏览器截图及示例执行不等于初学者已读懂；样章的人类阅读密度与讲解效果仍待用户评审。
保留既有 Monaco 构建体积提示与 React Flow 开发警告，本轮未扩大到这些无关改造。

## 查看方式与下一步

后端新增了图片端点，已运行的旧进程需要重启加载。确认没有生成中的回答后，在原启动窗口
按 Ctrl+C，重新运行根目录启动器，再刷新网页。不需要删除索引、重新导入项目或改数据目录。
本轮未强制结束用户已有服务。

启动后可打开：

- `http://127.0.0.1:5173/learn/python-functions#example`
- `http://127.0.0.1:5173/learn/sql-database#relationships`
- `http://127.0.0.1:5173/learn/state-lifecycle#ownership`

三篇已可审查，下一阶段先校准实际图文密度，再按运行项目、数据去向、调试恢复逐批扩充。
不推送远程，不自动合并本分支。
