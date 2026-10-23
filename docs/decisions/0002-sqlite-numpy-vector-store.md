# 0002. 向量存储用 SQLite + numpy 而非向量数据库

- **状态**：已接受
- **日期**：2026-10-23
- **影响范围**：`src/codeinsight/cognitive/retrieval/`、`storage/schema.sql`（`embedding` 表）
- **源文档**：§3.2 技术选型（向量存储一栏）

## 背景

源文档 §3.2 推荐 **ChromaDB / Qdrant** 做代码语义索引。

单人项目，本机运行，索引对象是**代码仓库**——不是百万级文档语料。
需要向量检索这件事本身是确定的，但"要不要一个向量数据库"取决于实际数据量与检索延迟要求。

如果不加抽象直接用 ChromaDB，将来换后端要动检索层代码。

## 决策

**向量以 float32 BLOB 存在 SQLite 的 `embedding` 表里**，检索时用 numpy 做**暴力余弦**。
检索层只暴露 `VectorStore` Protocol（`cognitive/retrieval/base.py`），换后端不动上层。

表结构：

```sql
CREATE TABLE embedding (
    chunk_id    INTEGER NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    model_id    TEXT NOT NULL REFERENCES embedding_model(model_id),
    vec         BLOB NOT NULL,      -- float32 LE
    text_sha256 TEXT NOT NULL,      -- 内容未变则复用向量
    PRIMARY KEY (chunk_id, model_id)
);
```

`model_id` 含维度（如 `bge-m3@1024`），**换模型即插新 model_id，不需迁移**；
旧行保留，可回滚。

## 理由

- **数据量**：一个中型 Python 仓库的 chunk 数在 1e3–1e5 量级。
  1e5 × 1024 维 × 4 字节 = 400 MB，numpy 暴力余弦在现代 CPU 上是**单次矩阵乘**，
  量级在几十毫秒。HNSW 的优势在这个规模上体现不出来。
- **少一个原生依赖**。ChromaDB 有原生层，织忆项目上出现过**全量测试随机 segfault**
  （在 chromadb 原生层，与业务代码无关）。索引服务不该有这类偶发崩溃。
- **事务一致**。向量与其他索引数据在同一个 SQLite 事务里更新，
  不会出现"chunk 改了但向量没改"导致检索结果与仓库不一致——
  这正是源文档 §3.1 第四层末句要求避免的。
- **可解释**：暴力余弦的排序结果是精确的，评测时不需要怀疑 ANN 的近似误差污染指标。

## 备选方案

| 方案 | 为什么不选 |
|---|---|
| ChromaDB | 原生依赖 + segfault 风险 + 本项目规模下 HNSW 无收益 |
| Qdrant | 要跑独立服务，单机本地工具引入一个常驻进程不划算 |
| FAISS | 原生依赖，同上；且与 SQLite 的事务一致性无从谈起 |
| pgvector | 要跑 PostgreSQL |
| 自己写 HNSW | 单人项目不该造这个轮子 |

## 后果

- **得到的**：零额外服务、零原生依赖、事务一致、检索结果精确可复现（评测友好）。
- **失去的**：超过百万 chunk 量级时暴力检索会明显变慢。
- **将来要付的**：向量占用随 chunk 数线性增长，超大仓库需要压缩
  （已规划：>2e4 chunk 时改 int8 量化 + 每行 scale，余弦误差 <0.5%）。

## 重评条件

- 当 chunk 数超过 **2e5**，或暴力余弦的 p99 延迟超过 **200ms** 时，重评换 Qdrant。
- 当需要**向量过滤检索**（如"只在 backend/ 下搜"）时，暴力实现其实更灵活，不构成理由。
- 当需要**多用户/多机共享索引**时，必须换（SQLite 文件锁撑不住）。
