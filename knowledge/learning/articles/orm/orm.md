# ORM：对象与关系数据之间的映射

## 一张留言表，两种写法 {#overview}

学完这一篇，你能看懂 ORM 把表映射成类、把行映射成对象的方式，认出循环里的 N+1 查询，并判断哪些查询该写回原生 SQL。

留言板里有两张表：`users` 存作者，`messages` 存留言，`messages.user_id` 指向作者。你想列出每条留言和它的作者名字。

用原生 SQL，一个 `JOIN` 就能拿到结果，Python 收到的是几行元组。表一多、对象一复杂，你会反复写同样的“从行里取字段、拼成对象”的代码；关系一多，还要决定什么时候加载关联数据。

ORM 把这些重复动作映射出来：一张表对应一个类，一行对应一个对象，一列对应一个属性。你操作对象，ORM 负责把操作翻译成 SQL，再把结果行装配回对象。

它没有把数据库藏起来。底层仍然执行 SQL，仍然有事务、索引、连接和约束。区别只是你在 Python 里表达这些事，而不是手写每一行 `SELECT` 和每一段装配代码。

## 先用 sqlite3 查一遍 {#raw-sql}

先在 `orm_demo.db` 里建表，塞进三个作者和五条留言。这段是纯 SQL，用 `sqlite3` 或 SQLite 命令行执行都可以：

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL
);

INSERT INTO users (id, name) VALUES
    (1, '小林'), (2, '阿宁'), (3, '老周');

INSERT INTO messages (id, user_id, body) VALUES
    (1, 1, '周末对账吗？'),
    (2, 2, '我先把账单整理好。'),
    (3, 1, '记得带上收据。'),
    (4, 3, '晚上七点见。'),
    (5, 2, '好的。');

SELECT u.name, m.body
FROM messages AS m
JOIN users AS u ON u.id = m.user_id
ORDER BY m.id;
```

查询结果：

```
小林: 周末对账吗？
阿宁: 我先把账单整理好。
小林: 记得带上收据。
老周: 晚上七点见。
阿宁: 好的。
```

`messages` 里没有作者名字，只有 `user_id`。`JOIN users AS u ON u.id = m.user_id` 把每条留言和对应的作者行接起来，`SELECT u.name, m.body` 只取你需要的两列。

完整脚本会用 Python 的 `sqlite3.connect` 执行这几句，提交后关闭连接，把数据库交给后面的 ORM。

这段 SQL 表达得很直接：要什么、从哪张表、怎么关联、按什么排序。代价是结果到了 Python 之后仍然是一行行元组。要让每条留言变成有 `body`、有 `user` 的对象，还得自己写循环装配。

## 表和类怎么对上 {#mapping}

先装 SQLAlchemy：

```bash
pip install "sqlalchemy>=2.0"
```

把上面的两张表写成类：

```python
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20))

    messages: Mapped[list["Message"]] = relationship(back_populates="user")

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(String(100))

    user: Mapped[User] = relationship(back_populates="messages")
```

对应关系可以摊成一张表：

| 数据库里的东西 | Python 里的东西 |
|---|---|
| 表 `users` | 类 `User` |
| `users` 的一行 | 一个 `User` 实例 |
| 列 `name` | 属性 `name` |
| `messages.user_id` | `Message.user_id` |
| 两张表的外键关系 | `Message.user` 与 `User.messages` |

`Base` 收集表定义。`__tablename__` 指定映射到哪张表。`Mapped[int]` 和 `mapped_column` 描述 Python 类型与数据库列的关系；`String(20)` 则把数据库列类型和长度说清楚。

`relationship` 不是一列。它告诉 ORM：拿到一个 `Message` 后，可以通过 `.user` 找到对应的 `User`；反过来，`User.messages` 是这个人的留言集合。外键仍然在 `user_id` 那一列上，关系只是导航方式。

定义类不会创建表。上面的表是原生 SQL 建的；类只是把已经存在的表映射出来。新项目可以用 `Base.metadata.create_all(engine)` 建表，但正式项目通常用迁移工具管理表结构，别把类定义当成迁移。

## Session 记着哪些改动 {#unit-of-work}

`Session` 是工作单元。它记住你新加了什么、改了哪些属性、删了什么，并在合适的时机把这些变化发成 SQL。

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

engine = create_engine("sqlite:///orm_demo.db")

with Session(engine) as session:
    message = Message(user_id=1, body="明天见")
    session.add(message)
    print(f"commit 前 id：{message.id}")

    session.commit()
    print(f"commit 后 id：{message.id}")

    message.body = "改成后天见"
    session.rollback()
    print(f"rollback 后 body：{session.get(Message, message.id).body}")
```

输出：

```
commit 前 id：None
commit 后 id：6
rollback 后 body：明天见
```

第一步，`Message(...)` 只是一个 Python 对象。`session.add` 把它放进待写入集合，还没有执行 `INSERT`，所以 `id` 是 `None`。

