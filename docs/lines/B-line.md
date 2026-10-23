# B 线 · 知识探索 · 开工包

> **源文档 §2.6 项目关联知识探索 / §5-4 项目与技术知识双向关联 / §3.1 第三层「知识点关联检索」**
>
> 这是 CodeInsight 的**核心支柱之一**，不是可选功能。源文档在八处提到它
> （标题、定位句、§1.1 痛点、§1.3 目标、§3.1 四层、§4.3 工作流、§5-4 创新点、§10 成果）。

---

## 0. 开工前

```bash
cd <仓库根>-wt-knowledge
git branch --show-current     # 必须是 feat/knowledge
git log --oneline -1
```

**按顺序读**（别跳）：

1. [`../../AGENTS.md`](../../AGENTS.md) —— 作业规程
2. [`../functional-spec.md`](../functional-spec.md) 的 **「## 2. B 线」** —— 你的实现需求
3. [`../decisions/0011-concept-ontology-is-curated.md`](../decisions/0011-concept-ontology-is-curated.md) —— 本体为什么是手工策展的
4. [`../decisions/0007-facts-vs-inferences.md`](../decisions/0007-facts-vs-inferences.md) —— 输出怎么分栏
5. [`../workspace.md`](../workspace.md) —— 三线怎么协作

---

## 1. 你的车道（只有你能写）

```
src/codeinsight/cognitive/concepts/     ontology.py  detector.py  explain.py
knowledge/concepts/                     *.yaml，一个概念一个文件
```

**其他所有目录只读。** 要改 → 写 `docs/requests/NNNN-xxx.md` 提给主线。

---

## 1.5 开工前要跟用户对齐的事

**这些不要自己拍板。** 开工时把下列问题摆给用户，给出你的推荐和理由。

| # | 要对齐的 | 为什么必须问 |
|---|---|---|
| **B-Q1** | **20 个概念具体选哪 20 个** | 选哪些概念 = 产品定位。开工包里的清单是**建议**，用户可能有偏好（比如他最关心并发或缓存） |
| **B-Q2** | 每个概念的**文案详细程度** | 太短则"深入探索"没内容，太长则 20 个概念要写 40 小时。用户能接受多少投入？ |
| **B-Q3** | `tradeoffs` 用不用**模板句式** | 有模板 → 质量一致、写得快；但可能千篇一律。自由写 → 质量高、慢 |
| **B-Q4** | 检测规则**宁松还是宁严** | 宁松 → 召回高但噪声多；宁严 → 准确但可能漏。用户的验收标准是"准确率 ≥ 0.8"，据此定宽严 |
| **B-Q5** | `string_markers` 要不要 | 覆盖最广但最脏（靠字符串猜概念）。用户可能不接受"靠字符串就认定用了某技术" |

> **推荐**：B-Q1 先问（定清单再写）；B-Q2~Q5 可以带着默认值开工，
> 在写完前 2 个概念后拿样例给用户看效果再定。

**问不到用户时**：按开工包里的建议清单与默认详细度执行，
在 ADR 里标注"未与用户确认"，提交信息写 `决策：概念清单用建议版（未对齐，理由：…）`。

---

## 2. 今天的第一件事：写 20 个概念本体

**零依赖，现在就能干完。**

文件：`knowledge/concepts/<id>.yaml`
格式：**规格 §2.1 有完整 YAML 示例 + 6 个 detection 规则键 + category 枚举**，照着写。

建议的概念清单（可自行调整，但保证覆盖面）：

```
jwt            session          redis-cache     db-transaction  connection-pool
orm            async            thread-pool     dependency-injection
config-env     structured-logging retry-idempotency rate-limit
file-lock      context-manager  decorator       generator        abstract-base
singleton-lazy event-bus
```

### 硬要求

| 要求 | 原因 |
|---|---|
| 每个概念必须有 `summary`（2–3 句） | 「快速理解」这一级**不调 LLM**，直接读它 |
| `tradeoffs` **必须写**，不能留空 | 这是每个概念最值钱的部分——「为什么存在、代价是什么」 |
| `principles` / `alternatives` 尽量写 | 「深入探索」这一级的内容 |
| `detection` 只用规格列的 6 个键 | 检测器只认这 6 类 |
| `id` 小写 kebab-case、全局唯一 | 本体是索引的键 |
| `category` 从枚举里选 | — |

