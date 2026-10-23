# SQL 是什么：数据库、表、行与列

## 先建立直觉 {#overview}

SQL 是一种查询和管理数据的语言。数据库负责有组织地保存数据，SQL 则用来表达“我要查什么、增加什么、修改什么”。可以先把表想成一张有固定列的电子表格：每一行是一条记录，每一列描述一个属性；这种类比有助于入门，但数据库还会维护约束、并发与持久化。

## 原理与执行过程 {#mechanism}

假设商店需要保存商品名称与价格，可以建立商品表。商品 ID 用来稳定区分记录，名称用于展示，价格用于计算。SQL 描述的是需要的结果或数据变化，数据库负责选择执行方式。SQL 是语言；PostgreSQL、SQLite、MySQL 是不同数据库系统，它们支持相通的核心语法，也各有扩展与差异。

“表”和“文件”不在同一个抽象层：数据库内部也可能使用文件保存数据，但它向程序提供的是查询、约束和事务等能力。应用不必自己逐行扫描一个文本文件来处理所有问题。反过来，小而简单的数据也可能完全适合普通文件，不需要为了使用 SQL 而强行引入数据库。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```sql
-- 方言：PostgreSQL；独立教学数据
CREATE TABLE products (
    id integer PRIMARY KEY,
    name text NOT NULL,
    price numeric(10, 2) NOT NULL
);
INSERT INTO products VALUES (1, '笔记本', 12.00), (2, '钢笔', 35.00);
SELECT name, price FROM products WHERE price < 20;
```

## 一步一步读懂 {#walkthrough}

第一步，CREATE TABLE 定义 products 的结构，而不是立即创建商品。id 的主键约束要求它能稳定区分每一行；NOT NULL 表示相应字段必须有值。第二步，INSERT 加入两条教学记录。第三步，SELECT 选择要看的列，FROM 指定表，WHERE 只保留价格低于 20 的记录，得到笔记本与 12.00。

你可以先只理解最后一行，不必一次掌握建表。把条件改成 price >= 20，结果会换成钢笔；把列改成 name，就只返回名称。这个变化展示了 SQL 如何表达需求。真实项目中表名、字段、连接方式和权限必须从源码或数据库结构取证，不能把本例的 products 当成项目中一定存在的表。

## 常见误解 {#pitfalls}

数据库不是 SQL 的另一种叫法。结果看起来像表格，不代表它有默认顺序；需要稳定顺序时使用 ORDER BY。NULL 表示缺失或未知，不是空字符串或数字 0。示例采用 PostgreSQL 类型规则，不能直接据此断言 SQLite 会以完全相同方式约束价格精度。

## 工程中的取舍 {#tradeoffs}

关系型数据库适合需要结构化查询、约束和多条记录一致更新的数据。它也带来结构演进、索引维护、连接与备份成本。学习时先掌握表、查询和约束，再进入事务与索引；理解项目时先问它实际保存哪些数据，再追读写路径，而不是先背数据库术语。

## 接着探索 {#related}

- [SELECT：查询、筛选与排序](/learn/sql-select)
- [主键、外键与数据约束](/learn/sql-constraints)
- [事务：让多步数据库修改共同完成](/learn/sql-transactions)
- [URL、JSON 与 API 契约](/learn/web-api)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
