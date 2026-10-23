# 连接池：复用连接并限制并发

## 先建立直觉 {#overview}

数据库连接往往包含建立网络连接、认证和分配服务端资源等成本。连接池保存一组可复用连接，使用者借出连接完成工作后归还。它既是性能机制，也是限制数据库同时承受多少请求的一道容量边界。

## 原理与执行过程 {#mechanism}

连接池管理空闲、借出、失效与等待。归还前通常需要清理未完成事务，避免下一个使用者继承脏状态。池大小、额外溢出连接和等待超时共同影响并发与延迟。某些 SQLite 场景使用不同池策略，应依据库版本与数据库类型确认。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
from sqlalchemy import create_engine
engine = create_engine("sqlite:///demo.db")
with engine.connect() as connection:
    result = connection.exec_driver_sql("SELECT 1")
    print(result.scalar_one())
```

## 一步一步读懂 {#walkthrough}

engine 管理数据库访问与相应连接策略，connect 借出连接，离开 with 归还资源。这里的配置只用于演示接口，不承诺所有后端使用相同池实现。读真实项目要继续看 engine 创建参数、连接是否跨线程使用以及事务怎样结束。

## 常见误解 {#pitfalls}

池越大不一定越快，可能让数据库过载。连接对象常有线程或任务使用约束，不能随意共享。把连接还到池里不一定等于彻底关闭底层网络连接。连接池与 ORM Session 是不同抽象层。

## 工程中的取舍 {#tradeoffs}

复用降低建立成本，却增加生命周期和健康检查复杂度。短脚本可能无需复杂池配置，长期服务则需要关注等待、泄漏和数据库上限。应根据实际工作负载测量，而不是复制一个看起来很大的 pool_size。

## 接着探索 {#related}

- [ORM：对象与关系数据之间的映射](/learn/orm)
- [索引与查询代价](/learn/sql-indexes)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [SQLAlchemy ORM and Core](https://docs.sqlalchemy.org/en/20/intro.html)；作者：SQLAlchemy authors and contributors；MIT。版本：SQLAlchemy 2.0; sha256:db74e1fff59364aa035a0f11028c529ba04c3519dfe1cc9960cea4da6bda7c61。
