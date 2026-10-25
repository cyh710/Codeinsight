# 主键、外键与数据约束

## 让数据库替你守规矩 {#rules-in-database}

学完这一篇，你能给表加上主键、唯一、非空、取值范围和外键，让违规写入在数据库这一层就被拒绝。

接着上一节的 shop.db。小林开始记用户和订单。程序里已经检查过“邮箱不能重复”“数量必须大于 0”，但另一个导入脚本、一次手工修数据、同事的临时 SQL，都能绕过这些检查。

把规则写进表结构，所有写入路径就都得过同一道门。

商品表还是（已经建好，这里只列出结构）：

```sql
CREATE TABLE products (
    id    INTEGER PRIMARY KEY,
    name  TEXT    NOT NULL,
    price REAL    NOT NULL
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

新建两张表。如果它们已经存在，先清掉再建（只在练习库里这么做）：

```sql
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS users;

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

这几行里塞了五种规则。下面按约束一条一条试，每条都先插正常数据，再插一条违规的看报错。

## 主键与邮箱的唯一性 {#primary-key-unique}

先插一个正常用户：

```sql
INSERT INTO users (id, name, email) VALUES (1, '小林', 'lin@example.com');
```

再拿同一个 id 插一次：

```sql
INSERT INTO users (id, name, email) VALUES (1, '重复', 'dup@example.com');
```

```
Runtime error: UNIQUE constraint failed: users.id (19)
```

SQLite 把主键冲突也报成 `UNIQUE`，因为主键和唯一约束走的是同一套唯一性检查。别看到 `UNIQUE` 就以为只有 `UNIQUE` 列才会出错。PostgreSQL 的报错更直白，会说这是主键冲突。

换一个 id，但用已经存在的邮箱：

```sql
INSERT INTO users (id, name, email) VALUES (2, '阿敏', 'lin@example.com');
```

```
Runtime error: UNIQUE constraint failed: users.email (19)
```

`email TEXT NOT NULL UNIQUE` 里的 `UNIQUE` 管重复，`NOT NULL` 管缺失。两件事分开写，因为它们的规则不一样：`UNIQUE` 只约束非空值。SQLite 和 PostgreSQL 都允许多行 `email` 为 `NULL`，所以光写 `UNIQUE`，多个人不填邮箱也能通过。这张表加了 `NOT NULL`，才把“必须有邮箱”也堵上。

把两个正常用户补进去：

```sql
INSERT INTO users (id, name, email) VALUES
    (2, '阿敏', 'min@example.com'),
    (3, '老周', 'zhou@example.com');
```

主键可以是一列，也可以是几列。比如记录“谁买了什么”的中间表，可以写 `PRIMARY KEY (user_id, product_id)`，让同一对组合只出现一次。这里是单列主键，`INTEGER PRIMARY KEY` 还会在你不写 id 时自动分配。PostgreSQL 里对应的写法是 `GENERATED ALWAYS AS IDENTITY` 或者 `serial`。

自动分配的号不要当业务顺序用。删掉最大的一行，SQLite 下一行可能又拿到这个号；PostgreSQL 的序列不会因为删行回退，但失败的事务也会留下空洞。两种都不适合当订单号。

## 非空与取值范围 {#not-null-check}

再试一次不填邮箱：

```sql
INSERT INTO users (id, name) VALUES (4, '阿敏');
```

```
Runtime error: NOT NULL constraint failed: users.email (19)
```

`name` 给了，`email` 没给，也没有默认值，所以是 `NULL`，被 `NOT NULL` 拦住。空字符串 `''` 不是 `NULL`，它会被放行；如果空字符串也算无效，得再加一条 `CHECK (email <> '')`。

插入一张正常订单，作为下面检查的参照：

```sql
INSERT INTO orders (id, user_id, product_id, quantity, created_at)
VALUES (1, 1, 1, 2, '2026-10-01 10:00:00');
```

数量写 0：

```sql
INSERT INTO orders (id, user_id, product_id, quantity)
VALUES (2, 1, 1, 0);
```