第二步，`commit` 先 flush，把待写入的 `INSERT` 发给数据库，数据库分配 `id=6`；然后结束事务。提交后对象属性默认会过期，下一次访问可能触发一条新的 `SELECT` 来刷新。

第三步，改 `body` 只是把对象标记为已修改。`rollback` 丢弃这个改动，`session.get` 重新从数据库取，读到的还是“明天见”。

`flush` 和 `commit` 不是一回事。flush 把 SQL 发出去，但事务还没结束；commit 会 flush，然后提交事务。flush 成功之后 commit 仍可能失败，那时要回滚。

离开 `with` 时 Session 会关闭。没有 `commit` 的改动不会保存。Session 也不是 Web 登录会话；它管的是数据库工作单元和对象状态。

## 循环里的 N+1 查询 {#n-plus-one}

把前面的东西合起来，下面这份脚本自己建库、跑原生查询、用 ORM 查询，再计数它到底发了几条 `SELECT`。

```python
from pathlib import Path
import sqlite3

from sqlalchemy import ForeignKey, String, create_engine, event, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    selectinload,
)

DB_PATH = Path("orm_demo.db")
DB_PATH.unlink(missing_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.executescript("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL
);

INSERT INTO users (id, name) VALUES
    (1, '小林'), (2, '阿宁'), (3, '老周');

INSERT INTO messages (id, user_id, body) VALUES
    (1, 1, '周末对账吗？'),
    (2, 2, '我先把账单整理好。'),
    (3, 1, '记得带上收据。'),
    (4, 3, '晚上七点见。'),
    (5, 2, '好的。');
""")
conn.commit()

rows = conn.execute("""
    SELECT u.name, m.body
    FROM messages AS m
    JOIN users AS u ON u.id = m.user_id
    ORDER BY m.id
""").fetchall()
for name, body in rows:
    print(f"{name}: {body}")
conn.close()

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20))
    messages: Mapped[list["Message"]] = relationship(back_populates="user")

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(String(100))
    user: Mapped[User] = relationship(back_populates="messages")

engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")

selects = []

@event.listens_for(engine, "before_cursor_execute")
def count_select(conn, cursor, statement, parameters, context, executemany):
    if statement.lstrip().upper().startswith("SELECT"):
        selects.append(statement)

with Session(engine) as session:
    message = session.get(Message, 1)
    print(f"\n按主键取一行：{message.body}")

def load_messages(eager):
    selects.clear()
    with Session(engine) as session:
        statement = select(Message).order_by(Message.id)
        if eager:
            statement = statement.options(selectinload(Message.user))
        messages = session.scalars(statement).all()
        for message in messages:
            print(f"{message.user.name}: {message.body}")
    return len(selects)

print("\n--- 普通查询：循环里访问 user ---")
print(f"SELECT 次数：{load_messages(eager=False)}")

print("\n--- 加上 selectinload ---")
print(f"SELECT 次数：{load_messages(eager=True)}")

print("\n--- Session 的提交与回滚 ---")
with Session(engine) as session:
    message = Message(user_id=1, body="明天见")
    session.add(message)
    print(f"commit 前 id：{message.id}")
    session.commit()
    print(f"commit 后 id：{message.id}")
    message.body = "改成后天见"
    session.rollback()
    print(f"rollback 后 body：{session.get(Message, message.id).body}")

engine.dispose()
```

运行 `python orm_demo.py`，你会看到：

```
小林: 周末对账吗？
阿宁: 我先把账单整理好。
小林: 记得带上收据。
老周: 晚上七点见。
阿宁: 好的。

按主键取一行：周末对账吗？

--- 普通查询：循环里访问 user ---
小林: 周末对账吗？
阿宁: 我先把账单整理好。
小林: 记得带上收据。
老周: 晚上七点见。
阿宁: 好的。
SELECT 次数：4

--- 加上 selectinload ---
小林: 周末对账吗？
阿宁: 我先把账单整理好。
小林: 记得带上收据。
老周: 晚上七点见。
阿宁: 好的。
SELECT 次数：2

--- Session 的提交与回滚 ---
commit 前 id：None
commit 后 id：6
rollback 后 body：明天见
```

关键在 `SELECT 次数：4`。

关系默认是懒加载：查留言时不会顺便查作者，直到你访问 `message.user`，ORM 才去数据库取这个作者。

第一次查询取出 5 条留言，用了 1 条 `SELECT`。进入循环后，每访问一个从没加载过的 `message.user`，ORM 就单独发一条 `SELECT` 去查作者。五条留言来自三个作者，Identity Map 会让同一个作者只查一次，所以是 1 + 3 = 4 条。

如果留言变成 100 条、作者有 50 个，普通写法大约会发 51 条查询。数据库每次查询都有网络往返，即使单条很快，几十次往返也会把接口拖慢。这就是 N+1：1 条主查询加上 N 条关联查询。

加上 `selectinload(Message.user)` 后，ORM 先查留言，再用一条 `SELECT ... WHERE id IN (...)` 把需要的作者一次取回，所以是 2 条。它不会在循环里临时查数据库。

