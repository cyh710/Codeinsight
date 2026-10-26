# 函数、参数与返回值

## 函数是什么 {#overview}

函数算出了数，屏幕也显示了数，调用者却拿到了 None。这篇从这个现象出发，分清参数、返回值与屏幕输出，并学会沿调用处读懂一个函数。

先看一段能运行的代码。新建 `total.py`，输入：

```python
def calculate_total(price, quantity=1):
    print(price * quantity)

amount = calculate_total(12, 3)
print(amount)
```

用 `python total.py` 运行，屏幕依次显示 `36` 和 `None`。第一个数字来自函数内部，第二行来自最后的 `print(amount)`。函数确实做了计算，但**计算、显示、交回结果是三个不同动作**。

函数让一段计算有了名字：只定义一次，可以带着不同数据反复调用。名字之外，还要看它与调用者怎样交换数据。

名字之外还有两件事需要说清楚：

- **参数**——调用者能换的部分（这里换的是单价和数量）。
- **返回值**——函数交给调用者的结果（这里是总价）。

说清楚这三样（做什么、收什么、交回什么），别人就能用你的函数，你也能读别人的函数。

## 写第一个函数 {#example}

用下面的定义替换刚才的函数。这里只改最后一个动作：把显示换成返回。

```python
def calculate_total(price, quantity=1):
    total = price * quantity
    return total
```

函数下面保留调用和打印：

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

![打印走向屏幕，返回值交给调用处；没有 return 时，普通函数正常结束会返回 None。](/knowledge/assets/python-return-path)

图中的箭头表示执行先后。对第一段程序，内部 `print` 显示 36，函数结束后将 None 交给 `amount`，外部 `print` 才显示 None。换成 `return` 后，36 交给 `amount`，内部不再显示；调用者可以打印它，也可以拿它继续计算，例如 `amount + 1` 得到 37。

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

第一种省略数量，使用默认值 1，所以结果是 12。后两种都传入数量 3，结果才相同。关键字参数的价值在于把“3 是数量”写清楚；它不会改变这个乘法本身。

**第三步，`return` 到底做了什么。** 它把结果**交回调用处**，然后函数结束。试试把 `return total` 改成 `print(total)`：

```python
def calculate_total(price, quantity=1):
    total = price * quantity
    print(total)     # 改成这样

amount = calculate_total(12, quantity=3)
print(amount)
```

屏幕先显示 `36`，再显示 `None`。第一个是函数自己打印的，第二个打印的是 `amount`。因为函数没有显式 `return`，正常执行到结尾时返回 `None`。

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

对这个签名，在末尾增加有默认值的 `discount`，前面展示的调用方式仍然成立。实际修改接口还要核对所有调用处，尤其是使用关键字、位置解包或继承重写的地方；不能只凭“新增参数有默认值”就宣布兼容。

## 调用时发生了什么 {#mechanism}

**函数体什么时候执行？** 普通函数的函数体在调用时执行。执行 `def` 会创建函数对象、绑定名字，并求值默认参数等定义时表达式；它不是完全“什么都不做”。调用时再将实参绑定到形参，执行函数体，最后把返回值交给调用处。

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

## 调用时容易读错的地方 {#pitfalls}

**"`print` 和 `return` 差不多。"** 上面刚试过：`print` 向输出流写内容，`return` 把值交回代码。这里讨论的普通函数如果没有显式返回值并且正常结束，调用者得到 None；如果抛出异常，控制流会转向异常处理，不是正常拿到一个返回值。

**"函数里的变量在外面也能直接用。"** 局部名字不会自动成为外部名字。若想让调用者使用计算结果，应明确返回；不要为了取一个结果随意引入共享全局状态。对象本身可能被返回或被闭包保留，函数结束不等于所有对象立即销毁。

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

**看到 `*args` / `**kwargs` 怎么读？** `*args` 收集多余的位置参数，`**kwargs` 收集多余的关键字参数。判断必填项还要看默认值和参数种类：`*args` 前面的参数也可能有默认值，后面则可能有必填的仅限关键字参数。先看完整签名，再核对调用处传了什么。

## 函数该写多长 {#tradeoffs}

**写多长？** 一个函数只做一件事、名字说清做什么，是好函数。但**过度拆分**更烦——读一个流程要跳七八个文件，比一个长函数更难懂。判断标准：如果你要跳着看才能说清它在干什么，就该拆。

**返回值还是副作用？** 单纯计算适合返回值；保存数据、显示内容和发请求本来就需要副作用。若函数只依赖输入且没有可观察副作用，就更容易独立测试。仅仅“没有改外面”还不够，例如读取当前时间也可能让相同输入产生不同结果。

**函数签名就是它的接口。** 参数类型、可能返回什么、什么时候抛异常、会不会修改传进来的东西——这些要在定义处就说清楚。读一个陌生项目里的函数时，**从调用点开始读**比从定义开始读更快：先看它被怎么调用，就知道该关心哪些参数。

## 验证自己分清了什么 {#self-check}

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
> 这里实参是 5，函数内的 `x` 因而重新绑定到 10；这不等于返回 10。没有 `return`，正常结束时返回 `None`。
>
> 想返回结果，必须写 `return x * 2`。

**第 2 题**：`add_item` 和 `replace_item` 这两个函数里，为什么一个会改到调用方的列表，另一个不会？

> **答案**
>
> 因为 `add_item` 调的是 `items.append(item)`——**原地修改**了那个列表对象，调用方持有的正是同一个对象，所以看得见变化。
>
> `replace_item` 调的是 `items = [item]`——只是让函数内的**名字** `items` 指向了一个新列表。函数结束后这个名字消失，调用方那边一点没变。

若默认列表的示例还不直观，可以在两次调用前后打印 `id(todo)`。这个补充观察用于理解共享对象，无须再背一遍定义。

## 继续阅读 {#related}

- [变量、值与类型](/learn/python-values)
- [模块、包与导入](/learn/python-modules)
- [类型注解：把接口约定写出来](/learn/python-annotations)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)

## 参考资料 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
- 具体核对：[定义函数、默认参数与关键字参数](https://docs.python.org/3.13/tutorial/controlflow.html#defining-functions)。2026-10-26 修订了示例输出、默认参数解释和适用条件；原创示意图的作者及许可见资源清单。
