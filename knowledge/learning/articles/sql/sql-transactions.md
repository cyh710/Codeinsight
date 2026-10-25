# 事务：让多步数据库修改共同完成

## 一次下单要改两张表 {#two-writes}

学完这一篇，你能把扣库存和写订单放进同一个事务，中途失败时让两边的数据一起回到原样。

接着前面的 `shop.db`：`products`、`users`、`orders` 都在。三张表的结构如下，已经建过的不用重跑：

```sql
CREATE TABLE products (
    id     INTEGER PRIMARY KEY,
    name   TEXT    NOT NULL,
    price  REAL    NOT NULL
);

CREATE TABLE users (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    created_at  TEXT NOT NULL
);
```

一次下单要动两张表：往 `orders` 插一行，再把 `products.stock` 减掉买的件数。只做一件，后果都很具体。

订单写了、库存没扣，仅剩的一件会被卖两次。库存扣了、订单没写，货少了却查不到是谁买的。

两条写必须一起成立。这就是事务要解决的问题。

先给 `products` 加一列库存。`CHECK` 让库存不会被扣成负数：

```sql
ALTER TABLE products ADD COLUMN stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0);
```

这条 `ALTER` 只跑一次，重复跑会报 `duplicate column name: stock`。接着把四件商品的库存填上：

```sql
UPDATE products SET stock = 10 WHERE id = 1;
UPDATE products SET stock = 5  WHERE id = 2;
UPDATE products SET stock = 2  WHERE id = 3;
UPDATE products SET stock = 1  WHERE id = 4;

SELECT * FROM products;
```

你应该看到：

```
id  name    price  stock
--  ------  -----  -----
1   笔记本  12.0   10
2   钢笔    35.0   5
3   鼠标    89.0   2
4   键盘    199.0  1
```

`orders` 里还是前面那五条订单。现在多了库存这一列，下单就不只是往一张表里塞数据了。

## BEGIN 到 COMMIT：两条写绑成一组 {#commit-boundary}

先做一笔正常的下单：小林买两支钢笔。

```bash
sqlite3 shop.db
```

```text
.headers on
.mode column
```

```sql
BEGIN;

INSERT INTO orders (id, user_id, product_id, quantity, created_at)
VALUES (6, 1, 2, 2, '2025-02-01');

UPDATE products SET stock = stock - 2 WHERE id = 2;

SELECT stock FROM products WHERE id = 2;

COMMIT;

SELECT stock FROM products WHERE id = 2;
```

两条查询都会打印同一个数：

```
stock
-----
3
```

第一条 `SELECT` 在 `COMMIT` 之前，你看到 3，是因为这个事务自己已经改了库存。第二条在 `COMMIT` 之后，还是 3，因为改动已经正式生效。

差别不在数值，在别人能不能看到：提交之前，其他连接看不到这两条修改；提交之后，它们才能看到。

逐行拆开看：

- `BEGIN` 开启一个显式事务。在这之前，SQLite 默认每条语句自己提交；有了 `BEGIN`，后面的写先攒着。
- `INSERT` 写入 6 号订单，2 支钢笔。
- `UPDATE` 只改 `id = 2` 的钢笔，库存 5 变 3。
- 中间那条 `SELECT` 让你确认改动已经在事务里。
- `COMMIT` 是分界线：数据库把这一组修改变成正式状态，并让其他连接看到。

如果 `COMMIT` 之前程序崩了，数据库恢复时不会留下这两条半成品。这就是原子性：要么两条都生效，要么一条都不生效。

提交之后也不是"再也不能改"。以后你仍然可以开一个新事务，把库存改回去；那是另一次修改，不是撤销这一次。

`COMMIT` 之后，修改是否真的抗得住断电，还取决于数据库的持久化配置。SQLite 有 `synchronous`，PostgreSQL 有 `synchronous_commit`。默认配置通常足够认真对待，但别把"COMMIT 了"理解成"任何硬件故障都绝对不丢"。

## 中途失败时，ROLLBACK 把账抹平 {#rollback}

