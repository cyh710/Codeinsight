# 数据库事务：一致完成状态转换

## 先建立直觉 {#overview}

事务把相关数据库修改放在共同提交边界内。工程中它常用于维护跨记录不变量，例如领取输入时必须同时建立执行轮、更新会话指针并记录事件。需要先识别这些状态之间的关系，才能判断事务范围是否正确。

## 原理与执行过程 {#mechanism}

一个事务可能包含读取、条件检查和多次写入。数据库控制原子提交与并发交互，程序负责正确表达业务约束。不同连接、不同数据库或外部请求不会因为代码在同一个函数里就自动加入同一事务。SQLite 的 BEGIN IMMEDIATE 提前争取写事务资格，但仍需要处理忙等待和失败。

## 跟着例子理解 {#example}

```python
from contextlib import closing
import sqlite3

with closing(sqlite3.connect(":memory:")) as conn:
    conn.execute("CREATE TABLE queue (id INTEGER PRIMARY KEY, state TEXT)")
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO queue VALUES (1, 'running')")
    conn.commit()
```

## 一步一步读懂 {#walkthrough}

教学库先建表并提交，再显式开始一个写事务。INSERT 与随后 commit 属于这一事务。closing 负责关闭连接，并不是提交管理器；若提交前发生异常，未提交修改会在该连接关闭时回滚。分析项目应追同一连接上的 BEGIN 和 commit，而不是单凭出现 execute 就认定事务。

## 常见误解 {#pitfalls}

持久性受同步策略与故障类型影响。事务不自动保证任何业务规则，也不能撤销已经执行的外部工具。调用另一个函数若偷偷新建连接，可能打破预想的原子边界。仅看顺序执行不能证明并发正确性。

## 工程中的取舍 {#tradeoffs}

短事务减少锁占用。过小范围可能暴露中间状态，过大范围会阻塞其他操作并增加冲突。把耗时模型请求移出写事务通常有利于并发，但必须先可靠记录执行归属，并为恢复与重试定义边界。

## 接着探索 {#related}

- [事务：让多步数据库修改共同完成](/learn/sql-transactions)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)
- [文件锁：协调对共享文件的访问](/learn/file-lock)

## 来源与版本 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
