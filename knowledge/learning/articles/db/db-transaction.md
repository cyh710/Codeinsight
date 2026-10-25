# 数据库事务：一致完成状态转换

## 转账不能只改一半 {#half-transfer}

读完这一篇，你能画出一次转账的事务边界，用 sqlite3 演示回滚，并判断哪些失败可以重试、哪些不能。

小林给阿芳转 30 元。数据库里两条 UPDATE：小林减 30，阿芳加 30。第一条成功、第二条失败，30 元就从账上消失了。

事务把这两条绑成一个整体：要么都生效，要么都不生效。

它不负责判断余额够不够，也不负责解决所有并发问题。它只保证一件事：**提交边界内的修改，同生共死。**

## 跑一遍转账与回滚 {#rollback-demo}

新建 `transfer_demo.py`：

```python
import sqlite3

conn = sqlite3.connect(":memory:")
conn.executescript(
    """
    CREATE TABLE accounts (
        id      INTEGER PRIMARY KEY,
        name    TEXT    NOT NULL,
        balance INTEGER NOT NULL CHECK (balance >= 0)
    );
    INSERT INTO accounts (id, name, balance) VALUES (1, '小林', 100);
    INSERT INTO accounts (id, name, balance) VALUES (2, '阿芳', 20);
    """
)
conn.commit()


def show(label):
    rows = conn.execute("SELECT name, balance FROM accounts ORDER BY id").fetchall()
    print(label, ", ".join(f"{name}:{balance}" for name, balance in rows))


def transfer(src, dst, amount):
    conn.execute("BEGIN IMMEDIATE")
    try:
        balance = conn.execute(
            "SELECT balance FROM accounts WHERE id = ?", (src,)
        ).fetchone()[0]
        if balance < amount:
            raise ValueError("余额不足")
        conn.execute(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?", (amount, src)
        )
        changed = conn.execute(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?", (amount, dst)
        ).rowcount
        if changed != 1:
            raise ValueError("收款账户不存在")
        conn.commit()
        print(f"转账成功: {amount}")
    except Exception as exc:
        conn.rollback()
        print(f"转账失败: {exc}，已回滚")


show("开始:")
transfer(1, 2, 30)
show("成功一笔:")
transfer(2, 99, 10)
show("失败一笔:")
```

运行：

```bash
python transfer_demo.py
```

你应该看到：

```
开始: 小林:100, 阿芳:20
转账成功: 30
成功一笔: 小林:70, 阿芳:50
转账失败: 收款账户不存在，已回滚
失败一笔: 小林:70, 阿芳:50
```

建表和两条初始数据先 `commit` 了一次，它们不属于后面的转账事务。

第一笔转账里，`BEGIN IMMEDIATE` 开始事务，读出小林有 100，扣 30，给阿芳加 30，提交。两条 UPDATE 一起生效。

第二笔往账户 99 转 10。账户 99 不存在，但扣款那条先执行了：阿芳从 50 变成 40。接着加款那条影响 0 行，代码抛错，`rollback` 把阿芳的余额恢复到 50。所以"失败一笔"打印出来还是 `阿芳:50`。

`rowcount` 这个检查不能省。`UPDATE` 一个不存在的 id 不会报错，只会影响 0 行。如果不检查，代码会提交一笔没有收款方的扣款。

## 开始、提交与回滚各管什么 {#three-commands}

**`BEGIN` 划出起点。** 从这之后在同一连接上做的修改，都还在事务里，别的连接默认看不到。例子用 `BEGIN IMMEDIATE`，它在 SQLite 里表示"我现在就想要写权限"，冲突在开头就暴露。

**`COMMIT` 划出终点。** 事务里的修改一起生效，之后不能再回滚。例子把 `print("转账成功")` 放在 `commit` 之后，避免提交失败却先告诉用户成功。

**`ROLLBACK` 放弃这次事务。** 自 `BEGIN` 以来的修改全部丢弃，连接还能继续用。例子在 `except` 里回滚，然后把错误打印出来。

**边界该画在哪？** 画在一次完整业务状态转换的外面：转换前不变量成立，转换后不变量仍然成立。转账的不变量是"两个账户余额之和不变，且都不为负"。读余额、检查、扣款、加款都在这条边界内；发短信、调模型、生成报表不在这条边界内。

