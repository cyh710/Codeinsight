# 聚合与 GROUP BY

## 先把订单摆到桌上 {#order-table}

学完这一篇，你能用 COUNT、SUM 等函数把整表订单压成几个数，再按用户分组算出每个人花了多少。

接着前面的 `shop.db`：`products` 已经有了，`users` 和 `orders` 也建好了。三张表的结构再列一遍，已经建过的不用重跑：

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

四件商品是：1 号笔记本 12 元、2 号钢笔 35 元、3 号鼠标 89 元、4 号键盘 199 元。后两件如果还没插，补一下：

```sql
INSERT INTO products (id, name, price) VALUES (3, '鼠标', 89.00);
INSERT INTO products (id, name, price) VALUES (4, '键盘', 199.00);
```

四个用户和五条订单也放进去。已经有的行跳过，主键会拒绝重复：

```sql
INSERT INTO users (id, name, email) VALUES
  (1, '小林', 'lin@example.com'),
  (2, '阿蓝', 'lan@example.com'),
  (3, '老周', 'zhou@example.com'),
  (4, '小满', 'man@example.com');

INSERT INTO orders (id, user_id, product_id, quantity, created_at) VALUES
  (1, 1, 1, 2, '2024-03-02'),
  (2, 1, 3, 1, '2024-03-05'),
  (3, 2, 2, 3, '2024-04-11'),
  (4, 2, 1, 1, '2024-05-20'),
  (5, 3, 4, 1, '2025-01-08');
```

打开数据库，顺手把表头和表格模式打开，后面的输出都按这个格式显示：

```bash
sqlite3 shop.db
```

```text
.headers on
.mode column
```

查一眼订单：

```sql
SELECT * FROM orders;
```

你应该看到五行：

```
id  user_id  product_id  quantity  created_at
--  -------  ----------  --------  ----------
1   1        1           2         2024-03-02
2   1        3           1         2024-03-05
3   2        2           3         2024-04-11
4   2        1           1         2024-05-20
5   3        4           1         2025-01-08
```

五条订单、四个用户，足够看出聚合在做什么。

## 五个函数把五行压成一行 {#five-functions}

先算一笔总账：一共几单、卖了几件、收了多少钱、最便宜和最贵的一单各是多少。

```sql
SELECT
    COUNT(*)              AS 订单数,
    SUM(quantity)         AS 商品件数,
    SUM(quantity * price) AS 总金额,
    AVG(quantity * price) AS 平均每单,
    MIN(quantity * price) AS 最小单,
    MAX(quantity * price) AS 最大单
FROM orders
JOIN products ON products.id = orders.product_id;
```

你应该看到一行：

```
订单数  商品件数  总金额  平均每单  最小单  最大单
------  --------  ------  --------  ------  ------
5       8         429.0   85.8      12.0    199.0
```

这条查询分三步走通。

第一步，`JOIN products` 把每条订单和它对应的商品接上，这样 `price` 才能参与计算。一条订单只对应一件商品，所以接完还是五行，没有变多。

第二步，`quantity * price` 在每一行上各算一次：24、89、105、12、199。`SUM` 把这五个数加起来，得到 429。

第三步，五个聚合函数各给出一个值，整张表被压成了一行。`COUNT(*)` 数行，`SUM(quantity)` 数件数，`AVG` 是总和除以行数，`MIN` 和 `MAX` 找两头。

聚合的结果里不再有"哪一单"的信息。这一行回答的是"总共多少"，不是"具体是哪几单"。

## 按 user_id 分组，把名字接回来 {#group-by-user}

整表一个总数不够用。老板更常问的是：每个人花了多少？

```sql
SELECT
    user_id,
    COUNT(*)              AS 订单数,
    SUM(quantity)         AS 件数,
    SUM(quantity * price) AS 总金额
FROM orders
JOIN products ON products.id = orders.product_id
GROUP BY user_id
ORDER BY 总金额 DESC;
```

输出：

```
user_id  订单数  件数  总金额
-------  ------  ----  ------
3        1       1     199.0
2        2       4     117.0
1        2       3     113.0
```