把顺序反过来：先扣库存，再写订单，但订单的数量写成 0。

```sql
BEGIN;

UPDATE products SET stock = stock - 1 WHERE id = 3;

SELECT stock FROM products WHERE id = 3;

INSERT INTO orders (id, user_id, product_id, quantity, created_at)
VALUES (7, 1, 3, 0, '2025-02-01');

SELECT stock FROM products WHERE id = 3;

ROLLBACK;

SELECT stock FROM products WHERE id = 3;

SELECT COUNT(*) AS 订单总数 FROM orders;
```

先查库存，鼠标从 2 变成了 1：

```
stock
-----
1
```

第二条 `INSERT` 被 `CHECK (quantity > 0)` 拒绝，你会看到类似这样的一行：

```
Runtime error near line ...: CHECK constraint failed: quantity > 0 (19)
```

这时再查一次，库存还是 1。刚才那条 `UPDATE` 没有消失，它还在事务里等着。

执行 `ROLLBACK` 之后再查：

```
stock
-----
2
```

库存回到了动手前的 2。订单总数是 6：前面五条，加上上一节提交的 6 号订单；7 号订单没有写进去。

这条失败路径说明了两件事。

第一，`ROLLBACK` 撤销的是当前事务里所有还没提交的修改。它不管你中间成功了几条，一起撤。

第二，SQLite 的命令行在语句失败后不会自动结束事务。报错了，前面那条 `UPDATE` 还挂着，必须有人执行 `ROLLBACK`。在 PostgreSQL 里行为不一样：语句一报错，整个事务进入 aborted 状态，后面的语句都不能执行，直到你 `ROLLBACK`，或者回滚到某个保存点。

所以"失败就回滚"不是数据库替你完成的动作，是你的代码要走的路径。捕获异常后继续 `COMMIT`，前面那条扣库存就被提交了，订单却没写成，账正好错在最不该错的地方。

## 只撤销一半：SAVEPOINT {#savepoint}

有些失败只该撤掉一小段。键盘只剩 1 件，先卖出一件，再试着卖第二件：

```sql
BEGIN;

INSERT INTO orders (id, user_id, product_id, quantity, created_at)
VALUES (8, 2, 4, 1, '2025-02-02');

UPDATE products SET stock = stock - 1 WHERE id = 4;

SAVEPOINT before_second;

INSERT INTO orders (id, user_id, product_id, quantity, created_at)
VALUES (9, 3, 4, 1, '2025-02-02');

UPDATE products SET stock = stock - 1 WHERE id = 4;

ROLLBACK TO before_second;

RELEASE SAVEPOINT before_second;

COMMIT;
```

第二次扣减会把键盘库存从 0 扣成 -1，被 `CHECK (stock >= 0)` 拒绝：

```
Runtime error near line ...: CHECK constraint failed: stock >= 0 (19)
```

执行 `ROLLBACK TO before_second` 之后，标记之后的语句被撤销：9 号订单没有了，那次失败的扣减也没有了。标记之前的 8 号订单和第一次扣减还在。提交之后查一下：

```sql
SELECT * FROM orders WHERE id >= 8;
```

```
id  user_id  product_id  quantity  created_at
--  -------  ----------  --------  ----------
8   2        4           1         2025-02-02
```

```sql
SELECT id, name, stock FROM products WHERE id = 4;
```

```
id  name  stock
--  ----  -----
4   键盘  0
```

9 号订单不存在，键盘库存是 0。第一笔生意成交，第二笔被挡住。

`SAVEPOINT` 在事务内部打一个标记。`ROLLBACK TO` 只撤销标记之后的语句，不会把整个事务扔掉。`RELEASE SAVEPOINT` 只是去掉这个标记，它不是提交；真正让修改生效的还是收尾的 `COMMIT`。

什么时候用？一个大事务里有可选步骤，失败只影响这一步，前面的工作还要保留。比如下单主流程成功，赠品加不上，只想撤掉赠品那一段。

如果失败意味着整个业务不成立，就别用保存点，直接 `ROLLBACK` 整个事务。

