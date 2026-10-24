# 函数、参数与返回值

## 函数是什么 {#overview}

学完这一篇，你能写出一个能反复调用的函数，知道它收什么、交回什么，并且能看出调用方拿到的是不是它以为的那个东西。

你抄了三遍同一段计算：单价乘数量。第一次抄对了，第三次改价的时候忘了改其中两处。

函数就是给这段计算**起个名字**。起完名字，你只写一次，以后叫它就行。

名字之外还有两件事需要说清楚：

- **参数**——调用者能换的部分（这里换的是单价和数量）。
- **返回值**——函数交给调用者的结果（这里是总价）。

说清楚这三样（做什么、收什么、交回什么），别人就能用你的函数，你也能读别人的函数。

## 写第一个函数 {#example}

新建一个文件 `total.py`，写进去：

```python
def calculate_total(price, quantity=1):
    total = price * quantity
    return total
```

然后在**同一个文件**下面加两行，**运行它**：

```python
amount = calculate_total(12, quantity=3)
print(amount)
```

```bash
python total.py
```

你应该看到：

```
36
```

现在文件里有三个"东西"要分清：

- `def calculate_total(...)` —— **定义**。只是告诉 Python 有这么个函数，此刻什么都没算。
- `calculate_total(12, quantity=3)` —— **调用**。这一次才真的算了，返回 36。
- `print(amount)` —— **显示**。`amount` 拿到的是 36，打印是另一件事。

把 `print(amount)` 那行删掉，再运行——**什么都不会输出**。因为函数算完了、结果交回来了，但没人把它显示出来。这就是"计算"和"显示"的区别。

## 参数怎么对应上 {#walkthrough}

**第一步，参数怎么对应上。** 我们的定义有两个参数：`price` 和 `quantity`。调用时写了 `calculate_total(12, quantity=3)`：

- `12` 是**位置参数**——按顺序，它就是 `price`。
- `quantity=3` 是**关键字参数**——按名字，它就是 `quantity`。

为什么第二个要用关键字？因为 `price` 和 `quantity` 都是数字，位置传 `calculate_total(12, 3)` 也能跑，但你得靠记忆记住哪个是哪个。写成 `quantity=3`，读代码的人一眼就知道这个 3 是什么。

**第二步，默认值。** 定义里 `quantity=1` 是个默认值。不传数量时，它用 1：

```python
print(calculate_total(12))        # 12
print(calculate_total(12, 3))     # 36
print(calculate_total(12, quantity=3))  # 36
```

三种写法结果相同。第三种更好读。

**第三步，`return` 到底做了什么。** 它把结果**交回调用处**，然后函数结束。试试把 `return total` 改成 `print(total)`：

```python
def calculate_total(price, quantity=1):
    total = price * quantity
    print(total)     # 改成这样

amount = calculate_total(12, quantity=3)
print(amount)
```

屏幕会出现两个 36，但第一个是函数自己打印的，第二个打印的是 `amount`——而 `amount` 现在是 `None`。因为函数没有 `return`，Python 默认返回 `None`。

这就是初学者最常撞的墙：**`print` 是显示，`return` 是交回**。显示是给人看的，交回是给代码用的。

**第四步，局部变量。** 函数里的 `total` 是**局部**的——函数外面看不到它：

```python
print(total)   # NameError: name 'total' is not defined
```

这正是我们想要的效果：函数不该把内部细节漏到外面。

给它加一个折扣参数：

```python
def calculate_total(price, quantity=1, discount=0):
    total = price * quantity * (1 - discount)
    return total

print(calculate_total(12, 3, discount=0.2))   # 28.8
```

多了一个参数，**原来的调用方式全都还能用**（`discount` 有默认值 0）。这是加参数时该守的规矩：新的参数放后面并给默认值，别让老代码全部改一遍。

## 调用时发生了什么 {#mechanism}

**函数体什么时候执行？** 只有被调用时。`def` 那行只是把代码记下来，绑定一个名字。调用时才发生三件事：实参与形参绑定 → 执行函数体 → `return` 的值交回调用处。

**参数绑定的是"对象"，不是"值"。** 这一条在 Python 里特别容易踩坑：

```python
def add_item(items, item):
    items.append(item)     # 原地修改传入的列表

def replace_item(items, item):
    items = [item]        # 只是让局部名字指向新列表

a = [1, 2]
add_item(a, 3)
print(a)        # [1, 2, 3]  ← 调用方的列表被改了

b = [1, 2]
replace_item(b, 3)
print(b)        # [1, 2]     ← 调用方的列表没变
```

