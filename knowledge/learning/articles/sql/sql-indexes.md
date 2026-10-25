# 索引与查询代价

## 找一个人的订单，数据库读了整张表 {#full-scan}

学完这一篇，你能用 EXPLAIN QUERY PLAN 看出查询有没有走索引，并判断一张表该不该加索引。

接着前面的 `shop.db`：`products`、`users`、`orders` 三张表都在。结构如下，已经建过的不用重跑：

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

订单还是前面那五条，商品还是那四件。`products` 后来可能多了一列 `stock`，这一篇只查 `orders`，不影响计划。下面不新增数据，只看数据库准备怎么找。

打开数据库：

```bash
sqlite3 shop.db
```

```text
.headers on
.mode column
```

查小林的两条订单，先让 SQLite 交代它的计划：

```sql
EXPLAIN QUERY PLAN
SELECT * FROM orders WHERE user_id = 1;
```

你会看到类似这样的一行：

```
QUERY PLAN
`--SCAN orders
```

`EXPLAIN QUERY PLAN` 不会真的执行查询，它只打印数据库准备怎么执行。不同版本的 SQLite 可能在计划里多印几个词，关键词是 `SCAN` 和 `SEARCH`。`SCAN orders` 的意思是：把 `orders` 从头到尾读一遍，每读一行就检查 `user_id` 是不是 1。

五行数据，扫一遍几乎不花时间。表大到一次扫描明显变慢时，每次找一个人的订单都读完整张表，代价就不一样了。

`SCAN` 是全文扫描。数据库没有一条能直接跳到 `user_id = 1` 那些行的路径，只能一行行试。

## 建一条按 user_id 排的目录 {#create-index}

给 `orders` 建一条索引，按 `user_id` 排，同一个人内部再按 `created_at` 排：

```sql
CREATE INDEX orders_user_created_idx ON orders(user_id, created_at);
```

再问一次同一个查询：

```sql
EXPLAIN QUERY PLAN
SELECT * FROM orders WHERE user_id = 1;
```

这次的输出变成：

```
QUERY PLAN
`--SEARCH orders USING INDEX orders_user_created_idx (user_id=?)
```

注意两个词变了：`SCAN` 变成 `SEARCH`，并且多出了索引名和 `(user_id=?)`。

`SEARCH ... USING INDEX` 的意思是：数据库先在索引里定位到 `user_id = 1` 的那一段，再顺着索引项找到表里的行。它不用把整张表读完。

索引本身是一棵按 `(user_id, created_at)` 排好序的树。每个索引项存着这两列的值，再加一个指向表里那一行的位置。找 `user_id = 1` 时，数据库从树根往下走，几步就到那一段；找 `user_id = 1 AND created_at >= '2024-03-01'` 时，还能在那一段里按日期继续缩小。

`CREATE INDEX` 会先扫一遍现有数据把树建起来。之后的每一次 `INSERT`、`UPDATE`、`DELETE`，数据库都要顺手维护这棵树。查询变快不是白来的，代价在后面算。

数据行没有变，两条查询要的结果也没有变。变的只是数据库找行的路径。

## 列顺序决定了索引能帮谁 {#composite-order}

`orders_user_created_idx` 的第一列是 `user_id`，第二列是 `created_at`。这个顺序很关键。

只看日期，不看用户：

```sql
EXPLAIN QUERY PLAN
SELECT * FROM orders WHERE created_at = '2024-04-11';
```

```
QUERY PLAN
`--SCAN orders
```

索引里确实有 `created_at`，但它是第二列。索引先按 `user_id` 排，再按 `created_at` 排。不同用户的日期交错在一起，数据库没法只凭一个日期跳到目标位置，只好扫表。

把 `user_id` 也写上：

```sql
EXPLAIN QUERY PLAN
SELECT * FROM orders
WHERE user_id = 1 AND created_at >= '2024-01-01';
```

```
QUERY PLAN
`--SEARCH orders USING INDEX orders_user_created_idx (user_id=? AND created_at>?)
```

这次索引的两列都用上了。数据库先按第一列定位到小林那一段，再在段内按第二列找日期。

