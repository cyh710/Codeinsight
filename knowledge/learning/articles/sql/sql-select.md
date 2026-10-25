# SELECT：查询、筛选与排序

## 一句问题里的四个空 {#four-parts}

学完这一篇，你能把一句中文问题拆成从哪张表、留哪些行、看哪些列、怎么排，再拼成一条能跑的 SELECT。

接着上一节的 shop.db。小林被问了一句：“10 到 50 元之间的商品，按价格从高到低，给我前三个。”他打开表一看，只有名字和价格，问题里的每个限定词都得自己翻译成 SQL。

表还是上一节建的那张（已经建好，这里只列出结构）：

```sql
CREATE TABLE products (
    id    INTEGER PRIMARY KEY,
    name  TEXT    NOT NULL,
    price REAL    NOT NULL
);
```

已有两条数据：`(1, '笔记本', 12.00)`、`(2, '钢笔', 35.00)`。

一句查询问题可以拆成四个空：

| 中文里的部分 | 填进 SQL 的位置 |
|---|---|
| 从哪张表拿 | `FROM products` |
| 留下哪些行 | `WHERE price BETWEEN 10 AND 50` |
| 结果里看哪些列 | `SELECT name, price` |
| 怎么排、要几条 | `ORDER BY price DESC LIMIT 3` |

拼起来：

```sql
SELECT name, price
FROM products
WHERE price BETWEEN 10 AND 50
ORDER BY price DESC
LIMIT 3;
```

四个空填完，语句就写完了。下面按这个顺序逐块试。

## 先把行筛出来 {#filter-rows}

进命令行：

```bash
sqlite3 shop.db
```

先让输出带上列名、排成表格，顺便把空值打印成 `NULL`：

```
.headers on
.mode column
.nullvalue NULL
```

这三行是 sqlite3 的点命令，不是 SQL，结尾不加分号。

看一遍全表：

```sql
SELECT name, price FROM products;
```

```
name    price
------  -----
笔记本  12.0
钢笔    35.0
```

只有两行，筛不出什么差别。补几条练习商品（这些 id 如果已经存在，跳过多余的插入）：

```sql
INSERT INTO products (id, name, price) VALUES
    (3, '圆珠笔', 3.50),
    (4, '文件夹', 8.00),
    (5, '订书机', 28.50),
    (6, '双肩包', 89.00),
    (7, '便签本', 4.20),
    (8, '胶带', 8.00);
```

现在筛 20 元以下的：

```sql
SELECT name, price
FROM products
WHERE price < 20
ORDER BY price;
```

```
name    price
------  -----
圆珠笔  3.5
便签本  4.2
文件夹  8.0
胶带    8.0
笔记本  12.0
```

`WHERE` 后面的条件会对每一行算一次，结果为真的留下，为假或为 `NULL` 的丢掉。`price < 20` 里的 `price` 是列名，`20` 是字面量。

比较符和别的语言差不多，只有两处不一样：

| 写法 | 含义 |
|---|---|
| `=` | 等于；标准写法是 `=`，SQLite 也接受 `==`，别依赖 |
| `<>` 或 `!=` | 不等于，标准写法是 `<>` |
| `<` `<=` `>` `>=` | 小于、小于等于、大于、大于等于 |

条件可以组合。要 10 到 50 元之间的：

```sql
SELECT name, price
FROM products
WHERE price >= 10 AND price <= 50
ORDER BY price;
```

```
name    price
------  -----
笔记本  12.0
订书机  28.5
钢笔    35.0
```

要 10 元以下或 50 元以上的：

```sql
SELECT name, price
FROM products
WHERE price < 10 OR price > 50
ORDER BY price;
```

```
name    price
------  -----
圆珠笔  3.5
便签本  4.2
文件夹  8.0
胶带    8.0
双肩包  89.0
```

`AND` 比 `OR` 结合得紧。下面两条只差一对括号，结果差很多：

```sql
SELECT name, price
FROM products
WHERE (price < 10 OR price > 50) AND name LIKE '便%';
```