`joinedload` 也能减少查询，但它会把留言和作者放在同一条 SQL 的 `JOIN` 里，父行可能重复，结果集更大。这里只有五条留言和三个作者，用哪种都不会差多少；数据量大时，要根据重复行和查询计划选。加载策略应该跟着查询走，不要在全模型上随便设一个全局懒加载开关。

## 五个容易踩的误会 {#pitfalls}

**“`session.add()` 之后数据库里就有这条了。”** 没有。`add` 只是把对象放进待写入集合，输出里的 `id` 还是 `None`。真正发 `INSERT` 通常发生在 flush 或 commit。更隐蔽的是，后面执行查询时 autoflush 可能提前把待写入内容发出去。

**“`commit` 和 `flush` 是一回事。”** 不是。flush 发送 SQL，事务仍然打开；commit 先 flush，再提交事务。flush 之后如果 commit 失败，数据仍然会回滚。调试时看到 SQL 已经执行，不等于已经持久化。

**“访问 `message.user` 只是读内存。”** 如果这个关系还没加载，ORM 会发查询。上面的 4 次 `SELECT` 就是这么来的。Session 关闭后再访问懒加载关系，还可能得到 `DetachedInstanceError`，因为对象已经不在可以发查询的上下文里。

**“模型类定义好，表就建好了。”** 模型只是映射。表要靠原生 SQL、`create_all` 或迁移工具创建。生产环境通常用 Alembic 这类迁移工具改表结构；直接 `create_all` 不会替你处理已有表的结构变更。

**“ORM 的 Session 就是用户登录会话。”** 不是。`Session` 是数据库工作单元，和 Cookie、登录 token 无关。它管理对象状态和事务；把它当成登录状态，容易在请求之间错误复用，或者在该关闭时一直不关闭。

## 什么时候直接写 SQL {#tradeoffs}

ORM 适合常规增删改查、简单关联和以对象为中心的代码。它把 `INSERT`、`UPDATE`、关联加载和事务边界包装起来，日常业务代码能少写很多重复装配。

下面这些情况，原生 SQL 往往更直接：

- 多表聚合报表、窗口函数、递归查询和数据库特有语法。
- 一次更新大量行，逐条对象更新既慢又占内存。
- 已经定位到热点的查询，需要看执行计划、强制索引或改写连接方式。
- 结果本来就不需要对象，只是一组统计数字。

SQLAlchemy 允许两者混用。`session.execute(text("..."), {"start": ...})` 仍然在同一个 Session 事务里执行，绑定参数也能避免把外部输入拼进 SQL。不要因为用了 ORM 就把所有查询都改写成对象遍历，也不要因为一条复杂 SQL 就绕开整个事务管理。

ORM 的代价是隐藏的查询和对象状态。读项目代码时，留意关系属性在哪里被访问、查询有没有加载选项、Session 的作用域有多长。打开 `echo=True` 或查询日志，看看一次请求实际发了几条 SQL，往往比猜更有效。

## 把 SQL 和对象对上 {#self-check}

**第 1 题**：五条留言来自三个作者，普通懒加载写法为什么是 4 条 `SELECT`，而不是 5 条或 6 条？

> **答案**
>
> 1 条查全部留言，然后每遇到一个尚未加载的作者发 1 条查询。三个不同作者各查一次，重复作者由 Identity Map 复用，所以是 1 + 3 = 4。
>
> 把访问作者的地方改成 `selectinload(Message.user)` 后，作者会由一条 `IN` 查询批量取回，总数变成 2。

**第 2 题**：`session.add(message)` 之后马上打印 `message.id`，为什么是 `None`？什么时候才会变成 6？

> **答案**
>
> `add` 只把对象放进 Session 的待写入集合，还没有执行 `INSERT`。数据库没有分配主键，所以 `id` 仍是 `None`。
>
> commit 触发 flush 后，`INSERT` 执行，SQLite 分配 `id=6`（前面已有 5 行），随后事务提交。

**第 3 题**：你定义了一个 `User` 模型，直接查询却得到“没有这张表”的错误。为什么？

> **答案**
>
> 模型类只是映射声明，不会自动创建表。表要由原生 SQL、迁移脚本或 `Base.metadata.create_all(engine)` 创建。
>
> 生产项目应优先用迁移工具管理表结构；`create_all` 适合本地试验，不负责修改已有表。

## 从 ORM 回到 SQL {#related}

- [JOIN：关联多张表](/learn/sql-joins)
- [数据库事务：一致完成状态转换](/learn/db-transaction)
- [连接池：复用连接并限制并发](/learn/connection-pool)
- [索引与查询代价](/learn/sql-indexes)

## ORM 的参考文档 {#sources}

- [SQLAlchemy ORM and Core](https://docs.sqlalchemy.org/en/20/intro.html)；作者：SQLAlchemy authors and contributors；MIT。版本：SQLAlchemy 2.0; sha256:db74e1fff59364aa035a0f11028c529ba04c3519dfe1cc9960cea4da6bda7c61。
