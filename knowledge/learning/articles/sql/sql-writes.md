# INSERT、UPDATE 与 DELETE

## 往表里加一条商品 {#insert-one-row}

学完这一篇，你能新增、修改、删除商品，并且在动手前先用查询确认目标行，避免一条漏写 WHERE 的语句改掉整张表。

接着上一节的 shop.db。小林进了一批货：台历、订书钉、笔筒，还有一块橡皮；台历的标价要改，笔筒要下架。

表结构没变（已经建好，这里只列出结构）：

```sql
CREATE TABLE products (
    id    INTEGER PRIMARY KEY,
    name  TEXT    NOT NULL,
    price REAL    NOT NULL
);
```

下面的新商品用 9 到 12 号。如果这些 id 已经有数据（重跑过这一篇），先删掉旧行或换一个没用过的号。

进库，打开表头和表格输出：

```bash
sqlite3 shop.db
```

```
.headers on
.mode column
```

先插一条台历：

```sql
INSERT INTO products (id, name, price) VALUES (9, '台历', 15.00);
```

命令行**什么也不打印**。写入成功时 sqlite3 不返回表格，沉默就是成功；只有报错才会打断你。

查一下确实进去了：

```sql
SELECT id, name, price FROM products WHERE id = 9;
```

```
id  name  price
--  ----  -----
9   台历  15.0
```

`INSERT INTO products (id, name, price)` 把列名写全了。不写列名也能跑：

```sql
INSERT INTO products VALUES (90, '试用品', 0.00);
DELETE FROM products WHERE id = 90;  -- 只是演示，不留这一行
```

但它要求值的顺序和表结构完全一致。以后给表加一列，这种老语句就会报“值的数量和列数不匹配”。写列名多打几个字，换来的是改表时不回头修旧代码。

`id` 也可以不写，SQLite 会拿当前最大的 `id` 加一。那个值可能被重用：删掉最大的一行之后，下一行又会拿到这个号。主键适合用来定位一行，不适合拿来当订单号或者时间顺序。

## 一次插入多行 {#insert-many-rows}

剩下的三件一起插：

```sql
INSERT INTO products (id, name, price) VALUES
    (10, '订书钉', 6.00),
    (11, '笔筒', 18.00),
    (12, '橡皮', 2.50);
```

查一下 9 到 12 号：

```sql
SELECT id, name, price FROM products WHERE id BETWEEN 9 AND 12 ORDER BY id;
```

```
id  name    price
--  ------  -----
9   台历    15.0
10  订书钉  6.0
11  笔筒    18.0
12  橡皮    2.5
```

一条语句插三行，少两次来回。**这三行是一条语句，要么全进，要么全不进。** 默认冲突策略下，中间任何一行违反约束，这条语句已经插入的部分也会撤回：

```sql
INSERT INTO products (id, name, price) VALUES
    (20, '试用品', 0.00),
    (1, '重复编号', 1.00);
```

```
Runtime error: UNIQUE constraint failed: products.id (19)
```

id 20 那行不会留下。查一下：

```sql
SELECT id, name FROM products WHERE id = 20;
```

没有输出。`(19)` 是 SQLite 的错误码 `SQLITE_CONSTRAINT`，前面的文字说明是哪个约束没过。在 PostgreSQL 里，多行 `INSERT` 同样是一条语句，失败也会整条回滚。

## 先查出来，再改和删 {#read-before-write}

改价格之前，先用 `SELECT` 把目标行看清楚：

```sql
SELECT id, name, price FROM products WHERE name = '台历';
```

```
id  name  price
--  ----  -----
9   台历  15.0
```

为什么不用 `WHERE name = '台历'` 直接改？因为名字不唯一。表里有两件叫“台历”的商品时，两条都会改。`id` 是主键，能唯一确定一行。

```sql
UPDATE products SET price = 12.50 WHERE id = 9 RETURNING id, name, price;
```

```
id  name  price
--  ----  -----
9   台历  12.5
```

`RETURNING` 把改完的行直接交回来。SQLite 3.35 起支持，PostgreSQL 也支持；版本更老时，改完再查一次。

想知道影响了几行：

```sql
SELECT changes();
```

```
changes()
---------
1
```

`changes()` 是 SQLite 的函数，返回上一条语句写入的行数。PostgreSQL 在驱动里拿 rowcount，或者用 `RETURNING` 把行拿回来。

