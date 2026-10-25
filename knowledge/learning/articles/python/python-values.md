# 变量、值与类型

## 改 b 为什么动到了 a {#overview}

读完这一篇，你能说清一次赋值到底做了什么，并判断改一个名字会不会动到另一个。

小林的记账工具里，budget 是本月预算，draft 是他想拿来试算的副本。他改了 draft，budget 也跟着变了。同事说"两个变量指向同一个列表"，他更糊涂了：赋值不是复制一份吗？

新建 demo.py，写入四行：

```python
a = [1, 2]
b = a
b.append(3)
print(a)
```

运行：

```bash
python demo.py
```

```
[1, 2, 3]
```

b 只加了一个 3，a 却变了。这个结果会贯穿整篇：**赋值只是把名字绑到对象上，不复制对象**。

## 先跑三组赋值 {#assignment}

在同一个目录新建 names.py，写入：

```python
a = [1, 2]
b = a
print(a is b)

c = [1, 2]
d = c
d = d + [3]
print(c is d)
print(c)
print(d)

items = ["笔记本"]
cart = items
cart.append("钢笔")

copy = items.copy()
copy.append("书包")
print(items)
print(copy)
print(items is copy)
```

运行：

```bash
python names.py
```

你应该看到：

```
True
False
[1, 2]
[1, 2, 3]
['笔记本', '钢笔']
['笔记本', '钢笔', '书包']
False
```

三组赋值，三种结果。第一组里两个名字是同一个列表；第二组做了加法再赋值，原来的列表没变；第三组只复制了外层，所以新列表能独立追加。

## 一次赋值做了哪两件事 {#walkthrough}

**第一步，先算右边。** `a = [1, 2]` 先创建一个列表对象，再把名字 `a` 绑到它上面。名字不是盒子，它只是命名空间里的一条记录：`a` 指向哪个对象。

**第二步，`b = a` 取的是右边表达式的值。** 表达式 `a` 求值得到那个列表对象，于是 `b` 也绑到同一个对象。没有第二个列表被创建，`a is b` 为 True。

**第三步，`b.append(3)` 改的是对象。** 方法通过 `b` 找到列表，在原地追加。`a` 和 `b` 指向同一张列表，所以打印 `a` 也看得到 3。

**第四步，`d = c` 同样只是别名。** 此时 `c` 和 `d` 指向同一个列表。

**第五步，`d = d + [3]` 和 append 不同。** `d + [3]` 先算出**一个新列表**，赋值再把 `d` 绑到新列表上。`c` 还指向旧列表，所以 `c` 不变、`d` 变了，`c is d` 为 False。

**第六步，`.copy()` 明确要求一份新列表。** `copy` 和 `items` 是两个不同的外层列表。给 `copy` 追加"书包"，`items` 不受影响。

画成箭头，前两步是这样：

```
a ─┐
   ├──> [1, 2]
b ─┘
```

赋值改变的是箭头，不是箭头指着的对象。`append` 改对象，`d = d + [3]` 改箭头。分清这两件事，后面一大半的困惑会消失。

## 类型决定能改还是只能换 {#mutability}

对字符串调用方法，再对列表调用方法：

```python
word = "ledger"
word.upper()
print(word)

word = word.upper()
print(word)

items = ["笔记本"]
items.append("钢笔")
print(items)
```

```
ledger
LEDGER
['笔记本', '钢笔']
```

`upper()` 返回一个新字符串，第一次没有接住返回值，`word` 还是原来的。第二次把返回值赋回 `word`，名字换了指向。列表不一样：`append` 直接改原来那个对象，不需要重新赋值。

"不可变"说的是对象内容不能改，不是说名字不能换。整数、字符串、元组属于前者；列表、字典、集合可以原地改。你随时可以让同一个名字改指另一种类型的对象，这叫动态类型，不代表运算会自动转换类型。

`+=` 最容易看错，因为它对两类对象的行为不同：

```python
name = "账本"
before = id(name)
name += "v2"
print(name, before == id(name))

box = [1]
before = id(box)
box += [2]
print(box, before == id(box))
```

```
账本v2 False
[1, 2] True
```

字符串的 `+=` 造了一个新对象，旧对象没变，所以 id 不同。列表的 `+=` 在原地扩展，还是同一个对象，所以 id 相同。这里只比较 `id(...)` 的结果，不打印具体数字，因为数字每次运行都可能不同。

类型还决定了这个对象能做什么：

```python
value = "5"
print(value * 2)
try:
    print(value + 1)
except TypeError as e:
    print("TypeError:", e)
```

```
55
TypeError: can only concatenate str (not "int") to str
```

`"5" * 2` 是字符串重复，结果是 `"55"`；`+` 要求两边都是字符串，所以加数字直接报错。类型属于对象，不属于名字。名字可以先后指向整数和字符串，但每一次运算都要看当时那个对象的类型。

## is 和 == 在问两个问题 {#identity}