在 PostgreSQL 里，保存点还有一个实际用途：事务报错后进入 aborted 状态，`ROLLBACK TO` 一个保存点能把事务救回来，继续执行后面的语句。

## 两个事务同时跑，互相看见什么 {#isolation}

前面的例子都是一个事务单独跑。真实的商店同时有几个人下单。

假设键盘只剩 1 件，两个事务都想买：

| 时刻 | 事务 A | 事务 B |
|---|---|---|
| t1 | `BEGIN`，读到库存 1 | |
| t2 | | `BEGIN`，也读到库存 1 |
| t3 | 算出 0，写入库存 0，`COMMIT` | |
| t4 | | 算出 0，写入库存 0，`COMMIT` |

两笔订单都成立，库存只扣了一次。这就是"读出来、算一下、写回去"的经典问题：两个事务读到的都是旧值，后写的覆盖了先写的。

隔离级别回答的就是"同时发生时，彼此能看到什么"：

| 你关心的事 | READ COMMITTED（PostgreSQL 默认） | REPEATABLE READ |
|---|---|---|
| 别人没提交的修改 | 看不到 | 看不到 |
| 你同一事务里再查一次 | 可能看到别人刚提交的新值 | 还是第一次读到的快照 |
| 同时改同一行 | 后到的等前者结束，再基于最新值执行 | 可能直接报冲突，要重试 |

在 PostgreSQL 里，`READ UNCOMMITTED` 被当作 `READ COMMITTED` 处理。`SERIALIZABLE` 更强，冲突时更可能中止其中一个事务，应用要准备好重试。

SQLite 的并发模型更粗：同一时刻只允许一个写事务，写会拿锁，另一个写要等。默认的 `BEGIN` 是延迟取锁，真正开始写的时候才拿；想一开始就占住写锁，用：

```sql
BEGIN IMMEDIATE;
```

开完记得用 `COMMIT` 或 `ROLLBACK` 收尾。在 PostgreSQL 里没有 `BEGIN IMMEDIATE`，普通 `BEGIN` 就是普通开始。两边的锁行为不要混着理解。

隔离级别也不是万能的。上面那种"读到 1，算出 0，再写 0"的代码，在 `READ COMMITTED` 下仍然可能覆盖别人的修改。把判断写进 `UPDATE` 的条件里：

```sql
UPDATE products SET stock = stock - 1 WHERE id = 4 AND stock >= 1;
```

然后检查这条语句影响了几行。影响 1 行，说明抢到了；影响 0 行，说明库存已经不够。SQLite 可以用 `SELECT changes();` 看上一句改了几行；在 PostgreSQL 里，应用代码可以读 `rowcount`，或者用 `UPDATE ... RETURNING`。

另一种办法是用 `SELECT ... FOR UPDATE` 把那一行锁住再算。在 PostgreSQL 里可以用这个写法；SQLite 不支持，因为它一次只让一个事务写。

## 事务里不要放慢动作 {#short-transactions}

下面这种做法很常见，也很伤：

```text
BEGIN;
UPDATE products SET stock = stock - 1 WHERE id = 4;
调用支付接口，等 30 秒……
INSERT INTO orders ...;
COMMIT;
```

从 `UPDATE` 开始，事务就占着锁。支付接口等 30 秒，别的下单请求就要等 30 秒。接口超时、用户关掉页面、程序卡住，锁可能占得更久。

更糟的是，`ROLLBACK` 撤不回已经发生的事情。支付已经扣款、短信已经发出、邮件已经投递，数据库回滚不会把这些动作一起撤回。

所以把耗时动作挪到事务外面：

- 能提前取的数、能提前算的东西，在 `BEGIN` 之前做完。
- `BEGIN` 里只放必须一起成功的数据库写入。
- 提交之后再发通知、调 webhook。如果通知必须可靠，就在同一个事务里写一条"待发送"记录，提交后由后台任务去发，这就是 outbox 的思路。
- 等用户输入更不能放在事务里。用户想五分钟，锁就占五分钟。

