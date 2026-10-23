# 0007. 事实与推断分开存放

- **状态**：已接受
- **日期**：2026-10-23
- **影响范围**：`models.py`（`Answer.facts` / `Answer.inferences`）、Agent 输出层
- **源文档**：§2.3-6「**区分可验证的代码事实与模型推断**」

## 背景

源文档 §2.3-6 把"区分可验证的代码事实与模型推断"列为智能问答的六个特点之一。

一个 Agent 回答"这个函数为什么这么设计"时，答案里天然混着两类内容：

- **事实**：`classify_action` 在 `backend/agent/permissions.py:29`，它接收
  `permission_tier / tool_name / annotations / arguments`，返回
  `{requires_approval, always_confirm, safe_read, open_world, reason}`。
  这些都能在代码里查到。
- **推断**："它这样设计是为了让审批粒度可审计。"——这是模型的理解，
  代码里**没有**这句话，写它的人也没这么说过。

如果两者混在一段自然语言里，用户无法分辨哪句可以信。
在评测上也无法区分"答对了"与"编得像"。

## 决策

**输出结构分两栏：`facts[]` 与 `inferences[]`。**

```python
@dataclass
class Answer:
    text: str = ""
    facts: list[dict[str, Any]] = field(default_factory=list)      # 每条必须有 citation
    inferences: list[str] = field(default_factory=list)             # 显式标注为推断
    citations: list[Citation] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    abstained: bool = False
    abstention_reason: str = ""
```

规则：
1. `facts` 里的每一条**必须**指向一个 `Citation`（`path:line`）。
2. `inferences` 里的每一条**必须**显式标注为推断，前端与 API 都要区分显示。
3. 检索**无命中**时，`abstained=True` 并给出 `abstention_reason`——
   **不允许模型编造 `file:line`**。
4. 评测指标 `citation_precision` 直接基于 `facts` 与 `citations` 计算，
   不从自由文本里正则抽取。

## 理由

- 这是源文档的直接要求，不是我加的。
- **它让"引用证据准确率"这个指标变得可测**（§6「项目问答质量：回答正确率、
  引用证据准确率」）。没有分栏，指标就只能靠正则抽 `path:line`，
  抽到的可能是模型编的，也可能是真事实，分不开。
- **它让"诚实弃答"成为一个可判定的事件**。`abstained` 是布尔值，
  可以直接进评测表（`abstain_rate` 也是一个值得报告的指标——
  一个从不弃答的系统和一个适当弃答的系统，可信度完全不同）。
- 这与织忆的 **evidence 机制**是同构的：那边是"模型要记录用户事实，须提供用户原话证据，
  证据不匹配则拒绝写入"。这里是"模型要陈述代码事实，须提供 `file:line` 证据"。

## 备选方案

| 方案 | 为什么不选 |
|---|---|
| 一段自然语言，靠提示词要求模型自己标注 | 无法验证标注是否属实；评测只能正则抽取 |
| 只保留引用，不分栏 | 用户仍分不清"这个函数是这样实现的"与"它大概是想这么做的" |
| 让模型输出 JSON schema 强制分栏，但不做校验 | schema 挡不住"事实里塞推断"，需要落库时校验 |
| 不做弃答，总是给答案 | 检索无命中时模型只能编；这正是要防的失败模式 |

## 后果

- **得到的**：诚实性可判定；问答质量可测；用户能区分可信与不可信。
- **失去的**：输出格式更复杂；提示词要更长；模型偶尔会过度保守（把事实标成推断）。
- **将来要付的**：需要在落库时**校验** `facts` 的每条都有 citation，
  校验不过就降级为 inference——这条校验规则要写进 M3。

## 重评条件

- 当 `citation_precision` 长期 >0.95（模型基本不会犯事实错误）时，
  可以把分栏做成**默认折叠**而不是强制显示，简化界面。
- 当评测显示模型的推断被用户大量当作事实误解时，
  需要加强标注措辞（但**不能取消分栏**）。
