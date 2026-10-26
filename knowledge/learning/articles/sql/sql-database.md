# SQL 是什么：数据库、表、行与列

## SQL 是什么 {#overview}

SQL 是向关系型数据库表达数据操作的语言。这篇从一张商品表出发，观察数据怎样写入、筛选，再用订单表看懂两张表如何关联。

假设你用记事本记商品：笔记本 12 元，钢笔 35 元。记录多了，你会想按价格筛选、按编号更新，并防止订单引用一个不存在的商品。数据库提供组织、查询和约束数据的机制，SQL 用来表达这些要求。

先把表理解为有固定列的数据集合：一行是一条记录，一列是某个属性。它与电子表格有相似之处，但数据库还提供约束、事务和查询优化等机制。数据库也不会自动保证所有业务正确：没有相应约束，错误数据仍可能写进去。

`SELECT name FROM products` 表达“取出商品名”。你不必在这条语句里编写打开文件、解析每一行、逐行遍历的过程。SQL 不等于数据库本身：SQLite、PostgreSQL 是数据库系统，各自支持共同语法和不同扩展。

本篇运行示例使用 **SQLite 3**，以 Python 标准库 `sqlite3` 验证。它不要求安装独立的 sqlite3 命令行工具。在本仓根目录运行：

```bash
python knowledge/learning/examples/sql_basics.py
```

脚本使用内存数据库，不修改项目数据。若改用其他 SQL 工具，先确认它连接的数据库；不要把 SQLite 的行为直接视为所有数据库的规则。

## 建一张表 {#example}

先定义结构：

```sql
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL
);
```

表里现在没有商品。`id` 标识记录，`name` 存商品名，`price` 存价格。主键与 NOT NULL 是由数据库检查的约束，不是给人看的备注。

写入两条记录：

```sql
INSERT INTO products (id, name, price) VALUES
    (1, '笔记本', 12.0), (2, '钢笔', 35.0);
```

| id | name | price |
|---|---|---|
| 1 | 笔记本 | 12.0 |
| 2 | 钢笔 | 35.0 |

想找价格低于 20 的商品：

```sql
SELECT name, price FROM products WHERE price < 20 ORDER BY id;
```

结果只有 `笔记本，12.0`。SQL 工具可能显示表格，Python 可以拿到元组；显示形式不同，不改变查询选择了哪些字段与记录。

这里用 REAL 是为了先理解查询。真实金额若要求精确计算，要另外设计表示方式，例如整数分；不能把浮点演示直接当财务方案。SQLite 的类型亲和性也不等于所有值都会按声明强制限制，类型约束须单独核对。

## 这三步各自在做什么 {#walkthrough}

建结构、写数据、查结果是不同动作。读代码时可按这个顺序观察：

1. **建了什么结构？** 列、主键、约束、默认值决定允许的数据形状。
2. **写入了什么？** 列名让输入与列对应。新增列还要核对默认值和约束，不能默认旧写入一定兼容。
3. **需要什么结果？** SELECT 指定列，FROM 指定来源，WHERE 指定条件。

| 语句部分 | 本例作用 |
|---|---|
| `SELECT name, price` | 结果保留商品名与价格 |
| `FROM products` | 从商品表读取 |
| `WHERE price < 20` | 保留条件为真的行 |
| `ORDER BY id` | 明确要求按编号排序 |

把条件改成 `price >= 20` 会返回钢笔；把结果列改成 `SELECT name`，价格就不出现在结果中。两处分别控制“哪些行”和“哪些列”。查询未选择某列，不会从原表删除那列。

## 一笔订单为什么只记商品编号 {#relationships}

现在保存订单。先用一个小模型说明引用：订单保存商品编号，查询时按编号找到商品。SQLite 需要为当前连接启用外键检查，下面的 PRAGMA 在事务开始前执行。

```sql
PRAGMA foreign_keys = ON;
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
INSERT INTO orders (id, product_id, quantity) VALUES
    (101, 1, 2), (102, 1, 1), (103, 2, 1);
```

![orders.product_id 引用 products.id：一个商品可以被多笔订单引用，箭头表示引用关系，不表示执行先后。](/knowledge/assets/sql-table-relation)

订单 101 与 102 都引用商品 1，因而找到同一个笔记本；103 引用商品 2。声明 REFERENCES 且启用外键检查，数据库才检查引用。画线或给字段起相同名字，不会建立约束。在事务中途修改 `foreign_keys` 也不能按预期切换检查设置。

用关联查询把需要的列放到一起：

```sql
SELECT orders.id, products.name, orders.quantity,
       products.price * orders.quantity AS total
FROM orders
JOIN products ON products.id = orders.product_id
ORDER BY orders.id;
```