`GROUP BY user_id` 把五行分成三组：1 号两组订单、2 号两组、3 号一组。聚合函数在组内计算，不是整表计算。所以结果从"一整行"变成了"每组一行"。

4 号用户小满没有订单，`orders` 里根本没有他的行，也就不会出现。想让没下单的人也显示成 0，要用 `LEFT JOIN`，后面讲 `COUNT` 时会看到写法。

`ORDER BY 总金额` 用的是结果列的别名。SQLite 和 PostgreSQL 都允许在 `ORDER BY` 里引用这种别名，写起来比重复一遍 `SUM(...)` 省事。

光有 `user_id` 不好读。把 `users` 接进来：

```sql
SELECT
    users.name,
    COUNT(*) AS 订单数,
    SUM(orders.quantity * products.price) AS 总金额
FROM orders
JOIN products ON products.id = orders.product_id
JOIN users    ON users.id    = orders.user_id
GROUP BY users.id, users.name
ORDER BY 总金额 DESC;
```

```
name  订单数  总金额
----  ------  ------
老周  1       199.0
阿蓝  2       117.0
小林  2       113.0
```

`GROUP BY` 里写了 `users.id, users.name` 两列。`id` 已经能唯一确定一个人；把 `name` 也写进去，`SELECT` 里没有聚合的列就都出现在 `GROUP BY` 里，两个数据库都不会挑毛病。SQLite 本身更宽松，没写进 `GROUP BY` 的列它也可能放行；宽松不等于更安全。

`JOIN` 在逻辑上先于分组发生：数据库先把订单接上商品和用户，形成一张带名字的宽表，再按 `user_id` 分组。你写的时候可以按"先分组、再接名字"思考，但别指望数据库真的先分组再去找名字。

## WHERE 筛行，HAVING 筛组 {#where-vs-having}

现在加两个条件：只看 2024 年的订单，并且只留下总金额超过 115 元的用户。

```sql
SELECT
    user_id,
    COUNT(*)              AS 订单数,
    SUM(quantity * price) AS 总金额
FROM orders
JOIN products ON products.id = orders.product_id
WHERE created_at >= '2024-01-01'
  AND created_at <  '2025-01-01'
GROUP BY user_id
HAVING SUM(quantity * price) > 115
ORDER BY 总金额 DESC;
```

输出只剩一组：

```
user_id  订单数  总金额
-------  ------  ------
2        2       117.0
```

这里有两个过滤条件，位置不能互换。

`WHERE` 在分组之前执行，它只看单行。老周的订单日期是 `2025-01-08`，被 `WHERE` 拿掉，所以他连一个组都形不成。

`HAVING` 在分组之后执行，它看的是整组。小林的两条订单都在 2024 年，组存在，总金额 113 元，没过 `HAVING` 的 115 元线，被丢掉。

按 SQL 的逻辑顺序，可以列成这张表：

| 阶段 | 处理的对象 | 能不能用 COUNT、SUM |
|---|---|---|
| `WHERE` | 一行一行 | 不能 |
| `GROUP BY` | 把行分进组 | 不能写聚合函数 |
| 聚合函数 | 每个组算出一个值 | 在这里算 |
| `HAVING` | 一组一组 | 能 |

`created_at` 存成 `YYYY-MM-DD` 的文本，字符串比较的结果和日期比较一致，所以 `>= '2024-01-01'` 能直接筛年份。在 PostgreSQL 里，这一列通常用 `DATE` 或 `TIMESTAMPTZ`，写 `'2024-01-01'` 会被转成日期再比较。

`WHERE` 里写 `SUM(...) > 100` 会直接报错，因为那时还没有组；这种条件只能放进 `HAVING`。

## COUNT(*) 和 COUNT(列) 数到的不是一回事 {#count-null}

想知道每个用户下了几单，包括一单都没下的人：

```sql
SELECT
    users.name,
    COUNT(*)          AS 行数,
    COUNT(orders.id)  AS 订单数
FROM users
LEFT JOIN orders ON orders.user_id = users.id
GROUP BY users.id, users.name
ORDER BY users.id;
```

