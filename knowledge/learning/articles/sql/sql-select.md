# SELECT：查询、筛选与排序

## 先建立直觉 {#overview}

SELECT 表达要从数据中得到什么结果。FROM 指定来源，WHERE 过滤记录，ORDER BY 指定顺序。把一句自然语言问题拆成“从哪里、保留哪些行、显示哪些列、怎样排序”，通常比记住整段语法更容易。

## 原理与执行过程 {#mechanism}

查询是声明式描述，数据库可以通过不同计划得到同样结果。理解 SQL 时可以按逻辑顺序思考来源、过滤、投影与排序，但真实执行方式由优化器决定。没有 ORDER BY 时，结果顺序不应被依赖。分页还需要稳定排序与明确的并发变化处理。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```sql
-- PostgreSQL；假设 products 已存在
SELECT name, price
FROM products
WHERE price < 50
ORDER BY price ASC, id ASC
LIMIT 5;
```

## 一步一步读懂 {#walkthrough}

先从 products 取候选行，再只保留价格小于 50 的商品。结果显示 name 和 price 两列，按价格升序；同价时按 id 排序，避免分页时顺序随意变化。最后最多返回 5 条。列出什么与按什么排序可以不同，具体可用表达式受查询结构与数据库规则影响。

## 常见误解 {#pitfalls}

WHERE name = NULL 通常不表达想要的空值判断，应使用 IS NULL。LIKE 的通配符与普通相等不同。把用户输入直接拼进查询字符串可能造成 SQL 注入，参数绑定应由数据库驱动负责。LIMIT 不是筛选条件的替代。

## 工程中的取舍 {#tradeoffs}

只选需要的列可减少传输和耦合。索引可能加速筛选排序，但不能只凭 WHERE 的存在就认定走了索引。性能结论需要实际数据、执行计划和测量。初学时先把查询结果手算出来，再讨论优化。

## 接着探索 {#related}

- [SQL 是什么：数据库、表、行与列](/learn/sql-database)
- [索引与查询代价](/learn/sql-indexes)
- [JOIN：关联多张表](/learn/sql-joins)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
