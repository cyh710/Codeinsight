# 0009 · 重新定位源码目录与现代文件夹选择框

- 日期：2026-10-26
- 状态：用户明确要求修复，沿用本会话跨线实现授权。

## 契约增量

新增 `POST /projects/{id}/relocate`，请求 `{root_path: string}`，响应 202 复用
`CreateProjectResponse`。按 ID 保留项目名称、对话、回合和原有工作区记录。
只接受具有有效 HEAD 的 Git 仓库根目录。索引中或正在生成回答时返回 409。

请求受理先写 `index_run` 运行标记；后台以事务重建索引并切换路径，成功一起提交。
失败回滚旧索引与路径并保存失败原因；服务重启将未完成的重新定位标为失败，允许重试。
`ProjectDetail` 增加可选 `index_error`，用于展示重建失败原因。
前端失效路径处提供“重新定位”，显示原路径、选中路径和明确的提交按钮。

## 系统窗口

织忆浏览器通过 `input[webkitdirectory]` 打开现代系统文件夹窗口，但浏览器不会提供完整
本地路径。CodeInsight 需要 Git 根路径，因此保留原有仅本机的路径选择 API，在 Windows
子进程中通过标准库 ctypes 调用 `IFileOpenDialog(FOS_PICKFOLDERS)`，获得同类现代外观。
不上传目录、不增加依赖；取消、超时、锁和本机 Origin 检查沿用现有语义。