```
Runtime error: CHECK constraint failed: quantity > 0 (19)
```

`CHECK (quantity > 0)` 是行级条件，每一行插入或修改时算一次，结果为假就拒绝。它引用同一行里的列没问题，比如 `CHECK (quantity > 0 AND quantity < 1000)`；但它看不到别的行，也查不了别的表。像“每个用户最多 3 个未付款订单”这种规则，写不进 `CHECK`。

`CHECK` 还有个容易忽略的点：表达式结果是 `NULL` 时，它不算违反。如果列本身可空，`CHECK (price > 0)` 会放行 `NULL`。真要“必须有值且在范围内”，就把 `NOT NULL` 和 `CHECK` 一起写。

`created_at` 有默认值。插入时不写这一列，SQLite 用 `datetime('now')` 填当前 UTC 时间。在 PostgreSQL 里，更常见的写法是 `timestamptz NOT NULL DEFAULT now()`，存带时区的时间。

再插一张正常订单：

```sql
INSERT INTO orders (id, user_id, product_id, quantity, created_at)
VALUES (2, 2, 2, 1, '2026-10-02 15:30:00');
```

```sql
SELECT id, user_id, product_id, quantity FROM orders ORDER BY id;
```

```
id  user_id  product_id  quantity
--  -------  ----------  --------
1   1        1           2
2   2        2           1
```

## 外键与那条容易忘的开关 {#foreign-key-pragma}

`orders.user_id REFERENCES users(id)` 的意思是：`user_id` 不为 `NULL` 时，它的值必须在 `users.id` 里存在。`product_id` 同理，指向商品表。`NOT NULL` 和 `REFERENCES` 是两条规则：前者要求必须填，后者要求填了就得指向一个真实的行。

SQLite 的外键检查**默认是关的**。先看一眼：

```sql
PRAGMA foreign_keys;
```

```
foreign_keys
------------
0
```

打开：

```sql
PRAGMA foreign_keys = ON;
PRAGMA foreign_keys;
```

```
foreign_keys
------------
1
```

这个开关按连接生效。新开一个 `sqlite3` 会话，或者应用新建一个连接，都要重新设一次；有些驱动能在连接初始化时替你执行。在 PostgreSQL 里，外键默认就强制生效，不需要这一步。

现在插一张不存在的用户的订单：

```sql
INSERT INTO orders (id, user_id, product_id, quantity)
VALUES (3, 99, 1, 1);
```

```
Runtime error: FOREIGN KEY constraint failed (19)
```

换成不存在的商品，报错一样：

```sql
INSERT INTO orders (id, user_id, product_id, quantity)
VALUES (3, 1, 99, 1);
```

```
Runtime error: FOREIGN KEY constraint failed (19)
```

这条消息不告诉你是哪一列的外键，只给一个约束错误码。两个外键都查一遍。

关掉开关会怎样：

```sql
PRAGMA foreign_keys = OFF;
INSERT INTO orders (id, user_id, product_id, quantity)
VALUES (99, 99, 1, 1);
SELECT id, user_id FROM orders WHERE id = 99;
```

```
id  user_id
--  -------
99  99
```

脏数据就这么进去了。SQLite 提供了 `foreign_key_check` 来事后审计：

```sql
PRAGMA foreign_key_check;
```

```
table   rowid  parent  fkid
------  -----  ------  ----
orders  99     users   1
```

`table` 是子表，`rowid` 是违规行的 rowid，`parent` 是被引用的父表，`fkid` 是第几个外键。清掉这行，再把开关打开：

```sql
DELETE FROM orders WHERE id = 99;
PRAGMA foreign_keys = ON;
```

外键还会挡住删除。用户 1 有订单，直接删他：

```sql
DELETE FROM users WHERE id = 1;
```

```
Runtime error: FOREIGN KEY constraint failed (19)
```

删被引用的父行时，数据库默认拒绝。这个行为可以在建表时改：

