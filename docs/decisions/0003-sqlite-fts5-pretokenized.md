# 0003. 关键词检索用 SQLite FTS5 + 入库预分词

- **状态**：已接受
- **日期**：2026-10-23
- **影响范围**：`storage/schema.sql`（`chunk_fts` 虚表 + 3 个触发器）、`cognitive/retrieval/bm25.py`
- **源文档**：§3.2 技术选型（语义检索：Embedding + BM25）、§5-2 结构化代码检索

## 背景

源文档要求 BM25 关键词通道。问题有三个：

1. **用什么实现倒排索引**——自研、还是用现成的？
2. **代码怎么分词**——代码标识符是 `get_user_name`、`HTTPServer`、`foo()`，
   不是自然语言。默认分词器会把它们切碎。
3. **FTS 索引怎么跟主表同步**——增量索引会 insert / update / delete。

第 3 点最容易出 bug：如果同步逻辑分散在三条路径上，"文件删了但 FTS 里残留旧行"
这类问题极难发现，而且它直接导致**检索结果与当前仓库不一致**（源文档 §3.1 第四层末句明令避免）。

## 决策

**用 SQLite FTS5 内置 `bm25()`，external content 虚表 + 触发器同步。**

```sql
CREATE VIRTUAL TABLE chunk_fts USING fts5(
    token_text,
    content='chunk',
    content_rowid='id',
    tokenize = "unicode61 tokenchars '_'"
);
```

分词**在入库前完成**：自写 `split_identifiers(text)`，为每个标识符产出
**全名 + snake 分词 + camel 分词 + 小写形式**，写进 `chunk.token_text` 这一列空格分隔的串。
**查询时走同一个函数**。

同步交给三个触发器（`chunk_ai` / `chunk_ad` / `chunk_au`），应用层零同步代码。

## 理由

### 为什么用 FTS5 而不是自研倒排索引

- 自研倒排索引 = 造轮子 + 自己承担持久化、增量更新、压缩、查询解析。
- FTS5 是 SQLite 内置的，**零依赖**，且 `bm25()` 的排序质量就是标准 BM25。

### 为什么必须预分词

`unicode61` 的实测行为（本机 SQLite 3.51 验证）：

| 输入 | unicode61 默认切分 |
|---|---|
| `get_user_name` | `get` / `user` / `name` |
| `HTTPServer` | `httpserver`（**驼峰不拆**） |
| `foo()` | `foo` |
| `中文注释` | **整块一个 token** |

两个后果：

1. **标识符被切碎** → BM25 的词频与长度归一化都失真，
   `get_user_name` 这个整体概念被当成三个普通词。
   `tokenchars '_'` 让下划线标识符保持原子（用 `fts5vocab` 查词表可验证）。
2. **中文成巨型 token** → 中文 docstring 变成一个超长 term，
   BM25 的长度归一化会**系统性压低中文重的 chunk 的排名**。
   这会让 BM25 臂在对照实验里显得比实际更差——**污染实验结论**。
   所以中文走 jieba（纯 Python，无 C 扩展），与织忆现有依赖一致。

预分词让**入库与查询共用一套逻辑**，可以写单元测试保证口径一致；
代价是 `token_text` 体积约为 body 的 2–3 倍。

### 为什么用触发器而不是手工同步

- 触发器是**事务内原子**的。手工维护要在 insert / update / delete 三条路径各写一遍，
  最容易漏的是 delete —— 而那正是"文件删了 FTS 里残留旧行"的来源。
- 手工方案约 25–30 行分散代码；触发器方案 0 行应用层代码，
  代价是每条 chunk 插入多一次虚表写（全量 1e5 chunk 索引时间 +10% 量级，可接受）。
- 已在 `tests/test_schema.py` 覆盖 insert / update / delete 三条路径。

## 备选方案

| 方案 | 为什么不选 |
|---|---|
| 自研倒排索引 | 造轮子；持久化、增量、查询解析全要自己扛 |
| `rank_bm25`（纯 Python） | 中文分词要靠 jieba，语料规模上去后内存与速度都不划算；且没有持久化 |
| Elasticsearch | 要跑 JVM 服务，单机工具不值当 |
| contentless FTS5 表 | 增量更新后必须整体重建（1e4 chunk 约几十毫秒，可接受），但**失去增量**；触发器方案更好 |
| 不预分词，直接用 unicode61 | 中文巨型 token 污染 BM25 臂的对照结论；标识符被切碎 |

## 后果

- **得到的**：零依赖、持久化、增量更新天然支持；标识符原子；中文不污染排名；
  同步 bug 从"应用层三处代码"变成"数据库级保证"，且有回归测试。
- **失去的**：`token_text` 空间膨胀 2–3 倍；预分词逻辑必须与查询侧严格一致
  （由测试保证）；触发器让批量插入稍慢。
- **将来要付的**：若将来要支持**代码搜索语法**（正则、`field:value` 之类），
  FTS5 的查询语法需要适配。

## 重评条件

- 当 chunk 数超过 **1e6**、FTS 索引体积超过 2 GB 时，重评是否拆表或换引擎。
- 当需要**前缀匹配**（`get_user*`）时，FTS5 原生不支持，需另加一张前缀表——
  届时重评是否换成自研索引。