```
name  行数  订单数
----  ----  ------
小林  2     2
阿蓝  2     2
老周  1     1
小满  1     0
```

小满那一行是关键。`LEFT JOIN` 保证他出现在结果里，但 `orders` 那边没有匹配的行，所有订单列都是 `NULL`。

`COUNT(*)` 数的是结果行，小满占了一行，所以是 1。

`COUNT(orders.id)` 数的是这一列里有值的行。小满的 `orders.id` 是 `NULL`，不计数，所以是 0。

统计"每个用户几单"时，要的是后者。写 `COUNT(*)` 会把"没有订单"错算成"有一单"。

空表还有一组容易误会的输出。先把 `NULL` 显示出来：

```text
.nullvalue NULL
```

```sql
SELECT COUNT(*) AS 行数, SUM(quantity) AS 件数, AVG(quantity) AS 平均
FROM orders
WHERE 0;
```

```
行数  件数  平均
----  ----  ----
0     NULL  NULL
```

`COUNT(*)` 是 0，因为确实没有行。`SUM` 和 `AVG` 是 `NULL`，不是 0。零行相加没有"和"这个值，硬给 0 等于在说"这些不存在的订单金额加起来是零"。

做报表时如果一定要显示 0，用 `COALESCE(SUM(quantity), 0)` 显式替换。这是你的选择，不是数据库的默认。

`AVG` 还有个细节：它先丢掉 `NULL`，再除以有值的行数，不是除以总行数。如果你的列允许 `NULL`，这两种分母会给出不同的平均值。想要"按总行数平均"，得写 `SUM(x) / COUNT(*)`。

## 明细问题别硬塞进统计 {#detail-vs-summary}

统计写顺手之后，很容易把明细也塞进同一条查询：

```sql
SELECT user_id, product_id, SUM(quantity * price) AS 总金额
FROM orders
JOIN products ON products.id = orders.product_id
GROUP BY user_id
ORDER BY user_id;
```

```
user_id  product_id  总金额
-------  ----------  ------
1        1           113.0
2        2           117.0
3        4           199.0
```

这个结果看起来像"每个用户买了哪个商品"，其实不是。小林既买了笔记本又买了鼠标，结果里的 `product_id = 1` 只是组里某一行的值。SQLite 允许这样写，但没保证它挑哪一行；在 PostgreSQL 里，这条查询会直接报错，要求你把 `product_id` 放进 `GROUP BY` 或聚合起来。

问题出在粒度。统计问题的一行代表一个用户，明细问题的一行代表一单，两者不该挤在同一行里。

要明细，就保留明细：

```sql
SELECT
    users.name    AS 用户,
    products.name AS 商品,
    orders.quantity AS 数量,
    orders.quantity * products.price AS 金额
FROM orders
JOIN users    ON users.id    = orders.user_id
JOIN products ON products.id = orders.product_id
ORDER BY users.id, orders.id;
```

```
用户  商品    数量  金额
----  ------  ----  -----
小林  笔记本  2     24.0
小林  鼠标    1     89.0
阿蓝  钢笔    3     105.0
阿蓝  笔记本  1     12.0
老周  键盘    1     199.0
```

写查询之前先问一句：**结果里的一行代表什么？** 一条订单、一个用户、还是一天？想清楚粒度，再决定 `GROUP BY` 写什么。

JOIN 还会改变行数。现在一条订单只对应一件商品，接上 `products` 不会变多。如果以后建了 `order_items`，一条订单对应多行商品，再拿订单总额去 `SUM`，同一笔订单会被重复加。用 `DISTINCT` 把重复行压掉，常常只是把症状盖住；真正该做的是先把明细汇总到订单粒度，再参与后面的统计。

还有一个位置问题：在数据库里聚合，传回应用的行数少；在应用里聚合，SQL 更简单。数据只有五行时两种都行。数据大到一次查回很多行时，先在数据库里分组通常更省传输。预计算好的汇总表读起来更快，但每次写入都要更新它，漏更新就会给出过期的数字。

