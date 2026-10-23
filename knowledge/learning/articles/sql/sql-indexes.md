# 索引与查询代价

## 先建立直觉 {#overview}

索引是一种额外维护的数据结构，帮助数据库更快定位部分记录，类似书后按关键词定位页码的目录。它可能减少扫描，也会占空间并增加写入维护成本。不是每列都应建立索引，也不是有索引的查询一定更快。

## 原理与执行过程 {#mechanism}

数据库根据条件、排序、统计信息和预计成本选择执行计划。常见 B-tree 索引适合某些相等、范围和排序查询；组合索引的列顺序会影响使用方式。优化器可能认为扫描全表更便宜，这在小表或匹配大部分记录时很正常。EXPLAIN 显示计划，带实际执行的分析选项还会真正运行语句，需要理解其副作用。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```sql
-- PostgreSQL
CREATE INDEX messages_user_id_idx ON messages(user_id);
EXPLAIN SELECT id, text FROM messages WHERE user_id = 7;
```

## 一步一步读懂 {#walkthrough}

先建立按 user_id 组织的索引，再观察该查询计划。计划可能显示使用索引，也可能不使用；仅凭示例代码无法承诺具体结果。可以在固定数据规模下比较执行计划与时间，改变匹配记录比例，再观察选择何时变化。

## 常见误解 {#pitfalls}

索引不是查询结果缓存。对列使用某些函数后，普通索引可能不再直接适用。查询时间受冷缓存、并发和数据分布影响，单次测量不足以说明稳定收益。EXPLAIN ANALYZE 对写语句可能实际修改数据，不能随意在生产库试验。

## 工程中的取舍 {#tradeoffs}

优先根据真实常用查询设计索引，避免为假想请求增加全部写入成本。每次优化都应记录数据规模、计划与运行条件。概念检测只能说明出现索引相关证据，不能自动证明性能提升。

## 接着探索 {#related}

- [SELECT：查询、筛选与排序](/learn/sql-select)
- [聚合与 GROUP BY](/learn/sql-aggregate)
- [连接池：复用连接并限制并发](/learn/connection-pool)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
