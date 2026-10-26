# 0012. 通用项目探索首版

- 日期：2026-10-26；状态：用户已批准完整计划，统一跨线实施。
- 基线：9b927e8；分支 codex/project-exploration；不合并主线、不推送。

## 契约增量

- Answer/非流式/SSE 最终答案新增可选 exploration：版本、要点、流程、最多三个动作。动作种类仅 follow_up/code/knowledge/graph/timeline。
- Query 增加 action_origin，指向本会话持久化回答动作或当前概览入口；服务端重新解析，客户端说明不作为事实。
- 项目 overview 增加 project_intro、head_commit、index_epoch、exploration_entries；仅从已有索引生成，无额外模型调用。
- 回合增加 GET /projects/{id}/conversations/{cid}/turns/{request_id}；会话读取增加 exploration_state，PATCH 增加 clear_exploration。
- schema 3→4 原地新增 conversation.exploration_json，默认 {}。只保存当前目标和最多 12 条已展示要点，模型预算最多 4KB，不表示用户已掌握。
- 材料区新增 exploration 模式，身份绑定项目/会话/来源回合/知识目标。全文教材继续按原规则复用。

## 兼容与实施所有权

本次统一修改 Agent、storage、API、前端及相应冻结契约。旧客户端忽略新字段，新客户端兼容旧答案；索引及原有会话保留，不改知识内容和检测规则，不新增依赖。
结构化建议使用内部工具；失效或伪造附加内容降级，保留正常正文。版本变化不把旧结论静默当成新事实。

## 验收

迁移/重启、SSE 与非流式一致、动作来源重读、图关系和引用校验、草稿保护、重复提交、跨项目/会话、材料刷新、失效与 Provider 降级。离线 Provider，真实模型调用 0。