边界不能太小。把扣款和加款拆成两个事务，中间就有一次"钱只扣了没加"的可见状态；进程这时崩掉，钱就真的少了。

边界也不能太大。把不相关的写操作、甚至网络请求塞进同一个事务，会让锁持有更久，冲突更多，一次无关的失败还会把有用的修改一起回滚。

**`with conn:` 只负责提交或回滚已经打开的事务。** 代码块正常结束时提交，抛异常时回滚；但事务从哪一刻开始，仍然由语句或连接的设置决定。初学阶段显式写 `BEGIN`、`COMMIT`、`ROLLBACK`，更容易看清边界落在哪。

**`conn.close()` 不是提交。** 关闭连接时，未提交的修改通常会被回滚，但不要依赖"关连接"来管理边界：该提交的地方要显式提交，该回滚的地方要显式回滚。把关闭连接当成事务管理器，出错时很难判断究竟发生了什么。

**别随便嵌套 `BEGIN`。** SQLite 在已经开启的事务里再执行 `BEGIN` 会报错。需要部分回滚时用 `SAVEPOINT`，但那是另一个层次的工具；多数业务代码只要一个清晰的事务边界。

## 两个并发事务各自看见什么 {#concurrency-view}

| 时刻 | 事务 A（转账） | 事务 B（查余额） |
|---|---|---|
| A `BEGIN`，扣 30，未提交 | A 自己看到 70 | B 看到 100 |
| A `COMMIT` | 70 成为新状态 | 下一次读看到 70 |
| B 也想改同一行 | A 已结束 | 等待，或者超时报错 |

默认隔离下，未提交的修改别人看不见。B 在 A 提交前读到的是旧值，不是 70。不同数据库的隔离级别会改变一些细节，但"未提交不可见"是最常依赖的一条直觉。

两个事务写同一行，数据库必须排队。SQLite 同一时刻只允许一个写事务：第二个 `BEGIN IMMEDIATE` 会等，默认等 5 秒，等不到就报 `database is locked`。PostgreSQL 用行锁；两个事务互相等对方的锁时会出现死锁，数据库会牺牲其中一个。

**读-改-写仍然可能丢更新。** A、B 都读到 100，各自算出 70 再写回，结果只扣了一次。解决办法不是"套个事务"就完事：要么把检查和修改放进一条语句（`UPDATE accounts SET balance = balance - ? WHERE id = ? AND balance >= ?`，再看 `rowcount`），要么用 `SELECT ... FOR UPDATE` 锁住这一行。

例子里的 SQLite 因为 `BEGIN IMMEDIATE` 提前拿了写锁，两个写事务不会同时进来。换到别的数据库，不能假设这一点。

## 哪些失败值得重试 {#retry-rules}

| 失败 | 重试 | 原因 |
|---|---|---|
| 锁等待超时、`database is locked` | 是 | 竞争者释放后可能成功 |
| 死锁、`deadlock detected` | 是 | 数据库已经回滚其中一个事务，整笔重来 |
| 连接断开、网络抖动（未提交） | 是 | 重连后重来；先确认上次没有提交 |
| 余额不足 | 否 | 业务结果，重试不会变 |
| 唯一约束冲突 | 通常否 | 数据已存在或重复提交，用幂等键区分 |
| CHECK、外键约束失败 | 否 | 代码或数据有问题，重试只会再失败 |

重试要从 `BEGIN` 开始，不是只重跑末尾那条 `UPDATE`。失败的事务已经回滚，之前读到的值也可能已经变了。

重试要退避、加随机抖动、设上限。立刻重试会在锁竞争时火上浇油；无限重试会把一次局部故障拖成雪崩。

事务不保证幂等。客户端超时后重发"转账 30"，可能转两次。给每笔业务一个请求 id，在数据库里建唯一索引，让"同一笔只执行一次"成为约束。这比在应用层用 `if` 判断可靠得多。

提交成功但响应丢了，是最难的一种：客户端不知道到底成没成。幂等键让重试安全，查询接口让客户端能确认真实结果。

## 事务里不要放网络请求 {#no-network}