这就是复合索引的"最左前缀"：查询条件必须从索引的第一列开始用，后面的列才能接着用。像一本先按姓、再按名字排序的电话簿——你知道姓，能翻到那一页；你只知道名字，电话簿帮不上忙，只能从头翻。

所以索引的列顺序要按查询来定。如果最常查的是"某个人在某段时间的订单"，`(user_id, created_at)` 正合适。如果最常查的是"某一天的订单"，应该建 `(created_at)`，或者 `(created_at, user_id)`。

顺序对了还有额外的好处：`WHERE user_id = 1 ORDER BY created_at` 可以顺着索引的顺序读，不用再单独排序。

在 PostgreSQL 里，B-tree 索引也是这个规则。`(user_id, created_at)` 对单独按 `created_at` 的查询同样帮不上定位的忙。

## 在列上套函数，索引就用不上 {#function-on-column}

下面这条查询想找小林 2024 年的订单：

```sql
EXPLAIN QUERY PLAN
SELECT * FROM orders
WHERE user_id = 1
  AND strftime('%Y', created_at) = '2024';
```

```
QUERY PLAN
`--SEARCH orders USING INDEX orders_user_created_idx (user_id=?)
```

索引只用上了 `user_id`。`created_at` 那一列出现在计划里了吗？没有。

索引里存的是 `created_at` 的原值，不是它的年份。数据库要先读到每一行，对 `created_at` 调用 `strftime`，才知道是不是 2024 年。索引没法帮它跳过不属于 2024 的行。

改成范围查询，条件就能落回原始列：

```sql
EXPLAIN QUERY PLAN
SELECT * FROM orders
WHERE user_id = 1
  AND created_at >= '2024-01-01'
  AND created_at <  '2025-01-01';
```

```
QUERY PLAN
`--SEARCH orders USING INDEX orders_user_created_idx (user_id=? AND created_at>? AND created_at<?)
```

这一次 `created_at` 的两个边界都出现在计划里。数据库能在索引中先把日期范围缩出来，只读那一段的行。

条件写成半开区间 `>= 起点 AND < 下一年起点`，比 `BETWEEN` 更不容易把下一年 1 月 1 日零点算进来。

`strftime` 是 SQLite 的函数。在 PostgreSQL 里没有这个函数，对应写法是 `date_part('year', created_at) = 2024` 或者 `to_char(created_at, 'YYYY') = '2024'`；函数套在列上，普通索引一样用不上。想走索引，还是把条件改写成日期范围。

索引不是"只要列出现在 WHERE 里就能用"，它只认得列的原值。

## 索引不是白拿的 {#index-cost}

索引要占空间。它是一个独立的数据结构，表里有多少行，索引里就有多少项，外加树的页。几个索引加起来，占的空间不能忽略。

索引还要维护。每插一条订单，数据库除了写表，还要往每个索引里插一项；改 `user_id` 或 `created_at`，要把索引项从旧位置挪到新位置；删订单，也要删索引项。表上索引越多，每次写要干的活越多。

查询也会受影响。索引让某些查询变快，但优化器多了一些选择，计划也可能变得不那么直观。索引不是免费的加速按钮，它是一笔用写入和空间换读取的买卖。

还有一点常被误会：索引不保存查询结果。它保存的是键和指向行的位置。同样的查询跑第二次，数据库仍然要执行一遍，只是找行更快。想让结果不重复计算，那是缓存要解决的问题，不是索引。

唯一索引还承担另一件事：`UNIQUE` 约束在 SQLite 和 PostgreSQL 里都靠唯一索引实现。建它不全是为了查询速度。

## 哪些表不该急着建索引 {#when-not}

**小表。** 整张表只有几页时，全表扫也很快。这篇的五条订单就是这种规模，建完索引后 SQLite 照样选了 `SEARCH`。五行数据上，扫描本来就读不了几页，计划里出现 `SEARCH` 不代表你赚到了什么。索引的收益要等表大到扫描明显变慢才会出现。

**低区分度的列。** 区分度就是这一列有多少个不同的值。邮箱几乎一人一个，区分度高；订单状态只有几种，区分度低。如果条件会命中表里大部分行，数据库要先在索引里找出大量位置，再一行行回表，可能还不如直接扫表。在 PostgreSQL 里，这种情况优化器常常直接选 `Seq Scan`。SQLite 的代价模型更简单，小表上未必这么做，所以要在真实数据量上看计划。

