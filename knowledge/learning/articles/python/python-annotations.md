# 类型注解：把接口约定写出来

## 注解写在函数上，但不会拦住谁 {#overview}

类型注解写给读代码的人和静态检查工具看，运行时的 Python 不会替你检查。读完这一篇，你能给函数和容器写注解，也知道它拦不住什么。

小林写了一个求总和的函数，注解说参数是"带 amount 键的字典列表"：

```python
def total(expenses: list[dict[str, float]]) -> float:
    return sum(item["amount"] for item in expenses)


print(total([{"amount": 12.5}, {"amount": 35.5}]))
print(total([12, 35]))
```

第一次调用输出 `48.0`，第二次在运行时报错：

```
TypeError: 'int' object is not subscriptable
```

注解并没有在调用时拦住 `[12, 35]`。Python 照常进入函数，直到执行 `item["amount"]` 才发现整数不能这样取键。传参的地方和报错的地方隔了好几行，排查时得往回找。

注解的作用是**把类型约定写出来**：给读代码的人看，给编辑器看，给 mypy 这类静态工具看。它不是运行时的守卫。

## 一个带注解的函数长什么样 {#syntax}

给小林记一笔开支的函数加上注解：

```python
def add_expense(name: str, amount: float, tags: list[str] | None = None) -> str:
    tag_text = ",".join(tags) if tags else "无"
    return f"{name} {amount:.2f} [{tag_text}]"


print(add_expense("午饭", 18))
print(add_expense("打车", 26.5, ["交通", "雨天"]))
```

```
午饭 18.00 [无]
打车 26.50 [交通,雨天]
```

参数名后面的冒号写输入类型，箭头写返回类型，这几部分要分开理解：

- `name: str` 表示这个参数应该是字符串。
- `amount: float` 表示这个参数应该是浮点数。mypy 对 `int` 传给 `float` 参数是放行的，运行时整数和浮点数也本来就能一起运算。
- `tags: list[str] | None` 表示它要么是字符串列表，要么是 `None`。
- `= None` 是默认值，表示调用时可以省略这个参数。类型和默认值是两件事：前者说"允许什么值"，后者说"不传时用什么"。
- `-> str` 表示函数交回一个字符串。

返回注解不是给 `return` 语句加类型，而是对调用方的承诺。读到一个陌生函数，先看签名，就能知道该传什么、会拿回什么、哪些参数可以不传。

注解默认在函数或类定义时求值。类要引用自己的类型时，这条规则会撞墙：

```python
class Node:
    def __init__(self, value: int, next: Node | None = None) -> None:
        self.value = value
        self.next = next
```

```
NameError: name 'Node' is not defined
```

执行 `def __init__` 这一行时，Python 要先算出 `Node | None`，可 `Node` 这个类还没建完。在文件最上方加上 `from __future__ import annotations`，同一段代码就能跑：

```python
from __future__ import annotations


class Node:
    def __init__(self, value: int, next: Node | None = None) -> None:
        self.value = value
        self.next = next


print(Node(1).value)
```

```
1
```

这个导入让当前模块的注解以字符串形式保存，等工具需要时再解析，定义时不再求值。它同时解决了自引用和部分循环导入问题。`from __future__` 必须放在文件开头（文档字符串之后），只影响当前模块；它改变的是注解怎么存，不改变"注解默认不检查运行时"这件事。

## Optional、联合类型与容器注解 {#optional-union}

"查得到就返回名字，查不到返回空"是常见需求。返回类型要把"空"写进去，否则调用方会以为一定有字符串：

```python
def find_amount(name: str, ledger: dict[str, float]) -> float | None:
    return ledger.get(name)


amount = find_amount("午饭", {"午饭": 18.0})
if amount is not None:
    print(f"花了 {amount:.2f} 元")
print(find_amount("打车", {"午饭": 18.0}))
```

```
花了 18.00 元
None
```

`float | None` 的读法是"float 或者 None"。Python 3.10 起可以直接用 `|` 拼联合类型；更早的代码常见 `Optional[float]`，意思完全一样，需要先 `from typing import Optional`。

找到值以后，先用 `is not None` 排除空值，再调用 `amount` 的方法或格式化。这个检查在业务上也必要：`None` 不会自动变成 0，拿它做算术或按金额格式输出会直接报错。

容器的注解分两层：容器本身，和里面装的东西。

| 注解 | 含义 |
| --- | --- |
| `list[str]` | 字符串列表 |
| `dict[str, float]` | 键是字符串、值是浮点数的字典 |
| `set[int]` | 整数集合 |
| `tuple[str, int]` | 固定两个元素：字符串和整数 |
| `dict[str, list[float]]` | 值是浮点数列表的字典 |