| id | name | quantity | total |
|---|---|---|---|
| 101 | 笔记本 | 2 | 24.0 |
| 102 | 笔记本 | 1 | 12.0 |
| 103 | 钢笔 | 1 | 35.0 |

笔记本出现两次不是重复错误：这是两笔不同订单。JOIN 根据条件组合行，不会自动理解“只要一份商品名”。没有匹配、LEFT JOIN 与多对多可继续读[关联查询](/learn/sql-joins)。

这仍是教学模型。真实订单通常要记录**成交时价格**，否则商品改价会改变按当前价格计算的历史金额。是否保存快照取决于业务含义，不能因为学会关联就把所有重复字段删除。

## 数据库在背后做了什么 {#mechanism}

数据库检查语句、表与列，再规划如何取得结果。逻辑上可以理解成从来源匹配行、按条件筛选、形成结果列，再按要求排序。这个理解过程不等于物理执行计划，数据库可能借助索引优化读取。

`WHERE price * 0.8 < 30` 表示打八折后价格低于 30；`price * 2` 则是乘二。表达式要与业务含义一致。对列运算有时影响普通索引使用，要结合数据库、表达式索引与执行计划判断，不能说“一有计算就必然不用索引”。

数据库也检查约束。重复主键、违反 NOT NULL、在启用外键检查时引用不存在的商品，都应得到错误。捕获并解释错误是调用程序的职责；请求没有显示异常，不证明数据已经写成功。

## 四件容易搞混的事 {#pitfalls}

**结果没有天然顺序。** 没有 ORDER BY 就不保证排序。连续几次看起来一样，也不能把观察写成接口承诺。稳定分页还要处理排序字段相同的情况。

**NULL 不是零或空字符串。** 它表示缺失或未知。`WHERE price = NULL` 不能按普通相等比较找到空值，应使用 `IS NULL`。本例 price 有 NOT NULL 约束，不能插入 NULL；其他表是否允许缺失，要看它的定义。

**主键不等于必须手填编号。** 本篇显式填 id 便于观察。SQLite 的 `INTEGER PRIMARY KEY` 具有与 rowid 相关的自动编号行为，与其他类型声明、其他数据库的自增方式不同。

**表改名通常有现成语句。** SQLite 与 PostgreSQL 都支持：

```sql
ALTER TABLE products RENAME TO goods;
```

这会改名并保留数据。应用查询、部署迁移等仍要核对；某些其他结构变更可能需要重建表，但不能把重建当作改名的通用步骤。验证脚本在所有查询之后才改名，之后再查询旧表名就会失败。

## 什么时候不该用数据库 {#tradeoffs}

选择取决于查询、约束、并发、持久化与恢复需求。只有几十条但必须可靠保存、被多个进程修改的数据，也可能适合 SQLite；大量临时且可重建的数据，未必需要长期数据库。条数不能单独决定方案。

数据库带来迁移、备份与连接管理成本。简单配置可能只需要 JSON 文件；需要关联、筛选和一致性的数据，自己实现这些能力往往更复杂。先明确要求，再比较代价。

## 改一个条件，预测结果 {#self-check}

给关联查询增加 `WHERE orders.quantity >= 2`，会剩下哪一行？先看订单数据，再执行，结果只包含 101：筛的是数量，不是总额。

再尝试插入引用商品 999 的订单。若连接启用了外键检查且没有这个商品，写入会失败。它验证的是数据库约束，与“前端下拉框没有商品 999”提供的保证不同。

## 继续阅读 {#related}

- [查询、筛选与排序](/learn/sql-select)
- [键与数据约束](/learn/sql-constraints)
- [关联查询](/learn/sql-joins)
- [事务](/learn/sql-transactions)
- [URL、JSON 与 API](/learn/web-api)

## 参考资料 {#sources}

- [SQLite ALTER TABLE](https://www.sqlite.org/lang_altertable.html)、[外键](https://www.sqlite.org/foreignkeys.html)、[类型](https://www.sqlite.org/datatype3.html)。SQLite authors；Public Domain；快照与许可见来源清单。
- [PostgreSQL 18 教程](https://www.postgresql.org/docs/18/tutorial.html)、[ALTER TABLE](https://www.postgresql.org/docs/18/sql-altertable.html)。PostgreSQL Global Development Group；PostgreSQL License。本篇示例为 SQLite，PostgreSQL 资料用于比较。
- 2026-10-26 重写数据观察，修正折扣、表改名、输出方式和适用边界。图为原创，作者及许可独立记录。