**写多读少的表。** 日志、事件流水这类表，写入频繁，查询模式又固定。每加一个索引，每次写入都要多维护一处。先确认真的有一条常用查询需要它，再建。

**根本没出现在查询里的列。** 不在 `WHERE`、`JOIN`、`ORDER BY` 里用的列，建索引没有查询收益（唯一约束除外）。

判断顺序很朴素：先收集真实会跑的查询，看看它们按什么列过滤、连接、排序，再给这些列建索引。不要先给每列都建一个，然后指望优化器自己挑。

## 四个关于索引的误会 {#index-myths}

**"建了索引，查询就一定走索引。"** 不一定。优化器会算代价；条件命中大部分行、表很小、列上套了函数、复合索引没用上第一列，都会让它放弃索引。前面按 `created_at` 单独查的计划就是例子：索引在，还是 `SCAN`。

**"索引越多，查询越快。"** 查询不一定更快，写入一定更慢。每个索引都要占空间、在每次写时维护。索引应该跟着查询走，不是跟着列走。

**"索引会把查询结果缓存起来，第二次就快。"** 不会。索引存的是键和行位置，不是结果集。第二次查询仍然要执行，只是如果索引合适，找行会快一些。能直接从索引回答的覆盖索引，省的是回表，也不是缓存结果。

**"EXPLAIN 里出现 SEARCH，就证明快了。"** 计划只说明路径，不说明实际花了多久。要看真实数据量下的读取行数和时间。在 PostgreSQL 里，`EXPLAIN ANALYZE` 会真的执行语句并报告实际耗时；对 `UPDATE`、`INSERT`、`DELETE` 来说，它也会真的改数据，别在生产库随手试。SQLite 没有 `EXPLAIN ANALYZE`，可以用 `.timer on` 或应用侧的计时，多跑几次再判断。

## 用 EXPLAIN 验证你的答案 {#self-check}

先自己写，再对照。仍然用 `shop.db` 里的 `orders`。

**第 1 题**：订单经常按 `created_at` 的范围查，应该建什么索引？建完后计划里的关键词是什么？

> **答案**
>
> ```sql
> CREATE INDEX orders_created_at_idx ON orders(created_at);
> ```
>
> 再查范围：
>
> ```sql
> EXPLAIN QUERY PLAN
> SELECT * FROM orders
> WHERE created_at >= '2024-01-01' AND created_at < '2025-01-01';
> ```
>
> 你会看到类似 `SEARCH orders USING INDEX orders_created_at_idx (created_at>? AND created_at<?)` 的一行。索引的第一列就是查询条件用的列。

**第 2 题**：已经有 `(user_id, created_at)` 这条复合索引，`WHERE created_at >= '2024-01-01'` 能靠它定位吗？为什么？

> **答案**
>
> 不能。索引先按 `user_id` 排序，`created_at` 只是组内的第二排序键。没有 `user_id` 条件，日期在不同用户之间交错，数据库没法从索引中间直接跳到某一天。
>
> 如果还没建单独的 `(created_at)` 索引，计划里会是 `SCAN orders`；如果按第 1 题建了，它会改用那条新索引，这正说明单独的日期索引解决了问题。如果这种查询很常见，建 `(created_at)`，或者把复合索引改成 `(created_at, user_id)`。

**第 3 题**：把 `WHERE strftime('%Y', created_at) = '2024'` 改写成能走索引的条件。

> **答案**
>
> 用范围条件，让原始列直接参与比较：
>
> ```sql
> SELECT * FROM orders
> WHERE created_at >= '2024-01-01'
>   AND created_at <  '2025-01-01';
> ```
>
> `strftime` 的结果不在索引里，数据库必须逐行计算；范围条件直接作用在索引存的原值上，才能定位到那一段。

## 相关篇目 {#related}

- [SELECT：查询、筛选与排序](/learn/sql-select)
- [聚合与 GROUP BY](/learn/sql-aggregate)
- [事务：让多步数据库修改共同完成](/learn/sql-transactions)
- [SQL 是什么：数据库、表、行与列](/learn/sql-database)

## 参考资料 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