报告上的每个数，都要连同时间范围、过滤条件一起记下来。算得对，但算的是错误的时间段，结论还是错的。

## 四个容易算错的地方 {#aggregate-pitfalls}

**"GROUP BY 之后，SELECT 里想选哪列都行。"** SQLite 不拦你，但没被分组的列只会拿到组里某一行的值，换一行数据或换一个版本就可能变。在 PostgreSQL 里，这种写法会直接报错。前面那条带 `product_id` 的查询就是反例：数字看起来合理，含义却不成立。

**"WHERE 里可以写 COUNT(*) > 1。"** 不行。聚合函数要等分组之后才有值，`WHERE` 执行时还没有组：

```
Parse error near line 1: misuse of aggregate function COUNT()
```

要筛"下单两次以上的人"，把条件写到 `HAVING COUNT(*) >= 2`。

**"空表的 SUM 是 0。"** 是 `NULL`。`COUNT(*)` 才是 0。报表要显示 0 就写 `COALESCE(SUM(...), 0)`，别把两种空结果混为一谈。

**"平均每单 = 平均件数 × 平均单价。"** 两个平均值各自算完之后再相乘，和"先算每一单的金额再平均"不是一回事：

```sql
SELECT
    AVG(quantity) * AVG(price) AS 分开平均再相乘,
    AVG(quantity * price)      AS 先算每单再平均
FROM orders
JOIN products ON products.id = orders.product_id;
```

```
分开平均再相乘  先算每单再平均
--------------  --------------
111.04          85.8
```

111.04 来自 1.6 件乘以 69.4 元；85.8 才是每单金额的平均。相乘时，件数多的一单不一定买了贵的商品，两个平均值对不上号。

## 自己写三条查询 {#self-check}

先盖住答案自己写一遍，再对照。仍然用前面那五条订单。

**第 1 题**：列出每个用户的名字和订单数，一单没下的人也要显示 0。

> **答案**
>
> 用 `LEFT JOIN` 保住所有用户，再用 `COUNT(orders.id)` 数真正有值的订单号：
>
> ```sql
> SELECT users.name, COUNT(orders.id) AS 订单数
> FROM users
> LEFT JOIN orders ON orders.user_id = users.id
> GROUP BY users.id, users.name
> ORDER BY users.id;
> ```
>
> 小满会得到 0。写成 `COUNT(*)` 的话，他会得到 1。

**第 2 题**：查 2024 年总金额超过 100 元的用户，按金额从高到低排。

> **答案**
>
> ```sql
> SELECT user_id, SUM(quantity * price) AS 总金额
> FROM orders
> JOIN products ON products.id = orders.product_id
> WHERE created_at >= '2024-01-01'
>   AND created_at <  '2025-01-01'
> GROUP BY user_id
> HAVING SUM(quantity * price) > 100
> ORDER BY 总金额 DESC;
> ```
>
> 结果里是阿蓝 117 元和小林 113 元。年份条件放 `WHERE`，分组后的金额条件放 `HAVING`。

**第 3 题**：为什么 `SELECT user_id, product_id, SUM(...) FROM orders GROUP BY user_id` 不能回答"每个用户买了哪个商品"？

> **答案**
>
> 因为结果一行代表一个用户，不是一单。一个用户买了多件商品时，`product_id` 只能取组里某一行的值，SQLite 不保证取哪一行，在 PostgreSQL 里这种写法会被直接拒绝。
>
> 要回答"买了哪个商品"，查询的粒度必须是一单一件商品，不能让 `GROUP BY user_id` 把明细压掉。要么写明细查询，要么把 `product_id` 也放进 `GROUP BY`。

## 接下来读什么 {#related}

- [SELECT：查询、筛选与排序](/learn/sql-select)
- [JOIN：关联多张表](/learn/sql-joins)
- [索引与查询代价](/learn/sql-indexes)
- [事务：让多步数据库修改共同完成](/learn/sql-transactions)

## 参考的原文与版本 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