| 写法 | 删除被引用的用户时 |
|---|---|
| 不写，或 `ON DELETE NO ACTION` | 拒绝删除 |
| `ON DELETE RESTRICT` | 拒绝删除，意图写得更明确 |
| `ON DELETE CASCADE` | 把这个用户的订单一起删掉 |
| `ON DELETE SET NULL` | 把订单的 `user_id` 置为 `NULL`，列必须可空 |

`CASCADE` 省事，但误删一个用户会连带删掉他的全部订单；订单这种有审计价值的数据，通常选拒绝，让调用方先处理关联行。`SET NULL` 在这里用不了，因为 `user_id` 是 `NOT NULL`。

`PRAGMA foreign_keys` 不能在事务中间改。要开就在 `BEGIN` 之前开。

## 约束在什么时候检查 {#constraint-mechanism}

`INSERT` 和 `UPDATE` 每写一行，数据库就把相关约束过一遍。主键和 `UNIQUE` 的检查靠索引查找，写入时也要维护索引；`NOT NULL` 和 `CHECK` 是逐行算表达式；外键要去父表找那一行。任何一条不过，当前语句中止。

所以约束不是“建议”，是写入路径上的硬门槛。程序里的校验可以先跑，给用户一句好读的提示；数据库约束负责兜底，防的是并发和绕过。

并发这一层值得说清楚。两个连接同时执行：

1. 连接 A 查邮箱 `a@example.com`，没找到。
2. 连接 B 也查，也没找到。
3. A 插入成功。
4. B 插入成功——如果没有 `UNIQUE`，两条重复就进去了。

两次 `SELECT` 和两次 `INSERT` 之间存在空隙，只有数据库里的 `UNIQUE` 能把第四步挡住。先查再插的程序逻辑替代不了它。

外键的父行查找也需要索引。`users.id` 是主键，查得快；`orders.user_id` 上没有索引时，删除一个用户就要扫一遍订单表。SQLite 不会自动给外键子列建索引，PostgreSQL 也不会。常用的话就手动加：

```sql
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
```

表只有两行时看不出区别。等订单多起来，这个索引才值钱。

约束可以起名字，比如 `CONSTRAINT quantity_positive CHECK (quantity > 0)`。PostgreSQL 的报错会带上这个名字，迁移和排查都方便；SQLite 的 `CHECK` 报错会带上表达式本身。约束一多，命名比省几个字有用。

## 四个关于约束的错觉 {#constraint-pitfalls}

**“程序里查过重了，数据库不用加 UNIQUE。”** 上面那个两连接的时间线就是反例。检查与写入不在一个原子操作里，两个请求可以同时通过检查。`UNIQUE` 把判断和写入放进同一条语句，才能真正防住。

**“写了 REFERENCES，外键就一定生效。”** SQLite 默认关着，`PRAGMA foreign_keys;` 回 0。忘了开，脏数据能直接插进去，删除父行也不会被拦。每建立一个连接就设一次，或者用 `PRAGMA foreign_key_check;` 定期审计。PostgreSQL 默认开启，没有这个坑。

**“有 CHECK 就相当于 NOT NULL。”** 不是。`CHECK` 只拒绝表达式为假的行，表达式为 `NULL` 时放行：

```sql
DROP TABLE IF EXISTS temp_check_null;
CREATE TEMP TABLE temp_check_null (q INTEGER CHECK (q > 0));
INSERT INTO temp_check_null (q) VALUES (NULL);
SELECT COUNT(*) FROM temp_check_null;
```

```
COUNT(*)
--------
1
```

要“必须有值且大于 0”，写 `q INTEGER NOT NULL CHECK (q > 0)`，两条都要。

**“主键会一直递增，删掉的号不会再用。”** SQLite 的 `INTEGER PRIMARY KEY` 不写 `AUTOINCREMENT` 时，新行取当前最大值加一，删掉最大那行后这个号会被重用：

```sql
DROP TABLE IF EXISTS temp_id_reuse;
CREATE TEMP TABLE temp_id_reuse (id INTEGER PRIMARY KEY, v TEXT);
INSERT INTO temp_id_reuse (v) VALUES ('a'), ('b'), ('c');
DELETE FROM temp_id_reuse WHERE id = 3;
INSERT INTO temp_id_reuse (v) VALUES ('d');
SELECT id, v FROM temp_id_reuse;
```

