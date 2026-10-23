# 工作区文档 · 三线并行怎么协作

> 本文讲的是**物理环境与协作规矩**：三条线各在哪、谁能动什么、怎么合、卡住了找谁。
> 功能需求在 [`functional-spec.md`](functional-spec.md)，阶段在 [`roadmap.md`](roadmap.md)。

---

## 1. 一句话

同一个仓库，**三个 worktree、三个分支、三条线并行**。
`main` 是集成分支，**只有 A 线能合**。

---

## 2. 物理布局

```
<仓库根>                 main             A 线（索引+检索+Agent+MCP+集成）
<仓库根>-wt-knowledge    feat/knowledge   B 线（知识探索）
<仓库根>-wt-frontend     feat/frontend    C 线（前端+API）
```

- 三个目录是**同一个 Git 仓库的三份检出**（`git worktree`），共享同一份对象库。
  在任一目录提交，另一个目录**看得到那个 commit**（对象共享），但工作区互不影响。
- 三条线的**起点一致**：`9d8a145`。
- 查看当前布局：`git worktree list`（在任一目录执行）。

### worktree 的三个坑

| 坑 | 说明 | 怎么办 |
|---|---|---|
| 同一个分支不能在两个 worktree 同时 checkout | git 会直接拒绝 | 每个 worktree 一个分支，不要 `git checkout main` |
| 在 worktree 里跑 `git worktree remove` 会删掉那个目录 | 目录里未提交的改动会丢 | 先 `git status` 确认干净 |
| `git gc` / `git prune` 在别的 worktree 有未提交改动时可能误伤 | 极少发生 | 不手动 gc |

---

## 3. 三条线的车道

| 线 | 分支 | 目录 | 负责的源文档章节 |
|---|---|---|---|
| **A 线** | `main` | `cognitive/{parsing,indexing,retrieval,embedding}/`、`agent/`、`llm/`、`execution/`、`storage/`、`eval/`、`models.py`、`config.py`、`cli.py`、`docs/` | §2.1 §2.2 §2.3 §2.4 §2.5 §5 §6 |
| **B 线** | `feat/knowledge` | `cognitive/concepts/`、`knowledge/concepts/` | **§2.6** §5-4 |
| **C 线** | `feat/frontend` | `frontend/`、`src/codeinsight/api/` | §3.1-1 §2.1-UI |

### 开工包

每条线的工作目录里都有一份"开工包"，**agent 只需要打开自己那一份**：

| 线 | 开工包 |
|---|---|
| A 线 | [`lines/A-line.md`](lines/A-line.md) |
| B 线 | [`lines/B-line.md`](lines/B-line.md) |
| C 线 | [`lines/C-line.md`](lines/C-line.md) |

### 目录所有权规则

> **一个目录只有一个 agent 能写。** 这是三线并行不打架的根本保证。

越界了怎么办：**不要直接改**。在 `docs/requests/` 下加一个文件写清
「要 X 改 Y 的什么、为什么」，由 A 线统一改并同步三条线。

```bash
# 例：需要 models.py 加一个字段
cd <仓库根>-wt-knowledge
# 写 docs/requests/0001-add-symbol-kind-to-evidence.md
```

### 契约文件（只读）

| 文件 | 内容 | 谁提供 |
|---|---|---|
| `src/codeinsight/models.py` | 领域模型 | A 线冻结 |
| `src/codeinsight/storage/schema.sql` | 数据契约 | A 线冻结（M1 补两张表） |
| `src/codeinsight/config.py` | 配置项 | A 线冻结 |
| `docs/api-contract.md` | API + SSE 契约 | A 线本周补 |
| `frontend/src/api/types.ts` | 前端类型 | A 线本周补 |
| `fixtures/sample-index.json` | 真实索引样例 | A 线本周补 |

---

## 4. 每个 agent 的启动检查清单

开工前照着走一遍：

```bash
cd <你的 worktree>
git branch --show-current      # 确认在自己分支上
git log --oneline -1           # 确认起点
uv sync --extra dev            # A 线需要（Python）
```

然后读：