```python
a = [1, 2]
b = [1, 2]
print(a == b)
print(a is b)

c = a
print(a is c)
print(None == None, None is None)
```

```
True
False
True
True True
```

`==` 问的是"两个对象的值相等吗"。两个不同的列表都装 1 和 2，答案就是 True。

`is` 问的是"是不是同一个对象"。`b` 是另建的一张列表，所以 False；`c = a` 让两个名字指向同一张列表，所以 True。

判断 `None` 用 `is`，这是少数明确该用它的场景。不要用 `is` 比较数字或字符串是否相等。CPython 会缓存一些小整数和字符串，让 `1 is 1` 有时看起来成立，但那是实现细节，不是语言保证，换个版本或换个构造方式就可能变。

`id(a) == id(b)` 也能判断同一性，它比较的是对象标识。但 id 的值在对象释放后可能被复用，不适合保存下来当业务标识。

## 别名、浅复制与注解的五个误会 {#pitfalls}

**"`b = a` 是复制了一份。"** 没有。两个名字绑到同一个对象，改一个另一个看得见。上面的 a/b 已经验证过，想要独立副本得明确复制。

**"`.copy()` 之后两个列表完全无关。"** 只复制了外层。内层元素如果还是列表，仍然是共享的：

```python
a = [[1], [2]]
b = a.copy()
b[0].append(9)
print(a)
```

```
[[1, 9], [2]]
```

要连内层一起复制，用 `copy.deepcopy`。

**"可以用 `is` 判断两个字符串相等。"** 不要。判断值相等用 `==`。`is` 只回答同一性，字符串何时被缓存不由你控制。

**"变量有类型，类型注解会在运行时检查值。"** 类型跟着对象走，名字可以改指别的类型。注解默认只是给人和工具看的：

```python
total: int = "35"
print(total, type(total).__name__)
```

```
35 str
```

这段代码能正常运行。想强制检查，得靠额外的校验工具或库。

**"默认参数每次调用都会新建一个空列表。"** 默认值在函数定义时求值一次，之后所有调用共享同一个对象：

```python
def add_task(task, todo=[]):
    todo.append(task)
    return todo

print(add_task("a"))
print(add_task("b"))
```

```
['a']
['a', 'b']
```

要每次新建，用 `None` 占位，进函数后再创建列表。

## 复制到什么程度才够 {#copy-cost}

浅复制和深复制的差别，跑一遍就清楚：

```python
import copy

a = [[1], [2]]
shallow = a.copy()
deep = copy.deepcopy(a)

shallow[0].append(9)
print(a)
print(shallow)
print(deep)
```

```
[[1, 9], [2]]
[[1, 9], [2]]
[[1], [2]]
```

`a` 和 `shallow` 共享内层列表，所以一起变；`deep` 连内层都复制了，保持原样。

共享不是错误。函数往调用方给的列表里填结果、多个视图读同一份只读数据，都是在有意共享。共享省内存，也省复制时间，代价是耦合：一个地方改，别处也跟着变。

复制也不是越多越安全。浅复制只隔离外层，适合一层列表或字典；深复制会递归复制，数据大时开销明显，还可能碰到不能复制的对象，比如打开的文件、网络连接。把每个函数的参数都深复制一遍，通常只是把问题藏起来。

接口需要只读时，先把约定写清楚；确实要防调用方修改内部状态，再在边界返回副本。调试"值怎么突然变了"时，先找还有哪些名字指向同一个对象——赋值、函数参数、容器里的元素都算——再考虑加锁或复制。锁解决的是并发访问，不解决别名。

## 三道判断名字的题 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这段代码打印什么？

```python
a = [1]
b = a
b += [2]
print(a)
```

> **答案**
>
> `[1, 2]`。
>
> 列表的 `+=` 是原地扩展，`a` 和 `b` 指向同一个列表。改成 `b = b + [2]`，结果就不同了：那会先造一个新列表再绑定给 `b`，`a` 仍是 `[1]`。

**第 2 题**：`x = [1]`、`y = [1]`，`x == y` 和 `x is y` 分别是什么？怎样让 `x is y` 变成 True？

> **答案**
>
> `x == y` 是 True，值相等；`x is y` 是 False，两个不同的列表对象。
>
> 执行 `y = x` 之后，两个名字指向同一个对象，`x is y` 就是 True。

**第 3 题**：`nested = [[1]]`，`other = nested.copy()`，再执行 `other[0].append(2)`，`nested` 是什么？

> **答案**
>
> `[[1, 2]]`。
>
> `.copy()` 只复制外层列表，`nested[0]` 和 `other[0]` 还是同一个内层列表。要让两者彻底独立，用 `copy.deepcopy`。

## 往下读容器、函数和注解 {#related}

- [列表、元组、字典与集合](/learn/python-containers)
- [函数、参数与返回值](/learn/python-functions)
- [类型注解：把接口约定写出来](/learn/python-annotations)

## 参考资料 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
