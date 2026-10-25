# JOIN：关联多张表

## 订单表里只有编号 {#ids-without-names}

学完这一篇，你能把订单、用户、商品按编号连起来查，知道 INNER JOIN 和 LEFT JOIN 各留下哪些行，也能看出关联条件写错后多出来的行。

接着上一节的 shop.db。小林要给订单打发货单，orders 表里存的是 `user_id` 和 `product_id`，没有名字。

两张表的结构是这样（已经建过的话，这里只是列出来对照）：

```sql
CREATE TABLE users (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE orders (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

商品表（同样只是结构对照）：

```sql
CREATE TABLE products (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    price REAL NOT NULL
);
```

进库，打开表头和空值显示：

```bash
sqlite3 shop.db
```

```
.headers on
.mode column
.nullvalue NULL
```

如果这两张表还没建，先跑下面这段补齐；已经按上一篇建过就跳过。`IF NOT EXISTS` 和 `OR IGNORE` 让它在重跑时不会插重：

```sql
CREATE TABLE IF NOT EXISTS users (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO users (id, name, email) VALUES
    (1, '小林', 'lin@example.com'),
    (2, '阿敏', 'min@example.com'),
    (3, '老周', 'zhou@example.com');

INSERT OR IGNORE INTO orders (id, user_id, product_id, quantity, created_at) VALUES
    (1, 1, 1, 2, '2026-10-01 10:00:00'),
    (2, 2, 2, 1, '2026-10-02 15:30:00');
```

PostgreSQL 里没有 `INSERT OR IGNORE`，对应写法是 `ON CONFLICT DO NOTHING`。

查一下订单：

```sql
SELECT id, user_id, product_id, quantity FROM orders ORDER BY id;
```

```
id  user_id  product_id  quantity
--  -------  ----------  --------
1   1        1           2
2   2        2           1
```

知道 1 号订单是 `user_id = 1` 下的，但发货单上要写“小林”，不是“1”。没有 JOIN 的做法是先拿编号，再回用户表挨个查：

```sql
SELECT name FROM users WHERE id = 1;
```

```
name
----
小林
```

```sql
SELECT name FROM users WHERE id = 2;
```

```
name
----
阿敏
```

两条订单查两次。一百条订单就在程序里查一百次，这叫 N+1 查询：先拿一次列表，再为每一行单独补查关联数据。JOIN 让数据库一次把两边对上。

## 把两张表按编号对上 {#inner-join}

```sql
SELECT o.id, u.name AS 用户, o.quantity, o.created_at
FROM orders AS o
JOIN users AS u ON u.id = o.user_id
ORDER BY o.id;
```

```
id  用户  quantity  created_at
--  ----  --------  -------------------
1   小林  2         2026-10-01 10:00:00
2   阿敏  1         2026-10-02 15:30:00
```

三处新东西：

- `orders AS o` 给表起别名。两张表都有 `id` 列，不写 `o.id` 就不知道取哪个。
- `ON u.id = o.user_id` 是配对条件：订单的 `user_id` 等于用户的 `id`，这两行才算一行结果。
- `JOIN` 默认就是 `INNER JOIN`，只保留配上的行。用户表里没有的 `user_id`，那笔订单不会出现在结果里。

`SELECT *` 在这里会返回两张表的全部列：两个 `id`，再加上 `name`、`email` 等等，读起来很乱。**关联查询里把需要的列写清楚。**

如果外键是开的，`orders.user_id` 不会指向不存在的用户，INNER JOIN 不会丢订单。外键没开时，孤儿订单会被 INNER JOIN 悄悄丢掉；用 LEFT JOIN 把没配上的那一边找出来，才能看到它们。

数据库执行这种等值连接时，通常是拿左表的每一行，去右表找 `id` 相等的行。`users.id` 是主键，这个查找是一次索引定位；连接列上没有索引时，就可能退化成一遍遍全表扫。结果对不对由 `ON` 决定，快不快还要看连接列有没有索引。

## 三张表连起来算小计 {#multi-table-join}

发货单还需要商品名和小计：

```sql
SELECT o.id, u.name AS 用户, p.name AS 商品,
       o.quantity, p.price AS 单价,
       o.quantity * p.price AS 小计
FROM orders AS o
JOIN users AS u ON u.id = o.user_id
JOIN products AS p ON p.id = o.product_id
ORDER BY o.id;
```

```
id  用户  商品    quantity  单价  小计
--  ----  ------  --------  ----  ----
1   小林  笔记本  2         12.0  24.0
2   阿敏  钢笔    1         35.0  35.0
```

两个 JOIN 串起来：先把订单和用户配上，再把结果和商品配上。每加一个 JOIN，都可能增加列，也可能增加行——如果一边匹配到多行，结果就会展开。

`o.quantity * p.price` 用的是商品表里的**当前**价格。商品一调价，历史订单的小计会跟着变。真实系统通常在订单行里存一个下单时的单价，这笔钱是多少就记多少，不再回头查商品表。

这里每张订单都配得上用户和商品，所以结果还是两行。如果哪一边缺失，INNER JOIN 会把整条订单丢掉；对账时看到金额少了，先查这类孤儿数据。

## 没下过单的用户 {#left-join}

想知道哪些用户一单没下，用 `LEFT JOIN`：

```sql
SELECT u.id, u.name, o.id AS order_id
FROM users AS u
LEFT JOIN orders AS o ON o.user_id = u.id
ORDER BY u.id;
```

```
id  name  order_id
--  ----  --------
1   小林  1
2   阿敏  2
3   老周  NULL
```

`LEFT JOIN` 保证左表（`users`）的每一行都留下。右表没有匹配时，右表的列填 `NULL`。老周没订单，所以 `order_id` 是 `NULL`。

换成 `INNER JOIN`，老周这一行直接消失，结果只剩两行。

要找的就是这些没配上的：

```sql
SELECT u.id, u.name
FROM users AS u
LEFT JOIN orders AS o ON o.user_id = u.id
WHERE o.id IS NULL;
```

```
id  name
--  ----
3   老周
```

判断空值用 `IS NULL`，不是 `= NULL`。`NULL = NULL` 的结果还是 `NULL`，不会留下任何行。

## 关联条件写错会多出几行 {#cartesian-product}

把两张表并排写，中间用逗号，不给条件：

```sql
SELECT COUNT(*) FROM orders, users;
```

```
COUNT(*)
--------
6
```

2 条订单，3 个用户，出来 6 行。看具体行：

```sql
SELECT o.id AS order_id, u.name AS 用户
FROM orders AS o, users AS u
ORDER BY o.id, u.id;
```

```
order_id  用户
--------  ----
1         小林
1         阿敏
1         老周
2         小林
2         阿敏
2         老周
```

每条订单和每个用户都配了一次。这就是笛卡尔积（叉积）：没有条件，所有行对都算匹配。

SQLite 里 `JOIN` 后面不写 `ON` 也会得到这个结果；在 PostgreSQL 里，`JOIN` 后面必须跟 `ON` 或 `USING`，要叉积得明写 `CROSS JOIN`。别依赖“能跑”来判断条件写没写对。

把条件补上，6 行立刻回到 2 行：

```sql
SELECT o.id AS order_id, u.name AS 用户
FROM orders AS o, users AS u
WHERE u.id = o.user_id
ORDER BY o.id;
```

```
order_id  用户
--------  ----
1         小林
2         阿敏
```

数据库做连接时，本质上是在找满足配对条件的行对。没有条件，所有行对都满足；条件写宽了，行数会成倍涨。1000 条订单乘 1000 个用户是一百万行，排序、聚合、分页都会跟着崩。JOIN 完先数一下行数，是个便宜的习惯。

## 四条容易想反的关联规则 {#join-pitfalls}

**“JOIN 不写 ON 也能跑，所以条件可有可无。”** 能跑不等于对。上面 2 × 3 变 6 就是后果。SQLite 容忍这种写法，PostgreSQL 直接报语法错误。写 JOIN 时先把 `ON` 写出来，再填条件；不确定就先 `COUNT(*)`。

**“LEFT JOIN 之后在 WHERE 里过滤右表，还是左连接。”** 不一定。条件放 `ON` 和放 `WHERE`，语义不同：

```sql
SELECT u.name, o.id AS order_id
FROM users AS u
LEFT JOIN orders AS o ON o.user_id = u.id AND o.product_id = 1
ORDER BY u.id;
```

```
name  order_id
----  --------
小林  1
阿敏  NULL
老周  NULL
```

条件写在 `ON` 里，只是“找订单时只认商品 1”；没找到的用户仍然保留，右表填 `NULL`。把同一个条件挪到 `WHERE`：

```sql
SELECT u.name, o.id AS order_id
FROM users AS u
LEFT JOIN orders AS o ON o.user_id = u.id
WHERE o.product_id = 1
ORDER BY u.id;
```

```
name  order_id
----  --------
小林  1
```

`WHERE` 在连接之后执行，`NULL = 1` 不为真，阿敏和老周都被筛掉。LEFT JOIN 实际上变成了 INNER JOIN。想让条件只影响“配哪一行”、不影响“左表留不留”，就写在 `ON` 里。

**“一对多 JOIN 出重复行，是数据库重复了。”** 不是。一个用户有三张订单，按用户 JOIN 就得到三行，这是关系展开的正常结果。要去重用户，用 `DISTINCT`；要统计，用 `GROUP BY`。直接对关联结果分页，很容易把同一个用户拆到两页。

**“ON 写错一定会报错。”** 经常不会，而且结果看起来还对：

```sql
SELECT o.id AS order_id, o.user_id, u.id AS uid, u.name
FROM orders AS o
JOIN users AS u ON u.id = o.id
ORDER BY o.id;
```

```
order_id  user_id  uid  name
--------  -------  ---  ----
1         1        1    小林
2         2        2    阿敏
```

这里订单 id 刚好和用户 id 相同，所以结果看着没错。如果 3 号订单是小林下的，`ON u.id = o.id` 会把发货人写成 3 号老周。**配对要用业务上的外键（`o.user_id`），不是两个碰巧同名的 id。**

## 什么时候不该把表拆开 {#join-tradeoffs}

拆表的好处是不重复：用户名字只在 users 里存一份，改一次就全对。代价是每次读都要 JOIN。反过来，把用户名直接抄进 orders，读起来快，但改名时要更新所有历史订单，漏一条就前后不一致。

订单里的单价是另一种情况：它不是“重复”，而是历史事实。商品表里的价格会变，订单里必须留下成交时的价格。这类冗余是该留的，它保的是对账，不是省一次 JOIN。

JOIN 的列要有索引。`users.id` 和 `products.id` 是主键，本来就有；`orders.user_id`、`orders.product_id` 是外键子列，SQLite 和 PostgreSQL 都不会自动建索引。订单多了以后，可以加：

```sql
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_product_id ON orders(product_id);
```

`orders` 现在只有两行，加了也看不出区别。判断方法是看数据量和 `EXPLAIN QUERY PLAN`，不是看语句里有没有 JOIN。

用 ORM 时也要留意生成出来的 SQL。取一批订单，再在循环里访问 `order.user.name`，很容易变成一条查询加 N 条关联查询，就是开头那个 N+1。要么在查询时把关联一起取出来，要么批量查一次再在内存里配对。

只想筛“有订单的用户”时，`EXISTS` 往往比 JOIN 更合适：它只判断有没有，不会把一对多的行展开，也就不会为了去重再套一层 `DISTINCT`。JOIN 适合“要把两边的列一起拿出来”，不是所有关联都得写成 JOIN。

## 三道关联题 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：列出所有用户和他们买过的商品名，没买过的用户也要出现。

> **答案**
>
> ```sql
> SELECT u.name AS 用户, p.name AS 商品
> FROM users AS u
> LEFT JOIN orders AS o ON o.user_id = u.id
> LEFT JOIN products AS p ON p.id = o.product_id
> ORDER BY u.id;
> ```
>
> ```
> 用户  商品
> ----  ------
> 小林  笔记本
> 阿敏  钢笔
> 老周  NULL
> ```
>
> 两个 LEFT JOIN 都从左边的用户出发，老周没有订单，商品名就是 `NULL`。

**第 2 题**：`orders` 有 2 行，`users` 有 3 行。`SELECT COUNT(*) FROM orders, users;` 返回几行？为什么？

> **答案**
>
> 6 行。逗号连接没有配对条件，每条订单和每个用户都组合一次，2 × 3 = 6。
>
> 加上 `WHERE users.id = orders.user_id` 才会回到 2 行。JOIN 里漏写 `ON`，后果一样。

**第 3 题**：`ON u.id = o.id` 在当前数据上跑出了看似正确的结果，为什么？什么情况下会露馅？

> **答案**
>
> 因为订单 1、2 的 id 刚好等于用户 1、2 的 id，配对碰巧对了。这个条件根本没有用到 `user_id`。
>
> 只要出现一笔订单，它的 id 和下单用户的 id 不同，就会配错。比如 3 号订单是小林（user_id = 1）下的，`o.id = 3` 会去找 3 号用户老周，发货人直接写错。正确的条件是 `ON u.id = o.user_id`。

## 关联之后的下一步 {#related}

- [主键、外键与数据约束](/learn/sql-constraints)
- [SELECT：查询、筛选与排序](/learn/sql-select)
- [聚合与 GROUP BY](/learn/sql-aggregate)
- [ORM：对象与关系数据之间的映射](/learn/orm)

## 关联查询的参考 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
