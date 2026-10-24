# 0002. 索引引擎入口函数（POST /projects 的建索引接缝）

> **状态：✅ 已解决（2026-10-24）**。A 线合入 `cognitive/indexing.index_project`
> （按 `db_path + root + name + ref` 整-job 签名，自带 repo_state/index_run 记账），
> C 线已直接接线；本请求中建议的 `(conn, project_id, ...)` 签名未采用——
> 引擎侧签名更合理（名字复用语义与落库一致性都在引擎内闭环）。
> `symbol.path` 冗余列未加，读端点按 JOIN 实现。

- **提出方**：C 线
- **日期**：2026-10-24
- **紧急度**：阻塞"导入项目并建索引"真实跑通（读端点不受影响）
- **现状**：C 线已实现全部契约端点（`src/codeinsight/api/`），其中
  `POST /projects` 的异步建索引在 `api/indexing.py` 预留了引擎接缝；
  引擎缺席时 run 如实记 `failed`，不假装成功。

## 需要什么

A 线的落库索引器（规格 §1.2 A3/A4/A7，M1）落地时，暴露一个**入口函数**，
建议签名：

```python
def run_index(
    conn: sqlite3.Connection,
    project_id: int,
    root_path: str,
    ref: str | None,
) -> None:
    """扫描 → 解析 → 符号/边/切块落库 → repo_state 收尾（不含 index_run 记账）。"""
```

C 线在 `api/indexing.py::_ENGINE_CALLABLE` 一处接上即可，其余不动。

## 为什么是这个签名

- `conn` 由调用方传入：事务与 `index_run` 记账归 API 层，引擎只管数据；
- 不返回统计：写库后 C 线用 `COUNT(*)` 生成概览，避免两处口径漂移；
- 失败抛异常：`start_indexing` 已有 try/except 把异常记进 `index_run.stats_json`。

## 影响的调用点

- `src/codeinsight/api/indexing.py`（仅 `_ENGINE_CALLABLE` 赋值处）
- `POST /projects` → `GET /projects/{id}` 的 `status` 推导已按
  `index_run.finished_at/ok` 实现，引擎接入后无需改动。

## 附带确认

- `symbol` 表无 `path` 列（路径走 `file_id` JOIN）——C 线读端点已按此实现；
  若 A3 落库时愿意冗余一个 `symbol.path`，读写两边都能少一次 JOIN，
  但**不是必须**，请 A 线权衡后定。

---

## A 线答复与最终结论（2026-10-24）

引擎已落地，在 `src/codeinsight/cognitive/indexing/indexer.py`：

```python
def index_project(
    db_path: str | Path,
    *,
    root: str | Path,
    name: str,
    ref: str | None = None,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
) -> IndexResult:
    """建库 → 建项目行 → 全量索引 → 写 index_run 记账。"""
```

底层还有 `run_index(conn, project_id, root_path, ref)`——它只管数据、
不管记账，是 `index_project` 的内核。

### 最终采用 C 线的接法

C 线收敛后的写法是 **API 层直接调 `index_project`**，引擎自带全套记账
（`repo_state` + 成功路径的 `index_run`），API 只在引擎抛异常时补一条
`ok=0` 的 run。

**每次导入恰好一条 `index_run`**：

| 路径 | `index_run` 行数 |
|---|---|
| 成功 | 1（引擎写的） |
| 失败 | 1（API 层补的 `ok=0`） |

状态推导（`ORDER BY id DESC LIMIT 1`）始终只有一个来源 ✓。

> 顺带更正 A 线先前的一处担心：曾以为「引擎写一条 + API 补偿一条」会写成两条，
> 那是因为 API 层**事先**插了一条 run。C 线最终版本把那条预插去掉了，
> 所以没有重复。原先提的 `run_index(conn, ...)` 接缝因此不需要——
> 引擎仍然暴露它，但 API 不用。

### 集成时发现并修掉的一个真 bug

引擎原先会用 git origin URL **覆盖** `project.root_path`。
但 API 层的「同名同路径 = 重建索引」判定用的就是这一列——
覆盖之后，第二次导入同一个仓库会被误判成「同名不同路径」而拒掉（400）。

已改为：引擎**不覆盖**已有项目行的 `root_path`；
`project.root_path` 的语义统一为「这个项目指向哪个仓库（本地路径）」。
「公开仓库里不留本机绝对路径」这个顾虑落在**发布出去的东西**上：
索引库在 `.ci/` 里、被 gitignore；真正公开的是 `fixtures/sample-index.json`，
它的 `root_path` 由 `snapshot.py` 单独写成 git origin URL。

### 关于 `symbol.path`

**不加冗余列。** `symbol` 走 `file_id` JOIN 拿路径只有一次 JOIN，
而冗余一列意味着**两处可能不一致**（文件改名 / 增量更新时最容易漏）。
契约里 `symbol` 不带 `path` 字段也已经被前端接受——保持现状。
