# 0006. 引用信息与文本内容分离

- **状态**：已接受
- **日期**：2026-10-23
- **影响范围**：`agent/tool.py`（`ToolResult.content` / `ToolResult.data`）、
  `models.py`（`Evidence`、`Citation`）
- **源文档**：§2.3-4「将解释关联到实际文件与代码位置」、§3.2「上下文管理」

## 背景

源文档 §2.3-4 要求把解释关联到实际文件与代码位置。
同时 §3.2 要求「上下文管理」——工具结果不能无限进模型上下文，必须截断。

这两件事会打架：**如果 `file:line` 只存在于工具结果的文本里，截断文本就可能把引用截掉。**
结果是模型"引用了一个不存在的行号"或者干脆没有引用——而引用是本项目的诚实性开关。

如果不处理，代码里最自然的写法就是把 `path:line` 拼进 content 字符串，
截断逻辑一加，引用就开始随机丢失。

## 决策

**把引用信息放在结构化字段里，与给模型看的文本分开。**

```python
@dataclass(frozen=True)
class ToolResult:
    content: str          # 给模型看的文本（可能被截断）
    data: dict[str, Any]  # 结构化数据（不进模型上下文）
    truncated: bool = False
    error: str | None = None
```

```python
@dataclass(frozen=True)
class Evidence:
    chunk_id: int
    path: str
    lineno: int
    end_lineno: int
    qualname: str | None
    snippet: str
    score: float = 0.0
    lanes: tuple[str, ...] = ()
    concept_ids: tuple[str, ...] = ()
```

`data` 里的 `path` / `lineno` **不参与截断**。模型看到的 `content` 里的引用标记
由 `data` 生成，因此截断 `content` 不会破坏引用的完整性。

## 理由

- **引用是硬要求，不是装饰**。§2.3-6 要求区分"可验证的代码事实"与"模型推断"，
  而"可验证"的判定依据就是引用。引用丢了，诚实性开关就失效了。
- **结构化数据还有别的用处**：前端要拿 `file:line` 渲染可点击的证据面板、
  评测要拿它算 `citation_precision`、`stale_cite_rate` 要拿它比对内容哈希。
  这些都不该从模型上下文里的自由文本里正则抽取。
- **这是从织忆学到的**（见 `docs/ported-from-tapestry.md`）：那边踩过的坑是
  "工具结果同时进记录和事件流，两处若截断不一致，就会出现账本里有、模型没看到"。
  同一个道理，这里是"文本被截断、但引用不能丢"。

## 备选方案

| 方案 | 为什么不选 |
|---|---|
| 引用只写在 content 文本里 | 截断即丢引用；前端与评测都要正则解析自由文本，脆 |
| 截断时保护引用（正则识别行号并保留） | 靠正则识别代码位置本身就不可靠；且 content 被保护的部分可能超预算 |
| 不截断工具结果 | 违背 §3.2 上下文管理；大文件一次就能撑爆窗口 |
| 引用放在 system prompt | 与具体证据脱钩，无法定位到"这条事实对应哪段代码" |

## 后果

- **得到的**：截断不破坏引用；前端、评测、Agent 三方共用同一份结构化证据。
- **失去的**：每个工具都要同时产出 content 与 data，编写成本略高。
- **将来要付的**：模型看到的 content 与前端显示的 data 必须保持语义一致，
  需要在构造 `content` 时从 `data` 生成，而不是各写各的。

## 重评条件

- 当模型开始频繁"引用了 data 里没有的行号"（说明 content 与 data 脱节）时，
  改为**由 data 自动生成 content**，禁止手写 content。