### 禁止

- ❌ **不手工维护「概念 → 代码位置」映射表。**
  位置由 `detection` 规则在符号/关系索引上**自动派生**——代码改了重跑检测即同步。
  （这条是 ADR 0011 的核心，也是我最初误判的地方，别重蹈。）
- ❌ 不复制外部教材/百科的文本。定义、原理、权衡要自己写。

---

## 3. 今天的第一件事（并行）：检测器

文件：`src/codeinsight/cognitive/concepts/detector.py`

```python
class RuleBasedDetector(ConceptDetector):
    def detect(self, symbols: Sequence[SymbolView], edges: Sequence[EdgeView]) -> list[ConceptInstance]
```

- 逐条规则在 `SymbolView` / `EdgeView` 上跑，产出 `ConceptInstance`。
- **`evidence` 必须写清命中了什么**：`import jwt` / `decorator @app.get` /
  `call redis.Redis` / `inherits Base`。
- `confidence` < 1 表示推断出来的（例：`string_markers` 命中 → 0.7）。
- **测试自己造小的 `SymbolView` / `EdgeView` fixture 起步**，
  不要等主线的 `fixtures/sample-index.json`（可能几小时后才有）。

规则键 → 匹配对象（规格 §2.1 有表）：

| 键 | 匹配什么 | 边的 kind |
|---|---|---|
| `import_names` | 被导入的模块名 | `imports` |
| `call_names` | 被调用的名字 | `call` |
| `attribute_names` | 属性名 | `references` |
| `decorator_names` | 装饰器名 | `decorator` |
| `base_classes` | 基类名 | `inherits` |
| `string_markers` | 源码字符串 | 源码匹配 |

> ⚠️ `attribute_names` 与 `string_markers` 依赖 A 线的边数据。
> 如果 A 线还没产出 `references` 边，**提一个 `docs/requests/`**，
> 不要自己去改 `indexing/edges.py`。

---

## 4. 后续任务

| 顺序 | 任务 | 规格位置 |
|---|---|---|
| 4 | `concepts/ontology.py` —— 加载 + **校验**（必填字段、id 唯一、category 合法、detection 键合法）。**校验失败要报错，不静默跳过** | §2.2 |
| 5 | `concepts/explain.py` —— 三级深度 | §2.4 |
| 6 | 供检索层用的「概念 → 实例」查询 | §2.5 |
| 7 | M5：concept 臂 + 人工 gold set（30 个「概念→实例」对，算 P/R/F1） | §2.6 |
| 8 | M6：设计说明过期检测的概念侧（`design_decision.claims_json` vs `concept_instance`） | §2.7 |

### 三级深度速查

| 深度 | 内容 | 调 LLM？ | 延迟 |
|---|---|---|---|
| `quick` | 概念是什么、用途 | **不调**，读本体 `summary` | 瞬时 |
| `project` | 本项目的实现位置 + 执行方式 + **与其他模块的关系** | 轻量串场 | <1s |
| `deep` | 原理 + 设计权衡 + 其他实现方式 + 与现有代码的联系 | 调 | 可慢 |

`project` 级的「位置/执行方式/调用关系」**全部从索引自动派生**，不是 LLM 猜的。

---

## 5. 验收

- [ ] 20 个 YAML 全部通过 `load_ontology()` 的校验
- [ ] 每个 `ConceptInstance` 都有 `evidence`
- [ ] 人工核对：对织忆 `agent-v1` 跑一遍，实例准确率 **≥ 0.8**
- [ ] `quick` 级解释**不触发任何 LLM 调用**（要有测试证明）
- [ ] `deep` 级输出**分 facts / inferences**，facts 带 `file:line`

---

## 6. 交回主线

- 提交信息用中文，格式 `feat: 做了什么`，正文写动机。
- `git commit` 可以直接做；**`git push` 必须等用户明确说。**
- 主线会每天把 `main` 合回你的分支——**合之前先 `git status` 确认干净**。