```
name    price
------  -----
便签本  4.2
```

去掉括号：

```sql
SELECT name, price
FROM products
WHERE price < 10 OR price > 50 AND name LIKE '便%';
```

```
name    price
------  -----
圆珠笔  3.5
文件夹  8.0
便签本  4.2
胶带    8.0
```

第二条被解释成 `price < 10 OR (price > 50 AND name LIKE '便%')`，所以所有 10 元以下的商品都留下了，不管名字是什么。条件超过两个就加括号，不要靠记优先级。

## 文本、区间和清单 {#like-in-between}

名字是文本，不能用 `=` 做模糊匹配。找名字里带“本”的：

```sql
SELECT name FROM products WHERE name LIKE '%本%' ORDER BY id;
```

```
name
------
笔记本
便签本
```

`LIKE` 里有两个通配符：

- `%` 匹配零个或多个字符。
- `_` 匹配正好一个字符。

`文__` 是两个下划线，匹配“文”开头、后面正好两个字的商品：

```sql
SELECT name FROM products WHERE name LIKE '文__';
```

```
name
------
文件夹
```

SQLite 的 `LIKE` 对 ASCII 字母默认不区分大小写：

```sql
SELECT 'Pen' LIKE 'p%';
```

```
'Pen' LIKE 'p%'
---------------
1
```

在 PostgreSQL 里，`LIKE` 区分大小写，这条会返回 `f`；要忽略大小写得写 `ILIKE 'p%'`。

要在一组固定值里挑，用 `IN`：

```sql
SELECT name, price
FROM products
WHERE name IN ('钢笔', '订书机', '双肩包')
ORDER BY price;
```

```
name    price
------  -----
订书机  28.5
钢笔    35.0
双肩包  89.0
```

它和三个 `OR` 连写等价，但短、好读，也不容易漏括号。

要按区间筛，用 `BETWEEN`：

```sql
SELECT name, price
FROM products
WHERE price BETWEEN 5 AND 30
ORDER BY price;
```

```
name    price
------  -----
文件夹  8.0
胶带    8.0
笔记本  12.0
订书机  28.5
```

`BETWEEN 5 AND 30` 两头都包含，所以 5 元和 30 元本身也会留下。`NOT BETWEEN` 则把区间内外的判断反过来。

## 排序、翻页与列名 {#order-limit-alias}

不加 `ORDER BY`，数据库没有义务按任何顺序返回。想要价格从低到高：

```sql
SELECT name, price FROM products ORDER BY price;
```

`ASC` 是升序，可以不写；`DESC` 是降序。价格相同的行，顺序仍然不保证，所以可以再给一个排序键：

```sql
SELECT name, price
FROM products
ORDER BY price ASC, name DESC;
```

```
name    price
------  -----
圆珠笔  3.5
便签本  4.2
胶带    8.0
文件夹  8.0
笔记本  12.0
订书机  28.5
钢笔    35.0
双肩包  89.0
```

两个 8.0 元先按 `name` 降序排，胶带排在文件夹前面。**排序键从左到右生效：第一个键相同，才看第二个。**

这里的“降序”按字符编码比，不是按拼音。SQLite 默认用 BINARY 排序规则，`胶` 的编码比 `文` 大，所以胶带在前。PostgreSQL 按建库时选的 collation 排，中文结果可能不同。要按拼音，得另存一列拼音，或者在应用层排。

翻页用 `LIMIT` 和 `OFFSET`。价格最高的三件：

```sql
SELECT name, price
FROM products
ORDER BY price DESC, id
LIMIT 3;
```

```
name    price
------  -----
双肩包  89.0
钢笔    35.0
订书机  28.5
```

第二页，跳过前三行：

```sql
SELECT name, price
FROM products
ORDER BY price DESC, id
LIMIT 3 OFFSET 3;
```

```
name    price
------  -----
笔记本  12.0
文件夹  8.0
胶带    8.0
```

