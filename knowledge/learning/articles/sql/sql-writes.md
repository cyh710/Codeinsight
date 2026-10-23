# INSERT、UPDATE 与 DELETE

## 先建立直觉 {#overview}

SQL 不只查询，也能新增、修改和删除记录。写入会改变后续读者看到的数据，因此除了语法，还需要考虑条件、约束、事务与重试。尤其是 UPDATE 和 DELETE，忘记筛选条件可能影响整张表。

## 原理与执行过程 {#mechanism}

INSERT 建立新行，UPDATE 修改匹配行，DELETE 移除匹配行。约束可能拒绝写入，事务决定多步写入怎样共同提交。参数化查询把数据与 SQL 结构分开。发生网络超时时，客户端不能仅凭没有收到响应就判断写入没有发生。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```sql
-- PostgreSQL；在练习数据上执行
BEGIN;
INSERT INTO products (id, name, price) VALUES (3, '书包', 89.00);
UPDATE products SET price = 79.00 WHERE id = 3;
DELETE FROM products WHERE id = 3;
ROLLBACK;
```

## 一步一步读懂 {#walkthrough}

事务里先添加商品，再按主键修改价格，最后删除同一行。ROLLBACK 撤销尚未提交的修改，方便观察练习过程。真实保存时通常在确认全部步骤成功后 COMMIT。写入语句的影响行数有助于检查预期，例如应该更新一条却更新了零条。

## 常见误解 {#pitfalls}

只在界面隐藏删除按钮不能保护后端数据。字符串转义不应靠手写替换拼凑，优先使用驱动参数绑定。重复 INSERT 可能触发主键冲突，重复业务请求也可能造成两条不同 ID 的记录，需要单独设计幂等键。

## 工程中的取舍 {#tradeoffs}

批量写入可以减少往返，但一次失败影响的范围可能更大。软删除保留恢复空间，却增加查询过滤和唯一性设计复杂度。修改重要数据前应明确授权、备份和审计；事务不能自动撤回数据库外的网络副作用。

## 接着探索 {#related}

- [SELECT：查询、筛选与排序](/learn/sql-select)
- [事务：让多步数据库修改共同完成](/learn/sql-transactions)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
