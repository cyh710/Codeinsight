# 0025 · 当前工作区优先的项目理解

- 授权：2026-10-28，用户选择“完整调整：当前文件为主，索引辅助，历史快照保留”。
- 基线：a9708e9；分支 codex/workspace-first。本地提交，不合并、不推送；保留 .zcode/。

## 范围

普通问答可独立浏览、搜索和读取当前项目目录，不以索引文件表或 Git 提交作为准入条件。未提交、新增文件以及实验文本同样可读。索引仍提供语义候选、符号和静态关系，但明确属于索引版本，不能当作当前工作区的已验证关系。

读取的工作区字节保存为内容寻址快照，来源与材料按项目、路径、内容哈希标识；历史回答、分页和选区不默默换到最新磁盘内容。复用已有 file_snapshot 表记录 workspace:<hash> 归属，不迁移 schema。

## 契约

Citation / CodeReadingContext 增加可选 source_kind（workspace/index）与 content_sha256；索引引用保留 index_epoch/head_commit。GET code 增加 source_kind；未指定版本时默认当前工作区，显式 epoch/commit 继续兼容历史索引。工作区历史必须有此项目此路径的已记录哈希，不接受任意缓存读取。

GET files 保留默认索引数组，增加 source_kind=workspace 获取当前文件；数组项增加可选 source_kind/workspace_scan_truncated/workspace_unavailable，当前工作区哈希在实际读取时取得，不冒用旧索引哈希。扫描或展示截断可指定工具path子目录继续；目录不可用时文件树回退已索引清单。workspace源码失败复用reading_invalid错误码并返回具体hint，不误报必须建索引。

新增只读工具 list_files/search_files，read_file 默认 workspace，可显式读取 index。工具结果及来源携带实际版本。文件树支持工作区目录；无索引不阻断普通问答。路径限制在项目根内，排除缓存、二进制、密钥文件，限制扫描量并报告截断；不提供命令执行、不自动重建索引。

涉及工具、运行时、来源校验、选区、API、前端类型/页签/URL/阅读器。沿用现有预算、取消、去重、无进展恢复，不恢复总轮次上限。

## 验证

离线覆盖无索引、未提交/新增文件、实验结果、真实修改后的旧来源、中文/emoji选区、路径越界/符号链接/密钥、限额、过期索引关系、SSE/非流式版本一致和浏览器刷新恢复。全量 pytest/Ruff、前端 test/lint/build 及相关 Playwright。真实模型调用为0，不修改用户源码/索引、不结束已有服务。
