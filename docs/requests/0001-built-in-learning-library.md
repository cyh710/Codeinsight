# 0001. 内置学习知识库、学习链接与阅读上下文

- **提出方**：B 线
- **日期**：2026-10-24
- **紧急度**：阻塞三线联调；不阻塞 B 线独立服务与内容开发
- **依据**：用户已明确要求实施本请求所附的 B 线计划，含新增知识目录；不是未经确认的默认需求。

## 已确认范围

主界面继续三栏；正文术语首次出现时链接到已有章节，回答末尾最多推荐三个入口。
内置 46 篇 Python/Web/JS/TS/React/SQL 基础文章和 20 个工程概念，中文教材级正文。
同一份版本化内容同时用于目录阅读、章节检索和模型上下文；知识引用与项目代码引用分开。
目录浏览不要求已经导入项目；项目实例只能由代码索引派生。
本次不包含可执行练习、进度系统或自动写回个人教材。

## 目录与依赖

1. 新增 `knowledge/learning/` 归 B 线；用户在实施计划中已确认该用途与归属。
2. 请 A 线显式声明 `PyYAML>=6.0`。标准库不能读取规格的完整 YAML，不能依赖环境偶然装有它。
3. 已同步 A 线 `569adec` 及其中的 `split_identifiers`，知识检索默认复用该函数。
   当前环境无 jieba，依照共享实现回退中文二元词；jieba 依赖声明仍由 A 线管理。
4. 打包时由 A 线纳入知识资产；B 线服务支持显式资产目录，不从被索引仓库查找教材。

## 接口请求（A 冻结，C 实现路由）

- `GET /knowledge/tree`：全局目录，返回分组与文章概览。
- `GET /knowledge/topics/{id}`：文章、章节、版本、来源、前置知识与关联主题。
- `GET /knowledge/search?q=&limit=`：返回章节命中，保留 topic_id、section_id、version、snippet、sources。
- 内部站内链接统一 `/learn/{topic_id}#{section_id}`，由 C 拦截并在右栏打开。
- 问答请求增加可选 `reading_context`：知识目标或项目代码位置，不接收客户端编造的教材正文。
- 问答响应及最终 SSE answer 增加 `knowledge_sources` 与 `learning_entries`，原字段向后兼容。
- 代码侧概念可通过 B 的 concept→topic 查询打开教材；知识服务不伪造概念实例或入库 ID。

## 检测与解释输入

现有 `EdgeView` 没有 confidence；检测器不能把不确定边升级为确定事实。
B 提供兼容适配器接受可选边置信度、按路径提供的冻结源码；A 将解析产物中的原始
confidence 与源码传入。字符串取证由 B 使用 AST 且带实际行号，字符串不独立认定概念。
普通 `decode`、`execute`、`commit` 等不能不带来源就命中 jwt/事务。
同名末段匹配保留为不确定候选，优先使用完整路径/导入别名解析与组合证据。

## Agent 与阅读上下文

A 通过 B 的章节检索结果注入有界上下文，不混入代码检索对照实验通道。
纯知识问题不因代码无命中弃答；项目事实继续要求真实 file:line；教学示例与设计推断标识来源。
C 保留知识/代码往返、滚动位置、当前会话；项目切换清除旧项目代码上下文。
流式链接完整且目标可解析后才启用；失效链接呈现普通文字。
消息保存原参考版本；稳定站内地址可打开当前文章，但版本已更新时应提示变化，
不得静默把旧正文作为新版本注入。B 的 reading_context 会拒绝不匹配版本。

## B 线现有可接入服务

`LearningLibrary(directory, tokenizer=...)` 提供 tree/get/search/resolve_term/resolve_href/context。
`KnowledgeService.prepare_turn(question, reading=..., max_bytes=...)` 返回有界教材上下文和最多三个入口。
`link_answer` 返回文本、结构化 targets 与 learning_entries；`validate_answer_links` 去除虚构站内地址。
`KnowledgeContext.references` 中每个命中都有 target(topic_id,section_id,version)、snippet、score、sources。
API 适配可用 dataclasses.asdict 序列化这些只读对象；由 A 最终冻结字段，不将内部类型直接当成已发布 HTTP 契约。
源代码、测试与离线演示位于 B 分支；完整使用说明位于 knowledge/learning/README.md。

## 技术决策记录（请 A 收录 ADR）

- 文章 Markdown + JSON 清单；本体 YAML 保留原接口。知识版本和检测规则版本分别计算。
- B 的版本指纹是 SHA256；原库 concept_version 是 INTEGER。A 持久化时维护单调整数与指纹对应，
  不将哈希字符串直接写入旧字段；检测实现变化同样触发规则版本失效。
- 教材先离线编写/核验，来源锁定与许可独立保存，模型解释不写回。
- 首版知识检索为本地 FTS5（外加标题/别名精确解析），与项目向量通道分离。
- 无来源/无证据不会生成链接或代码位置。deep 的模型引用只能使用输入证据白名单。
- deep 使用 async 以适配现有异步 LLMProvider；quick/project 无模型调用。

## 影响与验收

A：契约、配置依赖、Agent 接入、实例落库、打包；C：API、二级阅读与导航、SSE 测试。
B：内容、本体、检测、检索、解释及离线接入样例。B 不直接修改冻结文件或 A/C 实现。
必须分别报告 B 服务验收与整站集成状态；原始抽样 fixture 不能证明全量召回率。