如果条件是 `WHERE id = 999`，没有这一行，语句不报错，但 `changes()` 会是 0：

```sql
UPDATE products SET price = 99.00 WHERE id = 999;
SELECT changes();
```

```
changes()
---------
0
```

**没有报错不等于改成功了。** 写完看一下影响行数，或者用 `RETURNING` 确认拿回了预期的行。

删除也一样，先查：

```sql
SELECT id, name, price FROM products WHERE id = 11;
```

```
id  name  price
--  ----  -----
11  笔筒  18.0
```

确认是笔筒，再删：

```sql
DELETE FROM products WHERE id = 11 RETURNING id, name, price;
```

```
id  name  price
--  ----  -----
11  笔筒  18.0
```

`SELECT changes();` 回 1。再查 id 11，没有输出，行没了。

`DELETE FROM products;` 会删掉整张表的所有行，表结构还在；`DROP TABLE products;` 连表一起删。两个都没有“确认”提示。

## 漏写 WHERE 会改掉整张表 {#missing-where}

小林想给台历打个折，手一快写成了 `UPDATE products SET price = price * 0.8;`，没有 `WHERE`。这条语句会把表里所有商品全部打八折，执行完就提交，没有撤销按钮。真实数据上，这种错误只能靠备份恢复。

所以不熟悉的写入，先放在事务里试：

```sql
BEGIN;
UPDATE products SET price = price * 2;
SELECT id, name, price FROM products WHERE id IN (1, 9);
```

```
id  name    price
--  ------  -----
1   笔记本  24.0
9   台历    25.0
```

整张表都翻倍了。确认看到的是你不想要的结果，撤回：

```sql
ROLLBACK;
SELECT id, name, price FROM products WHERE id IN (1, 9);
```

```
id  name    price
--  ------  -----
1   笔记本  12.0
9   台历    12.5
```

`BEGIN` 之后的修改只在当前连接里可见，`ROLLBACK` 把它们全部丢掉，`COMMIT` 才真正写进去。事务不是“撤销按钮”，它只是把提交推迟到你检查完的那一刻。你先 `COMMIT` 了，再想撤回就晚了。

安全改一条数据的顺序是：

```sql
BEGIN;
SELECT id, name, price FROM products WHERE id = 9;
UPDATE products SET price = 13.00 WHERE id = 9;
SELECT changes();
COMMIT;
```

中间任何一步发现不对，把 `COMMIT` 换成 `ROLLBACK;`。如果客户端断开连接，未提交的事务通常会被回滚；不同驱动的行为要查文档，别把它当保证。

## 写入时数据库在做什么 {#write-mechanism}

一条 `INSERT` 进来，数据库先解析语句，确认表和列存在，再逐行检查约束：主键或 `UNIQUE` 有没有冲突、`NOT NULL` 的列有没有值、`CHECK` 表达式是不是真、外键指向的父行在不在（SQLite 要先打开外键检查）。全部通过才写进去。

任何一条约束没过，当前语句中止。默认策略下，这条语句已经改掉的行会撤回；前面已经提交的语句不受影响。多行 `INSERT` 之所以“要么全进要么全不进”，就是这条规则在起作用。

`BEGIN` 把几条语句包成一个事务。`COMMIT` 之前，其他连接看不到你的修改（SQLite 靠锁，PostgreSQL 靠 MVCC）；`ROLLBACK` 之后，什么都没发生。事务是多个写入保持一致的边界，不是性能开关。

写入返回后，客户端通常还能拿到受影响的行数。SQLite 是 `changes()`，PostgreSQL 是驱动的 rowcount，或者用 `RETURNING`。**一个应该改一行的语句改成了零行，往往说明 `WHERE` 条件写错了，不是“没有变化所以成功”。**

网络超时是另一回事。客户端没收到响应，不代表服务端没提交；这时候盲目重试一条普通 `INSERT`，可能插出两条。给业务键加唯一约束，再用幂等写入：

```sql
INSERT INTO products (id, name, price) VALUES (9, '台历', 12.50)
ON CONFLICT (id) DO NOTHING;
```

已经有 9 号就什么也不做，没有才插入。SQLite 3.24 起支持，PostgreSQL 9.5 起支持，两边语法接近。要“有则更新”，把 `DO NOTHING` 换成 `DO UPDATE SET ...`。

## 四个写坏的场景 {#write-pitfalls}

