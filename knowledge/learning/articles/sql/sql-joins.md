# JOIN：关联多张表

## 先建立直觉 {#overview}

关联查询把多张表中的相关记录组合起来。例如，消息表只保存用户 ID，用户表保存名字；JOIN 可以把消息正文和发送者名字一起返回。它不会凭空理解两张表的业务关系，关联条件必须正确表达。

## 原理与执行过程 {#mechanism}

INNER JOIN 保留匹配记录；LEFT JOIN 还保留左侧未匹配记录，右侧相应列为 NULL。一个键在右侧匹配多行时，结果会扩展成多行，这是关系组合的正常结果，不一定是数据库重复出错。过滤条件放在 ON 或 WHERE，尤其对外连接可能产生不同语义。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```sql
-- PostgreSQL；users 与 messages 为教学表
SELECT m.id, m.text, u.name
FROM messages AS m
LEFT JOIN users AS u ON u.id = m.user_id
ORDER BY m.id;
```

## 一步一步读懂 {#walkthrough}

m 和 u 是表别名。按 user_id 与 id 的相等关系查找发送者。若消息的 user_id 为 NULL，LEFT JOIN 仍保留消息，name 为 NULL；INNER JOIN 则不会保留这一行。先画出两张小表并逐行配对，可以直接观察不同 JOIN 的结果。

## 常见误解 {#pitfalls}

关联条件遗漏会造成笛卡尔积。把一对多关联误当作一对一，会让汇总或分页数量出错。LEFT JOIN 后在 WHERE 强制右表字段满足条件，可能排除原本要保留的未匹配记录。

## 工程中的取舍 {#tradeoffs}

把数据规范化到多表可减少重复，但查询需要关联；过度反规范化则增加同步维护。性能应结合索引与实际计划观察。对于 ORM，仍应理解生成的 SQL，避免循环里不断查询关联对象。

## 接着探索 {#related}

- [主键、外键与数据约束](/learn/sql-constraints)
- [SELECT：查询、筛选与排序](/learn/sql-select)
- [聚合与 GROUP BY](/learn/sql-aggregate)
- [ORM：对象与关系数据之间的映射](/learn/orm)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
