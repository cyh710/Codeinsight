# 主键、外键与数据约束

## 先建立直觉 {#overview}

约束把部分数据规则交给数据库维护。主键稳定区分记录，外键要求关联对象存在，唯一约束防止某种重复，NOT NULL 防止必填字段缺失。它们补充程序检查，使其他写入路径也必须遵守相同规则。

## 原理与执行过程 {#mechanism}

主键可以由一列或多列组成。外键关联目标键，删除或修改目标时需要明确策略。CHECK 表达行级条件，但复杂跨行规则未必能直接放进去。SQL 对 NULL 和唯一性有具体规则，不同数据库或配置可能有差异。约束描述规则，索引常用于高效维护和查询，两者用途不完全相同。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```sql
-- PostgreSQL
CREATE TABLE users (id integer PRIMARY KEY, name text NOT NULL);
CREATE TABLE messages (
  id integer PRIMARY KEY,
  user_id integer REFERENCES users(id),
  text text NOT NULL,
  CHECK (length(text) > 0)
);
```

## 一步一步读懂 {#walkthrough}

users.id 区分用户，messages.user_id 指向用户。正文既不允许 NULL，也不允许长度为 0，两条规则缺一不可。若 user_id 没有 NOT NULL，缺失关联仍可能被允许；外键不是自动必填。删除用户时消息怎样处理，应在业务约定和外键策略中明确。

## 常见误解 {#pitfalls}

只在插入前 SELECT 检查重复，仍可能遭遇并发竞争，应有适当数据库约束。自增 ID 不等于全局业务顺序。外键存在不代表所有数据库连接都按预期启用了相关检查，例如 SQLite 需要核对连接配置。

## 工程中的取舍 {#tradeoffs}

强约束减少无效状态，但会影响迁移与历史数据导入。级联删除方便却可能扩大误删范围，限制删除更安全但需要清晰错误。设计数据模型时，应先描述实体关系与生命周期，再选择约束组合。

## 接着探索 {#related}

- [SQL 是什么：数据库、表、行与列](/learn/sql-database)
- [JOIN：关联多张表](/learn/sql-joins)
- [事务：让多步数据库修改共同完成](/learn/sql-transactions)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