锁和连接都有成本。事务里等一次 2 秒的 HTTP 请求，别的写操作就跟着等 2 秒。

更麻烦的是，网络请求不能回滚。邮件发了、支付扣了、模型调了，数据库再 `ROLLBACK`，外面的世界不会跟着退回去。

下面这种写法迟早出事：

```
BEGIN
UPDATE orders SET status = 'paid'
调用支付网关
INSERT INTO payments ...
COMMIT
```

支付网关扣款成功，但后面的 `COMMIT` 失败，用户付了钱却没有订单。网关超时也一样难办：不知道到底扣没扣。

常规做法是把网络调用放到事务外：先算好、先调用，再开一个短事务写结果；或者只在一个事务里写"待发送"的 outbox 记录，提交后由后台任务发送，失败可重试。

外部接口本身要支持幂等（幂等键、请求号），否则重试会重复扣款。

事务范围小不是目的，短锁才是。余额检查、扣减、流水写入要在一起；发通知、调模型、生成大报表不要塞进来。

如果业务必须跨多个服务，本地事务已经不够用，需要补偿或 saga；那是另一个话题，但起点仍然是：先别把网络请求塞进本地事务。

## 在函数里不等于在事务里 {#db-misconceptions}

**"代码写在同一个函数里，就在同一个事务里。"** 事务属于连接。助手函数如果自己 `sqlite3.connect(...)` 或开了新的 ORM session，它就在另一个事务里，外层 `commit` 或 `rollback` 管不到它。把连接当参数传进去，或者在同一个 session 上操作。

**"事务会替我检查业务规则。"** 事务保证原子性，不保证"余额不能为负""一个订单只能付一次"。这些规则要写进代码或数据库约束。例子里的 `CHECK (balance >= 0)` 是兜底，前面的 `balance < amount` 才是业务判断。

**"ROLLBACK 能撤销一切。"** 只撤销当前连接上、`BEGIN` 之后的数据库修改。已经发出的邮件、扣过的款、写过的文件、内存里改过的变量，都不会回来。把副作用放到事务外，或者设计补偿。

**"COMMIT 返回就绝对不丢。"** 持久性取决于数据库配置和硬件。SQLite 的 `PRAGMA synchronous`、PostgreSQL 的 `synchronous_commit`、异步复制和故障切换，都会影响"提交后一定在磁盘上"的强度。默认配置通常够用，但别把它说成绝对保证；关键数据要知道部署的实际保证。

## 练习 {#self-check}

**第 1 题**：转账成功后要给用户发一封确认邮件。这封邮件应该放在 `BEGIN` 之前、事务中间，还是 `COMMIT` 之后？

> **答案**
>
> 放在 `COMMIT` 之后，或者只把"待发邮件"写进 outbox，提交后由后台任务发送。
>
> 放事务中间，一旦后面回滚，邮件已经发出去，用户收到了一个不存在的转账通知。邮件发不出去也不该让转账回滚，两者需要分开处理。

**第 2 题**：函数 A 开了一个连接，扣了款但还没提交；函数 B 开了另一个连接，加款时抛异常。B 的回滚会撤销 A 的扣款吗？

> **答案**
>
> 不会。事务属于连接，A 和 B 是两个独立事务。B 的回滚只管 B 的连接；A 的扣款仍然悬在 A 的事务里，可能随后被提交，也可能被回滚，取决于 A 怎么处理。
>
> 要保证原子性，必须让两条修改走同一个连接、同一个事务。把连接作为参数传给两个函数，是最直接的办法。

**第 3 题**：`database is locked` 和 `CHECK constraint failed`，哪个可以重试？

> **答案**
>
> `database is locked` 可以重试。它表示暂时拿不到锁，退避一段时间后整笔事务重来，可能成功。
>
> `CHECK constraint failed` 不该盲目重试。它表示数据违反了约束，重试同一份数据只会再失败一次。先检查输入、代码逻辑或并发修改，修好原因再执行。

## 继续阅读 {#related}

- [事务：让多步数据库修改共同完成](/learn/sql-transactions)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)
- [文件锁：协调对共享文件的访问](/learn/file-lock)
- [ORM：对象与表之间的映射](/learn/orm)

## 参考资料 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