`LIMIT 3` 是最多三行，`OFFSET 3` 是先扔掉三行。两个都写时，排序必须稳定，否则两次查询可能把同一行分到两页。这里的 `id` 是兜底的唯一键。

回到开头那句话：10 到 50 元、按价格从高到低、前三个。四块拼起来：

```sql
SELECT name, price
FROM products
WHERE price BETWEEN 10 AND 50
ORDER BY price DESC
LIMIT 3;
```

```
name    price
------  -----
钢笔    35.0
订书机  28.5
笔记本  12.0
```

列可以改名，只影响输出，不改表结构：

```sql
SELECT name AS 商品, price * 0.8 AS 折后价
FROM products
WHERE price >= 30
ORDER BY price;
```

```
商品    折后价
------  ------
钢笔    28.0
双肩包  71.2
```

算出来的列也能参与排序，但别名不能随手用在 `WHERE` 里。SQLite 允许一部分这种写法，PostgreSQL 不允许；要筛，重复表达式或套一层子查询。

## 语句写的顺序不是执行顺序 {#execution-order}

`SELECT` 写在最前面，但数据库不是先执行它。逻辑上的处理顺序是：

1. `FROM products`：先确定数据来源。
2. `WHERE ...`：逐行留下满足条件的行。
3. `SELECT name, price`：从留下的行里取需要的列，算别名。
4. `ORDER BY ...`：排序。
5. `LIMIT ... OFFSET ...`：截取。

这解释了为什么 `WHERE` 里不能直接用 `SELECT` 刚起的别名：`WHERE` 比 `SELECT` 先算。也解释了为什么 `ORDER BY` 可以用别名：它在 `SELECT` 之后。

数据库实际怎么拿数据，由优化器决定。可能是全表扫，也可能走索引。看它的计划：

```sql
EXPLAIN QUERY PLAN
SELECT name, price FROM products WHERE price < 20 ORDER BY price;
```