跨系统的操作，加一个 `BEGIN` 也管不到另一个服务。那类问题要靠幂等键、执行记录和补偿，不是把事务写长。

## 四个容易踩空的地方 {#transaction-pitfalls}

**"语句报错，事务就自动回滚了。"** 不一定。SQLite 命令行里，失败的那条语句自己回滚，前面的修改还挂在事务里；在 PostgreSQL 里，事务会进入 aborted 状态，但也要你执行 `ROLLBACK` 才真正结束。代码里捕获异常后必须显式回滚，别默认数据库已经替你收尾。

**"再写一个 BEGIN 就是嵌套事务。"** SQLite 会直接拒绝：

```
Runtime error near line 2: cannot start a transaction within a transaction
```

第一个 `BEGIN` 仍然开着，记得 `ROLLBACK`。在 PostgreSQL 里，第二个 `BEGIN` 只给一条警告，不会开新事务。要在事务里做可回滚的小段，用 `SAVEPOINT`。

**"代码里用了 with，就一定提交或回滚了。"** 要看那个对象是什么。Python 的 `sqlite3` 连接在默认设置下当上下文管理器用时，成功提交、异常回滚，但它不会关闭连接；ORM 的 Session、连接池包装器、自定义上下文管理器各有各的规则。函数里另开一个连接，那个连接根本不在原事务里。

**"客户端超时，说明没写进去。"** 不一定。服务端可能已经 `COMMIT`，只是响应在网络上丢了。这时重试可能写第二遍。用业务幂等键（比如订单号）让重复请求落回同一行，或者先按业务键查一次，别凭"没收到回复"下结论。

## 三道上手题 {#self-check}

先自己写，再对照答案。库存接着前面的状态：鼠标 2 件、键盘 0 件。

**第 1 题**：用事务给用户 2 下一单鼠标，数量 1，提交后确认库存从 2 变成 1。

> **答案**
>
> ```sql
> BEGIN;
>
> INSERT INTO orders (id, user_id, product_id, quantity, created_at)
> VALUES (10, 2, 3, 1, '2025-03-01');
>
> UPDATE products SET stock = stock - 1 WHERE id = 3;
>
> COMMIT;
>
> SELECT stock FROM products WHERE id = 3;
> ```
>
> 结果是 1。`INSERT` 和 `UPDATE` 在同一个事务里，要么都成功，要么都撤销。

**第 2 题**：前面回滚示例里，执行 `ROLLBACK` 之前查库存是 1，之后是 2。这两个数字分别代表什么？

> **答案**
>
> 1 是"当前事务里已经改了，但还没提交"的值。只有这个事务自己看得到，其他连接看到的还是 2。
>
> 2 是回滚之后恢复的值。`ROLLBACK` 把事务里所有未提交的修改一起撤销，所以那条扣库存的 `UPDATE` 不算数了。

**第 3 题**：假设键盘只剩 1 件，两个事务同时下单。只把隔离级别调到 `REPEATABLE READ`，能不能保证不超卖？应该怎么写？

> **答案**
>
> 不能只靠隔离级别。隔离级别能决定对方看到什么、冲突时谁中止，但它不知道"库存够不够"。以 PostgreSQL 的 `REPEATABLE READ` 为例，后写的事务可能因为序列化冲突被中止；如果应用只会重试，却不在 `UPDATE` 里检查库存，重试后仍可能把库存扣成负数。
>
> 把库存条件放进 `UPDATE`：
>
> ```sql
> UPDATE products SET stock = stock - 1 WHERE id = 4 AND stock >= 1;
> ```
>
> 再检查影响行数。1 行表示扣减成功，0 行表示库存不够。也可以先用 `SELECT ... FOR UPDATE` 锁住那一行再算（在 PostgreSQL 里支持，SQLite 不支持）。

## 顺着事务读下去 {#related}

- [INSERT、UPDATE 与 DELETE](/learn/sql-writes)
- [主键、外键与数据约束](/learn/sql-constraints)
- [数据库事务：一致完成状态转换](/learn/db-transaction)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 引用的资料与版本 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
