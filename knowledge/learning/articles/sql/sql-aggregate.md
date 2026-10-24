# 聚合与 GROUP BY

## 先建立直觉 {#overview}

聚合把多条记录汇总成指标，例如消息数、总金额或每个用户的记录数。GROUP BY 指定按什么分组，聚合函数在各组内计算。汇总会丢失部分明细，所以需要确认你要回答的是明细问题还是统计问题。

## 原理与执行过程 {#mechanism}

COUNT(*) 统计行数，COUNT(column) 通常忽略该列的 NULL。SUM、AVG 等函数也有自己的空值规则。WHERE 先过滤输入行，HAVING 对分组结果过滤。关联查询若扩展了行数，后续聚合也会受到影响，不能盲目用 DISTINCT 掩盖错误关系。

## 跟着例子理解 {#example}

```sql
-- PostgreSQL
SELECT user_id, COUNT(*) AS message_count
FROM messages
WHERE text <> ''
GROUP BY user_id
HAVING COUNT(*) >= 2
ORDER BY message_count DESC;
```

## 一步一步读懂 {#walkthrough}

先排除正文为空字符串的记录，再按 user_id 分组。每组计算记录数，只保留至少两条的组。最后按数量排序。若想同时知道每条消息的正文，就不能把任意 text 直接塞进聚合结果；需要另一个明细查询或合适的窗口函数。

## 常见误解 {#pitfalls}

空表上的 COUNT 与 SUM 不一定得到相同形式的空结果。平均值的分母必须符合业务含义。分页后的条目数不能当作完整数据总数。关联造成的重复会污染统计，应先确认粒度。

## 工程中的取舍 {#tradeoffs}

在数据库中聚合能减少传输，但需要索引、计划与数据规模相匹配。预计算指标提升读取速度，却增加更新和修复成本。报告结果时应记录统计范围、时间区间和过滤条件，避免正确计算回答了错误问题。

## 接着探索 {#related}

- [SELECT：查询、筛选与排序](/learn/sql-select)
- [JOIN：关联多张表](/learn/sql-joins)
- [索引与查询代价](/learn/sql-indexes)

## 来源与版本 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