```
QUERY PLAN
|--SCAN products
`--USE TEMP B-TREE FOR ORDER BY
```

`SCAN products` 表示整张表扫一遍；`USE TEMP B-TREE FOR ORDER BY` 表示为了排序临时建了一棵 B 树。表只有八行时，这两种做法都快得看不出来；数据量上来以后，它们才是性能问题的来源。

还有一条：没有 `ORDER BY`，结果的顺序就不保证。你在命令行里连续跑两次 `SELECT * FROM products;`，可能碰巧顺序一样，但这不是承诺。要顺序，就明写。

## 五个容易写错的地方 {#select-pitfalls}

**“`WHERE price = NULL` 能找出没定价的商品。”** 不能。`NULL` 表示“不知道”，任何值和它做 `=` 比较，结果还是“不知道”，不会被当成真。试两个表达式：

```sql
SELECT NULL = NULL;
```

```
NULL = NULL
-----------
NULL
```

```sql
SELECT NULL IS NULL;
```

```
NULL IS NULL
------------
1
```

判断空值只能用 `IS NULL` 或 `IS NOT NULL`。如果你写 `SELECT name FROM products WHERE price = NULL;` 或 `... WHERE price IS NULL;`，在这张表上都查不出东西，因为 `price` 不允许为空；换成可空列，`= NULL` 依然一条都查不到。

**“`LIKE` 就是带通配符的 `=`。”** 不完全。`%` 和 `_` 会改变匹配范围，用户输入里的 `%` 也会被当成通配符。找“笔”字：

```sql
SELECT name FROM products WHERE name LIKE '%笔%' ORDER BY id;
```

```
name
------
笔记本
钢笔
圆珠笔
```

而 `name = '钢笔'` 只会回一行。要匹配字面量 `%`，得用 `ESCAPE` 指定转义符；更常见的做法是把输入当数据传，不拼进 SQL。

**“`AND` 和 `OR` 从左往右算。”** 不是，`AND` 优先。前面那对括号的例子已经验证过：去掉括号后，便宜的四个商品全留下了。条件一多就加括号。

**“`LIMIT 3` 就是前三名。”** 只有配了 `ORDER BY` 才是。`SELECT name FROM products LIMIT 3;` 只保证最多三行，哪三行由数据库决定。翻页时还要给一个唯一键兜底，否则并列值可能重复或漏掉。

**“用户输入转义一下就能拼进 SQL。”** 手写转义容易漏掉引号、注释符和编码问题。用驱动的参数绑定，把 SQL 结构和数据分开：

```python
cur.execute(
    "SELECT id, name FROM products WHERE name LIKE ?",
    (f"%{keyword}%",),
)
```

SQLite 的占位符是 `?`，psycopg 是 `%s`，写法看驱动；关键是不要把值直接拼进字符串。

## 少查一列，少扫一行 {#select-tradeoffs}

先只查你要的列。`SELECT *` 在命令行里方便，但表一加列，返回的形状就变了，调用方可能因此出错。明确写出列名，接口更稳，传输的数据也更少。

再小心写在 `WHERE` 里的表达式。`WHERE price * 0.8 < 30` 看起来自然，但一旦 `price` 上有索引，这种写法通常用不上；改成 `WHERE price < 37.5` 才有机会走索引。现在这张表没有索引，两种写法都是全表扫，差别还看不出来。

`LIKE '%本%'` 前面的 `%` 也让普通 B 树索引失效，因为索引是按前缀排的。数据量大时，PostgreSQL 要装 `pg_trgm` 或用全文检索；SQLite 可以用 FTS 表。普通索引救不了它。

深翻页也要留意。`LIMIT 20 OFFSET 100000` 会先数过十万行再扔掉，越翻越慢。换成“从上一页末尾的值之后接着取”，条件大致是：

```sql
SELECT name, price
FROM products
WHERE price < 12.0
ORDER BY price DESC
LIMIT 3;
```

并列值要用 `(price, id)` 一起比较，否则会漏掉或重复。这不是让你现在就换写法。表只有八行，怎么查都一样。判断标准是数据量和实际计划：行数少就手算结果，行数多就看 `EXPLAIN QUERY PLAN`，别凭感觉优化。

## 三题练手 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：查出价格在 3 到 40 元之间、名字里带“笔”的商品，按价格从低到高排。

> **答案**
>
> ```sql
> SELECT name, price
> FROM products
> WHERE price BETWEEN 3 AND 40 AND name LIKE '%笔%'
> ORDER BY price;
> ```
>
> ```
> name    price
> ------  -----
> 圆珠笔  3.5
> 笔记本  12.0
> 钢笔    35.0
> ```
>
> `BETWEEN` 包含 3 和 40；`LIKE '%笔%'` 把三个带“笔”的名字都留下。

**第 2 题**：只显示名称和八折价，按八折价从低到高取前三行。

> **答案**
>
> ```sql
> SELECT name AS 商品, price * 0.8 AS 折后价
> FROM products
> ORDER BY price * 0.8, id
> LIMIT 3;
> ```
>
> ```
> 商品    折后价
> ------  ------
> 圆珠笔  2.8
> 便签本  3.36
> 文件夹  6.4
> ```
>
> 第二个排序键 `id` 是为了让两个 8.0 元商品（文件夹、胶带）的顺序固定下来，否则每次翻页可能换一个。

**第 3 题**：为什么 `LIMIT 3 OFFSET 3` 翻页时，第二页可能和第一页重复？

> **答案**
>
> 两个原因。一是没写稳定的 `ORDER BY`，并列值的顺序每次可能不同；二是两次查询之间数据被插入或删除，偏移量会跟着变。
>
> 做法是给排序加唯一键（比如 `price DESC, id`），并在数据经常变的场景改用“从上一页末尾的值之后取”的写法。

## 沿着查询继续读 {#related}

- [SQL 是什么：数据库、表、行与列](/learn/sql-database)
- [JOIN：关联多张表](/learn/sql-joins)
- [索引与查询代价](/learn/sql-indexes)
- [聚合与 GROUP BY](/learn/sql-aggregate)

## 参考资料 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