只写 `list` 或 `dict` 也能运行，但等于告诉检查工具"里面的东西我不知道"，后续访问就失去保护。越靠近数据的边界，越应该把元素类型写出来。

函数什么都不返回时，写 `-> None`：

```python
def show(amount: float) -> None:
    print(f"¥{amount:.2f}")


show(18)
```

```
¥18.00
```

`-> None` 是明确声明"这个函数不交回有用的值"。不写返回注解，检查工具默认按"未知"处理，既不会要求你返回什么，也发现不了你漏写 `return`。

## 让 mypy 替你读一遍 {#mypy}

mypy 是第三方工具，Python 不自带。先装：

```bash
python -m pip install mypy
```

新建 `ledger.py`：

```python
def label(amount: int) -> str:
    return "¥" + str(amount)


print(label("12"))
```

先直接运行：

```bash
python ledger.py
```

```
¥12
```

`str(amount)` 什么都能接收，注解写着 `int` 也照跑不误。现在让 mypy 检查：

```bash
python -m mypy ledger.py
```

```
ledger.py:5: error: Argument 1 to "label" has incompatible type "str"; expected "int"  [arg-type]
Found 1 error in 1 file (checked 1 source file)
```

第 5 行指向 `print(label("12"))` 这次调用。mypy 没有执行代码，它读签名、读调用点，发现传入的是 `str`，而声明要 `int`。`[arg-type]` 是错误代码，方便你在配置里单独处理这一类问题。

把 `"12"` 改成 `12` 再跑：

```bash
python -m mypy ledger.py
```

```
Success: no issues found in 1 source file
```

mypy 只能检查它看得懂的部分。没有注解的函数，参数和返回值默认按 `Any` 处理，里面传错也不会报。注解覆盖得越多，检查才越有用。项目里如果没人运行这个命令，注解就只对读者和编辑器补全有帮助，合并代码前拦不住任何错误。

## 注解不转换数据 {#no-conversion}

注解是声明，不是转换。下面这段从 JSON 读出来两个字符串，函数却声明要整数：

```python
import json


def add(a: int, b: int) -> int:
    return a + b


data = json.loads('{"a": "12", "b": "30"}')
print(add(data["a"], data["b"]))
```

```
1230
```

`json.loads` 返回的是 `str`，`+` 执行的是字符串拼接。函数没有把 `"12"` 转成 12，注解也没有。要得到 42，得自己转：

```python
import json


def add(a: int, b: int) -> int:
    return a + b


data = json.loads('{"a": "12", "b": "30"}')
print(add(int(data["a"]), int(data["b"])))
```

```
42
```

`typing.cast` 也不转换。它只是告诉检查工具"相信我，这里是这个类型"：

```python
from typing import cast

raw = "12"
value = cast(int, raw)
print(type(value).__name__)
print(value + 1)
```

输出是：

```
str
TypeError: can only concatenate str (not "int") to str
```

`value` 还是那个字符串，`cast` 没有碰它。真正会检查运行时类型的是 `isinstance`：

```python
def add(a, b):
    if not isinstance(a, int) or not isinstance(b, int):
        raise TypeError("a 和 b 必须是整数")
    return a + b
```

JSON、表单、环境变量、数据库行这些边界上的数据，先转换和校验，再交给带注解的函数。类型检查通过，只说明代码里的形状对得上，不说明外部数据一定合法。

## Any、Optional 与错误的返回类型 {#pitfalls}

**"`Any` 只是临时占个位，用多了没关系。"** `Any` 会关掉这一条路径上的检查，而且会往下游扩散：

```python
from typing import Any


def load() -> Any:
    return "12"


value = load()
print(value + 1)
```

mypy 对这段代码说：

```
Success: no issues found in 1 source file
```

运行时却说：

```
TypeError: can only concatenate str (not "int") to str
```

`json.loads`、`dict.get` 的某些用法、没注解的第三方库都会返回 `Any`。在边界上接收 `Any` 可以，但应该尽快转成具体类型或做校验，不要让 `Any` 一路流进业务代码。

**"`Optional[str]` 表示这个参数可以不传。"** 它只表示值可能是 `None`，跟"能不能省略参数"是两回事。省略由默认值决定：

```python
def greet(name: str | None = None) -> str:
    if name is None:
        return "你好，陌生人"
    return f"你好 {name}"


print(greet())
print(greet("小林"))
```

```
你好，陌生人
你好 小林
```

写成 `name: str | None` 但不给默认值，调用时仍必须传一个参数，只是可以传 `None`。两个都要，才既允许省略、又允许空值。

