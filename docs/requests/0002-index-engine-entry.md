# 0002. 索引引擎入口函数（POST /projects 的建索引接缝）

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

## A 线答复（2026-10-24）

引擎已落地，入口在 `src/codeinsight/cognitive/indexing/indexer.py`：

```python
def run_index(
    conn: sqlite3.Connection,
    project_id: int,
    root_path: str | Path,
    ref: str | None = None,
    *,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
) -> dict:
    """扫描 → 解析 → 落库 → repo_state 收尾（不含 index_run 记账）。"""
```

签名与请求里提的一致。`main` 上已把 `api/indexing.py::_ENGINE_CALLABLE`
接成 `run_index`，测试也改成了「真仓库 → ready 且库里有符号」。

### 合并时请保留 `run_index` 这条接缝

C 线工作区里有一版未提交的改法：让 API 直接调 `index_project`
（自己开库、自己写 `index_run`）。两种都能跑，但**记账会重复**：

| | `index_run` 行数（一次导入） | 谁负责记账 |
|---|---|---|
| `run_index`（本答复） | 1 | API 层 |
| 直调 `index_project` | 2（引擎一条 + API 失败补偿一条） | 两边都写 |

`GET /projects/{id}` 的状态是按 `index_run` 推导的（`ORDER BY id DESC LIMIT 1`），
多一行会让「这次索引到底成没成」的判断有两个来源。

所以合并冲突时以 `run_index(conn, ...)` 为准：
**连接与 `index_run` 记账归 API 层，引擎只管数据**——这也是请求里写的分工。
`index_project(db_path, ...)` 保留给 CLI 与测试用，它是 `run_index` 的薄包装。