**“界面上没有删除按钮，普通用户就删不了。”** 界面只是入口。用户可以直接调接口、连数据库、改请求。权限检查要放在服务端，数据库账号也不要给应用 `DROP` 或 `TRUNCATE` 的权限。

**“UPDATE 忘写 WHERE，改回来就行。”** 改回来需要知道原来的值。整表更新会覆盖所有行，某些行还可能撞上唯一约束，导致语句中途失败。用事务、备份和 `changes()` 兜底；批量更新前先 `SELECT` 出目标行。

**“重复提交一次 INSERT，最多多一条记录。”** 可能撞主键报错：

```sql
INSERT INTO products (id, name, price) VALUES (9, '台历', 12.50);
```

```
Runtime error: UNIQUE constraint failed: products.id (19)
```

也可能因为主键是自动生成的，插出两条内容一模一样的业务记录。给业务键加唯一约束，或者用幂等键加 upsert。

**“把用户输入里的引号转义一下，就能拼 SQL。”** 转义规则不止引号，还有反斜杠、注释符、编码。用参数绑定：

```python
cur.execute(
    "UPDATE products SET price = ? WHERE id = ?",
    (new_price, product_id),
)
```

psycopg 用 `%s`，SQLite 用 `?`；占位符写法看驱动，原则一样：SQL 结构固定，值单独传。

## 批量、软删除与备份 {#write-tradeoffs}

批量插入把多条 `INSERT` 合成一条，减少客户端和数据库之间的来回。代价是一次失败影响的范围更大，锁也持得更久。实际做法是分块，块多大取决于你的重试成本和能容忍的锁时间；没有放之四海皆准的数字。

删除有两条路。硬删除直接 `DELETE`，查询简单，但删错了只能靠备份。软删除加一列 `deleted_at`，行还在，查询要处处加 `WHERE deleted_at IS NULL`；漏一处，用户就会看到已删除的商品。

软删除还会和唯一约束打架。比如邮箱 `UNIQUE`，用户注销后那条记录还在，新用户就不能用同一个邮箱。解决办法是建一个只约束未删除行的部分唯一索引，索引条件写成 `WHERE deleted_at IS NULL`。SQLite 和 PostgreSQL 都支持部分索引，前提是表里先有 `deleted_at` 列。

改重要数据之前，备份、权限、审计三件事比语法更重要。应用账号只给需要的权限；批量更新先在副本上跑；改完留下谁在什么时候改了什么。事务能撤回数据库里的语句，撤不回已经发出去的邮件、已经扣掉的款。

## 三道写入题 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：插入一件 `id = 13`、名字“尺子”、价格 4.50 的商品，然后只改它的价格到 5.00，并让语句返回修改后的行。

> **答案**
>
> ```sql
> INSERT INTO products (id, name, price) VALUES (13, '尺子', 4.50);
> UPDATE products SET price = 5.00 WHERE id = 13 RETURNING id, name, price;
> ```
>
> ```
> id  name  price
> --  ----  -----
> 13  尺子  5.0
> ```
>
> 先确认插入成功，再按主键改。`RETURNING` 让你直接看到改后的值。

**第 2 题**：你不小心执行了 `DELETE FROM products;`，之前没有 `BEGIN`。现在 `ROLLBACK;` 能救回来吗？

> **答案**
>
> 不能。没有显式事务时，每条语句自己就是一个事务，删完就已经提交了。`ROLLBACK` 只对当前打开的事务有效。
>
> 这就是为什么危险操作要先 `BEGIN`，或者先备份。

**第 3 题**：写一段安全改价的流程，把 id 为 12 的商品价格改成 3.00，要求先确认目标行、再修改、确认无误后提交；发现不对时能撤回。

> **答案**
>
> ```sql
> BEGIN;
> SELECT id, name, price FROM products WHERE id = 12;
> UPDATE products SET price = 3.00 WHERE id = 12;
> SELECT changes();
> COMMIT;
> ```
>
> 如果 `SELECT` 或 `changes()` 的结果不对，执行 `ROLLBACK;` 代替 `COMMIT;`，修改全部丢弃。

## 写完之后读什么 {#related}

- [SELECT：查询、筛选与排序](/learn/sql-select)
- [事务：让多步数据库修改共同完成](/learn/sql-transactions)
- [主键、外键与数据约束](/learn/sql-constraints)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 写入语句的参考 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