**"返回值可能为空，注解写 `str` 就行，调用方自己注意。"** 检查工具会相信注解，调用方也会。把这段存成 `none_demo.py`：

```python
def find(ledger: dict[str, str], key: str) -> str:
    return ledger.get(key)


print(find({"午饭": "食堂"}, "打车").upper())
```

mypy 报错：

```
none_demo.py:2: error: Incompatible return value type (got "str | None", expected "str")  [return-value]
Found 1 error in 1 file (checked 1 source file)
```

运行时则是：

```
AttributeError: 'NoneType' object has no attribute 'upper'
```

把返回类型改成 `str | None`，再在调用方检查：

```python
def find(ledger: dict[str, str], key: str) -> str | None:
    return ledger.get(key)


name = find({"午饭": "食堂"}, "打车")
if name is not None:
    print(name.upper())
else:
    print("没找到")
```

```
没找到
```

返回值有空洞，就要在签名里承认它。硬写一个更窄的类型，只是把错误推迟到运行时。

## 什么时候值得写注解 {#when-to-annotate}

**跨模块的函数、公开方法、会被别人调用的接口，值得写完整注解。** 读代码的人不用猜参数形状，编辑器能补全，检查工具能在改调用时发现不一致。

**数据结构在几个函数之间传来传去时，给形状起个名字。** 比如账单是 `dict[str, float]`，与其在每个签名里重复，不如写清楚一次，让读者一眼知道它长什么样。重复的复杂类型可以先用类型别名收住。

**一次性脚本、只有三行的局部辅助函数，可以先不写。** 如果注解比函数体还长，而且没有第二个调用方，阅读成本大于收益。等它被第二处调用，或者开始接收外部数据，再补。

**注解要有检查工具执行才算数。** 编辑器里开着 mypy 或 pyright，写代码时就能看到标红；CI 里跑同样的命令，才能拦住合并。只在仓库里堆注解、从不运行检查，注解就退化成文档。

**只承诺你能保证的类型。** 可能返回空就写 `| None`，可能抛异常就在文档里说，不要为了签名好看把 `None` 藏起来。`Any` 是边界上的临时工具，不是省事的默认值。

类型检查擅长发现"形状和调用对不上"，测试擅长验证"业务算得对不对"。一个函数可以类型完全正确，却把折扣算反；也可以逻辑正确，却在某个分支返回了 `None`。两者不能互相替代。

## 三个类型判断题 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这段运行会打印什么？mypy 会怎么说？

```python
def double(x: int) -> int:
    return x * 2


print(double("3"))
```

> **答案**
>
> 运行打印 `33`。`"3" * 2` 是字符串重复，不是数字乘法。
>
> mypy 会报 `Argument 1 to "double" has incompatible type "str"; expected "int"`。注解没有在运行时拦住字符串，工具只是在静态检查时发现了它。

**第 2 题**：这个函数的返回注解哪里不对？给出修好的版本，并说明调用方要做什么。

```python
def find(ledger: dict[str, float], name: str) -> float:
    return ledger.get(name)
```

> **答案**
>
> `dict.get` 在键不存在时返回 `None`，所以实际返回类型是 `float | None`，不是 `float`。mypy 会报 `Incompatible return value type`。
>
> ```python
> def find(ledger: dict[str, float], name: str) -> float | None:
>     return ledger.get(name)
> ```
>
> 调用方拿到结果后要判断：
>
> ```python
> amount = find({"午饭": 18.0}, "打车")
> if amount is None:
>     print("没记过这笔")
> else:
>     print(f"花了 {amount:.2f} 元")
> ```

**第 3 题**：JSON 里是 `{"amount": "18"}`，函数声明 `amount: float`。为什么 `amount` 不会自动变成数字？写一段安全转换的代码。

> **答案**
>
> 注解只在静态检查时描述类型，运行时不会执行转换。`json.loads` 按 JSON 里的字面量给出字符串，`amount` 就是 `str`。
>
> ```python
> import json
>
> raw = json.loads('{"amount": "18"}')
> try:
>     amount = float(raw["amount"])
> except (TypeError, ValueError):
>     raise ValueError("amount 必须是数字") from None
>
> print(amount)
> ```
>
> ```
> 18.0
> ```
>
> 转换失败时抛业务错误，比让字符串一路流到计算里更容易定位。需要保留原始异常时，把 `except (TypeError, ValueError):` 改成 `except (TypeError, ValueError) as exc:`，再把 `from None` 换成 `from exc`。

## 类型之后读什么 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [列表、元组、字典与集合](/learn/python-containers)
- [TypeScript 的类型注解与推断](/learn/ts-types)
- [抽象基类与协议：约定可以替换的能力](/learn/abstract-base)

## 参考来源 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