`add_item` 改的是**同一个列表对象**的内容，所以调用方看得见。`replace_item` 只是让函数内的名字 `items` 指向了一个**新**列表，函数一结束这个名字就没了，调用方那边什么都没变。

规律：**修改传入的可变对象 = 副作用；重新绑定名字 = 局部操作**。

**返回值和副作用是两个维度。** 一个函数可以只返回数据（纯函数），也可以只改外部状态（写文件、发请求），也可以两样都干。名字会骗人——叫 `save` 的函数不一定真的保存成功，叫 `get` 的函数也可能顺手更新了缓存。**要判断一个函数做了什么，得读它的实现，不是看它的名字。**

## 五个常见的坑 {#pitfalls}

**"`print` 和 `return` 差不多。"** 差很远。上面刚试过：`print` 只显示，`return` 才把值交回代码。一个只 `print` 不 `return` 的函数，调用方拿到的永远是 `None`。

**"函数里的变量在外面也能用。"** 不能，除非你明确说了 `global`（而那通常意味着设计有问题）。局部变量出函数就没了。

**"默认参数用列表没事，反正是同一个。"** 有事，这是最隐蔽的一个坑：

```python
def add_task(task, todo=[]):   # 危险
    todo.append(task)
    return todo

print(add_task("a"))   # ['a']
print(add_task("b"))   # ['a', 'b']  ← 上次的 'a' 还在！
```

默认参数**在函数定义时求值一次**，不是每次调用时。所以这个列表会被所有调用共享。要避免就用 `None`：

```python
def add_task(task, todo=None):
    if todo is None:
        todo = []
    todo.append(task)
    return todo
```

**"`*args` / `**kwargs` 看不懂，跳过。"** 它们只是"把剩下的打包"：`*args` 把多余的位置参数收成一个元组，`**kwargs` 把多余的关键字参数收成一个字典。看到长签名不用慌——先找有没有 `*args` 那一行，就知道前面那些是必填的。

## 函数该写多长 {#tradeoffs}

**写多长？** 一个函数只做一件事、名字说清做什么，是好函数。但**过度拆分**更烦——读一个流程要跳七八个文件，比一个长函数更难懂。判断标准：如果你要跳着看才能说清它在干什么，就该拆。

**返回值还是副作用？** 优先用返回值。纯函数（只算、只返回、不改外面）能随便调用、随便测试——你给它同样的输入，它给同样的输出。副作用（写文件、发网络请求）要单独标出来，让人知道这个调用会动东西。

**函数签名就是它的接口。** 参数类型、可能返回什么、什么时候抛异常、会不会修改传进来的东西——这些要在定义处就说清楚。读一个陌生项目里的函数时，**从调用点开始读**比从定义开始读更快：先看它被怎么调用，就知道该关心哪些参数。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这个函数，`result` 是什么？

```python
def double(x):
    x = x * 2

result = double(5)
print(result)
```

> **答案**
>
> `None`。
>
> 函数体里 `x = x * 2` 只是让**函数内的局部名字** `x` 指向 60，函数一结束这个名字就没了。没有 `return`，Python 默认返回 `None`。
>
> 想返回结果，必须写 `return x * 2`。

**第 2 题**：`add_item` 和 `replace_item` 这两个函数里，为什么一个会改到调用方的列表，另一个不会？

> **答案**
>
> 因为 `add_item` 调的是 `items.append(item)`——**原地修改**了那个列表对象，调用方持有的正是同一个对象，所以看得见变化。
>
> `replace_item` 调的是 `items = [item]`——只是让函数内的**名字** `items` 指向了一个新列表。函数结束后这个名字消失，调用方那边一点没变。

**第 3 题**：为什么 `def add_task(task, todo=[])` 会有问题？正确写法是什么？

> **答案**
>
> 默认参数在**函数定义时**求值一次，不是每次调用时求值。所以这个 `[]` 被所有调用共享——第二次调用时，上次追加的内容还在里面。
>
> 正确写法是用 `None` 占位，在函数体里判断：
>
> ```python
> def add_task(task, todo=None):
>     if todo is None:
>         todo = []
>     todo.append(task)
>     return todo
> ```

## 继续阅读 {#related}

- [变量、值与类型](/learn/python-values)
- [模块、包与导入](/learn/python-modules)
- [类型注解：把接口约定写出来](/learn/python-annotations)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)

## 参考资料 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
