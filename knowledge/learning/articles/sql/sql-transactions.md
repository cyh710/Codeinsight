# 事务：让多步数据库修改共同完成

## 先建立直觉 {#overview}

事务把一组数据库操作组织为整体，成功后提交，失败时撤销尚未提交的修改。它适合维护多步操作之间的约束，例如领取队列任务时，同时创建执行记录并更新队列状态。先理解这些修改为什么必须配套，再理解事务语法。

## 原理与执行过程 {#mechanism}

事务常用原子性、一致性、隔离性和持久性说明。原子性避免只提交半组修改；隔离性约束并发交互；持久性受数据库与存储配置影响。一致性仍要求程序和约束正确表达业务规则。事务不能把错误逻辑自动变成正确逻辑，也不能自动撤销外部工具或网络操作。隔离级别与锁行为存在数据库差异，SQLite 的 BEGIN IMMEDIATE 与 PostgreSQL 普通 BEGIN 不应混为一谈。

## 跟着例子理解 {#example}

```sql
-- PostgreSQL；教学示例
BEGIN;
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
UPDATE accounts SET balance = balance + 10 WHERE id = 2;
COMMIT;
```

## 一步一步读懂 {#walkthrough}

两条 UPDATE 希望共同表达一次转移。事务使提交边界共同成立，但例子仍缺少余额检查、账户存在性、并发策略和金额类型约定，因此不能当成可直接上线的转账实现。若第二步发生异常，应由调用方按连接约定回滚，而不是继续报告成功。阅读项目时，要找到事务开始、所有参与操作、提交和失败路径。

## 常见误解 {#pitfalls}

with 出现在代码中不一定意味着事务自动提交，要确认上下文管理器的类型。数据库客户端超时也不等于数据库未提交。嵌套函数若另开连接，可能已经离开原事务。把“有事务”直接推导成“线程安全”或“任何故障都不丢数据”都过于宽泛。

## 工程中的取舍 {#tradeoffs}

短事务减少锁占用和冲突。把模型请求放进写事务可能长时间阻塞其他写者。跨系统操作往往需要幂等、执行账本与补偿，而不只是加 BEGIN。应依据实际故障模型测试回滚、并发和恢复。

## 接着探索 {#related}

- [INSERT、UPDATE 与 DELETE](/learn/sql-writes)
- [主键、外键与数据约束](/learn/sql-constraints)
- [数据库事务：一致完成状态转换](/learn/db-transaction)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)
- [文件锁：协调对共享文件的访问](/learn/file-lock)

## 来源与版本 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