1. `AGENTS.md`（根目录，作业规程）
2. `docs/functional-spec.md` 的**自己那一节**
3. `docs/decisions/` 里与自己相关的 ADR
4. `docs/workspace.md`（本文）

---

## 5. 每天的节奏

| 时机 | 谁 | 做什么 |
|---|---|---|
| 开工 | 各线 | 在自己分支提交，改动只在自己的目录 |
| 收工 | A 线 | 把 `feat/knowledge` / `feat/frontend` 合进 `main`，跑全量测试 |
| 有契约变更 | 提出方 | 写 `docs/requests/NNNN-xxx.md`，A 线统一改 |
| 每周 | 全部 | 三线对齐：各自 demo + 说清下一步依赖 |

### main 的规矩

- **只有 A 线能合 main。**
- 合之前 `pytest` + `ruff` 必须全绿。**测试红 = main 红 = 谁都别想推。**
- 合的功能分支合进 main 后，**要合回各 feature 分支**（否则 feature 分支会落后，
  下次合并时把别人的改动覆盖掉）：

```bash
cd <仓库根>
git checkout main && git merge feat/knowledge && git merge feat/frontend
git push origin main

# 回灌到各 feature 分支
cd <仓库根>-wt-knowledge && git merge main
cd <仓库根>-wt-frontend  && git merge main
```

---

## 6. 冲突会出现在哪，怎么解

| 冲突类型 | 出现条件 | 解法 |
|---|---|---|
| **同文件同时改** | 越界改了别人的目录 | 谁都不改契约文件；提 `docs/requests/` |
| **接口不匹配** | A 线改了函数签名，另一边按旧签名写的 | 契约变更必须走 `docs/requests/`，**不能口头说** |
| **git 合并冲突** | 两侧改了同一文件的同一段 | 目录所有权正常时**不该发生**。发生了说明越界了——回退到正确的目录归属 |
| **schema 不一致** | B 线需要的字段 A 线没给 | A 线加字段（向后兼容），B 线等；不要 B 线自己改 schema |
| **测试互相影响** | 共用 `tests/conftest.py` | 各线写自己的测试目录，文件名不重名；`conftest.py` 由 A 线维护 |

---

## 7. 提交与推送

- **提交信息用中文**，格式：`类型: 做了什么`，正文说明动机与影响。
  例：`feat: 概念检测器支持 import_names 与 call_names 两类规则`
- **`git commit` 可以直接做；`git push` 必须等用户明确说。**（本项目约定）
- 各 feature 分支推到远程只为了备份与审阅，推之前同样要打招呼。
- 远程：`https://github.com/cyh710/Codeinsight.git`（public）

---

## 8. 环境

| 项 | 值 |
|---|---|
| Python | 3.13+ |
| 包管理 | `uv`（`uv sync --extra dev`） |
| 前端 | Node 24 / npm 11，依赖与织忆一致（+ Monaco + React Flow） |
| 数据库 | SQLite（WAL），索引库在 `.ci/codeinsight.db`（gitignore） |
| 密钥 | 只走环境变量 `CI_*` 前缀，**不入库不入日志** |

### 常用命令

```bash
uv run pytest -q                 # 全量测试
uv run ruff check .              # lint
uv run ruff format .             # 格式化
uv run ci init-db                # 建索引库
uv run ci where                  # 看本地路径
```

---

## 9. 卡住了怎么办

| 情况 | 找谁 / 怎么办 |
|---|---|
| 需要改契约 | 写 `docs/requests/NNNN-xxx.md` → A 线 |
| 需要别的线的数据 | 提需求要 **fixture 或接口**，不要直接读对方的库 |
| 想法与源文档冲突 | **以源文档为准**；确实要改，先写 ADR |
| 源文档没覆盖的空白 | 写 ADR 记录决策，再写代码 |
| 三个方向都不确定 | 停下来问用户，不要各自发挥 |

---

## 10. 一条底线

> **三个 agent 写出来的代码，最终署同一个名。**
>
> 所以：宁可多写一条 ADR 说明为什么这么做，也不要留一段"只有作者自己看得懂"的代码。
> 注释解释**为什么**，不解释**是什么**。
