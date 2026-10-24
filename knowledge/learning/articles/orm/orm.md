# ORM：对象与关系数据之间的映射

## 先建立直觉 {#overview}

ORM 把数据库中的表和记录映射为程序中的类与对象，让部分数据操作用对象接口表达。它能减少重复 SQL 和对象装配代码，但底层仍然执行数据库查询，事务、索引和数据约束依然存在。

## 原理与执行过程 {#mechanism}

映射定义列、键和关系，Session 等工作单元跟踪对象状态并组织持久化。读取对象可能触发查询，访问关联也可能产生额外 SQL。flush 把变更发送到数据库，commit 提交事务；两者不能混为一谈。读 ORM 代码时，应同时理解对象行为和实际生成的 SQL。

## 跟着例子理解 {#example}

```python
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
class Base(DeclarativeBase):
    pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
```

## 一步一步读懂 {#walkthrough}

Base 提供声明映射的基础，User 对应 users 表。Mapped 描述 ORM 属性类型，mapped_column 指定数据库列。定义类并不意味着表已经创建、迁移已执行或数据已写入。后续还需要数据库引擎、会话和明确事务边界。

## 常见误解 {#pitfalls}

对象属性访问不一定是纯内存操作。N+1 查询往往来自循环里逐个读取关联。ORM 的类型声明也不代替外部输入校验。不能把会话 Session 与 Web 登录会话混为一谈。

## 工程中的取舍 {#tradeoffs}

ORM 提高常规 CRUD 的表达力，但复杂查询和性能分析仍要懂 SQL。原生 SQL 更直接，却需要手工维护映射与参数。可在同一工程中按职责混合使用，只要事务与连接边界清楚。

## 接着探索 {#related}

- [JOIN：关联多张表](/learn/sql-joins)
- [数据库事务：一致完成状态转换](/learn/db-transaction)
- [连接池：复用连接并限制并发](/learn/connection-pool)

## 来源与版本 {#sources}

- [SQLAlchemy ORM and Core](https://docs.sqlalchemy.org/en/20/intro.html)；作者：SQLAlchemy authors and contributors；MIT。版本：SQLAlchemy 2.0; sha256:db74e1fff59364aa035a0f11028c529ba04c3519dfe1cc9960cea4da6bda7c61。