```
id  v
--  -
1   a
2   b
3   d
```

`d` 又拿到了 3。PostgreSQL 的序列不会因为删行回退，但失败的事务也会留下空洞。两种都别把 id 当业务顺序。

## 约束的代价 {#constraint-tradeoffs}

约束让无效状态进不来，代价是写入变慢、迁移变麻烦。每加一个唯一索引，插入和更新都要维护它；每加一个外键，写入和删除都要多查一次父表。数据量小的时候感觉不到，表大了就是实打实的开销。

给已有数据加约束，先把违规数据清干净。表里已经有重复邮箱时，`UNIQUE` 建不上；已有孤儿订单时，外键也建不上。PostgreSQL 可以先把外键或 `CHECK` 以 `NOT VALID` 加上，再 `VALIDATE CONSTRAINT`，减少锁表时间；SQLite 的 `ALTER TABLE` 能力有限，很多时候要重建表再搬数据。

`CASCADE` 和 `RESTRICT` 是两种产品决策。用户注销时，订单是该保留、该一起删，还是该把归属置空？先回答这个问题，再选约束；不要因为 `CASCADE` 省事就默认加上。

软删除和唯一约束会打架。用户表加了 `deleted_at` 之后，已注销用户的邮箱仍然占着 `UNIQUE`。部分唯一索引（条件 `WHERE deleted_at IS NULL`）能解决，但它要求所有查询都记得过滤 `deleted_at`，复杂度从约束转移到了查询。

字段经常变、每条记录形状不一样时，严格的关系表会逼你不停迁移。这种场景可以退一步用 JSON 列，把结构校验放到应用层。代价是数据库不再替你保证字段存在、类型正确、引用有效。规则重要就留在表上；规则只是展示层的约束，再考虑放宽。

判断标准不复杂：**违反了会让数据自相矛盾、或者让别的程序读到坏数据的规则，放数据库；只是流程提示、随时可能改的规则，放应用。** 两边都校验不浪费：应用负责给出人话，数据库负责兜底。

## 三道约束题 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：`PRAGMA foreign_keys` 是 `OFF` 时，插入一条 `quantity = 0` 的订单，会发生什么？

> **答案**
>
> 仍然会失败：
>
> ```
> Runtime error: CHECK constraint failed: quantity > 0 (19)
> ```
>
> `PRAGMA foreign_keys` 只控制外键检查，`CHECK`、`NOT NULL`、`UNIQUE`、主键不受它影响。

**第 2 题**：能不能用 `CHECK` 实现“每个用户最多 3 个未付款订单”？

> **答案**
>
> 不能。`CHECK` 只看得见当前这一行，看不到这个用户的其他订单，也不能对别的表做查询。
>
> 这种跨行规则要放在应用逻辑里，用事务和锁保证并发下不超；或者用触发器。另一种建模方式是在订单上放一个 `slot` 列（1、2、3），再对 `(user_id, slot)` 建唯一约束，把“最多三个”变成“同一格不能占两次”。代价是业务得管理这个格子的分配和释放。

**第 3 题**：邮箱只写 `email TEXT UNIQUE`，不写 `NOT NULL`，会漏掉什么？

> **答案**
>
> 会漏掉“必须有邮箱”。`UNIQUE` 允许多行 `NULL`，所以很多人可以不填邮箱，而且不违反唯一性。
>
> 要拦住缺失，写 `email TEXT NOT NULL UNIQUE`。空字符串 `''` 仍然是有效值，如果它也算无效，再加 `CHECK (email <> '')`。

## 从约束走到哪里 {#related}

- [SQL 是什么：数据库、表、行与列](/learn/sql-database)
- [JOIN：关联多张表](/learn/sql-joins)
- [事务：让多步数据库修改共同完成](/learn/sql-transactions)
- [索引与查询代价](/learn/sql-indexes)

## 约束语法的参考 {#sources}

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
