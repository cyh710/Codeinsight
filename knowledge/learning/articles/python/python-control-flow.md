# 条件与循环：程序怎样选择下一步

## 账本里有一笔 0 元 {#overview}

读完这一篇，你能把"跳过一条"和"结束整个循环"写对，并说清一段代码为什么会走这条分支。

小林记了一周的账，列表里有一条试算的 0 元，还有一条上周补录的 89 元。他要只统计本周、跳过 0 元。第一次他把"跳过"写成了 `break`，结果排在 89 后面的 35 元也没算进去。

跳过一条不等于结束整个循环。先把这段账跑对。

## 把一周的账跑一遍 {#ledger-loop}

新建 ledger.py：

```python
expenses = [
    ("周一", 12),
    ("周二", 0),
    ("上周五", 89),
    ("周三", 35),
]

total = 0
for day, amount in expenses:
    if day.startswith("上周"):
        continue
    if amount == 0:
        continue
    total += amount
    print(f"{day} 记入 {amount}")

print("本周合计", total)
```

运行：

```bash
python ledger.py
```

你应该看到：

```
周一 记入 12
周三 记入 35
本周合计 47
```

再看分档。新建 labels.py：

```python
for amount in [12, 0, -35, 200]:
    if amount < 0:
        label = "退款"
    elif amount == 0:
        label = "试算"
    elif amount < 50:
        label = "日常"
    else:
        label = "大额"
    print(amount, label)
```

```bash
python labels.py
```

```
12 日常
0 试算
-35 退款
200 大额
```

一个循环，两种用法：账本那段负责跳过和累加，分档这段负责从几个条件里选一个结果。

## 循环每一轮在做什么 {#walkthrough}

先看账本。

**第一轮，`day` 是"周一"，`amount` 是 12。** 两个 `if` 都不成立，`total` 从 0 变成 12，打印"周一 记入 12"。

**第二轮，`day` 是"周二"，`amount` 是 0。** 第一个 `if` 不成立，第二个成立，执行 `continue`。它跳过本轮剩下的语句，所以 `total` 不变，也不打印。

**第三轮，`day` 是"上周五"，`amount` 是 89。** 第一个 `if` 就成立，`continue` 直接进入下一轮。金额检查和累加都没走到。

**第四轮，`day` 是"周三"，`amount` 是 35。** 两个 `if` 都不成立，`total` 变成 47，打印"周三 记入 35"。

循环结束，打印合计 47。**每一轮只会走一个分支，`continue` 还会直接跳到下一轮**，所以写在 `continue` 后面的行不是每轮都执行。

把第一个 `continue` 改成 `break`，再跑一次，输出变成：

```
周一 记入 12
本周合计 12
```

`break` 在"上周五"那一轮把整个循环结束了，第四轮根本没有发生。这就是小林少算 35 元的原因。

再看分档。12 进来时，第一个条件假、第二个假、第三个真，得到"日常"，后面的 `else` 不再检查。0 在第二个条件就停下，-35 在第一个停下，200 一路假到 `else`。**条件是从上往下试的，命中一个就结束。**

顺序写反会出问题：

```python
amount = 20
if amount < 500:
    print("中额")
elif amount < 50:
    print("小额")
```

```
中额
```

20 明明小于 50，却打印了"中额"。因为第一个条件先成立，第二个分支被跳过了。更糟的是，只有第一个条件不成立时才会检查第二个，而那时金额已经大于等于 500，不可能小于 50，所以"小额"这一支永远不会执行。

## for 和 while 各管哪一种重复 {#for-vs-while}

手里已经有一串东西，要逐个处理，用 `for`。不知道要转几轮、只知道"到某个条件为止"，用 `while`。

下面用 `while` 从余额里扣款：

```python
payments = [12, 20, 35]
balance = 50
index = 0
while balance >= payments[index]:
    balance -= payments[index]
    index += 1
print(balance, index)
```

```
18 2
```

每一轮开始前先检查余额够不够下一笔。够就扣掉并移动下标：50 扣 12 剩 38，再扣 20 剩 18。第三笔 35 超过余额，条件为假，循环停下，此时下标是 2。

同样的事用 `for` 写，停止条件更显眼：

```python
payments = [12, 20, 35]
balance = 50
for payment in payments:
    if balance < payment:
        break
    balance -= payment
print(balance)
```

```
18
```

`for` 本身负责取每一笔，`break` 负责在余额不够时退出。没有手工维护的下标，也不会出现"所有款项都付完、下标越界"的问题。上面那段 `while` 如果余额足够付完三笔，下一轮访问 `payments[3]` 就会报 `IndexError`，实际代码还得加边界判断。

判断标准很简单：循环的主体是"处理这批数据"，选 `for`；循环的主体是"等到条件改变"，选 `while`。`while` 的函数体里必须有东西能让条件最终变假，否则它会一直转。

## break、continue、return 把执行带到哪 {#jumps}

```python
expenses = [
    ("周一", 12),
    ("周二", 0),
    ("上周五", 89),
    ("周三", 35),
]

def first_big(expenses, limit):
    for day, amount in expenses:
        if amount == 0:
            continue
        if amount >= limit:
            return day
    return None

print(first_big(expenses, 50))
print(first_big(expenses, 100))
```

```
上周五
None
```

第一次调用，限额 50：周一 12 不够，周二 0 被 `continue` 跳过，上周五 89 够了，`return "上周五"` 立刻结束整个函数，周三没有再看。

第二次调用，限额 100：所有金额都不到 100，循环正常结束，走到函数末尾的 `return None`。

三个关键字的作用范围不一样：

| 关键字 | 范围 | 之后执行什么 |
|---|---|---|
| `continue` | 当前这一轮 | 直接进入下一轮 |
| `break` | 最近一层循环 | 循环后面的语句 |
| `return` | 整个函数 | 回到调用处，函数结束 |

`break` 只退出最近一层循环。两层循环嵌套时，内层 `break` 之后外层还会继续转。想一次跳出两层，要么用标志变量，要么把这段循环放进函数里用 `return`。

## 少算一项、多删一个和停不下来的循环 {#pitfalls}

**"代码从上往下写，所以每一行都会执行。"** 不会。上面的 `continue` 跳过了累加，`if/elif` 每次只走一个分支，`return` 和异常也能让后面的行不执行。读业务代码时，先找分支和退出点，再算具体数值。

**"`range(1, 5)` 会包含 5。"** 不包含，结束值取不到：

```python
print(list(range(1, 5)))
```

```
[1, 2, 3, 4]
```

要包含 5 就写 `range(1, 6)`。这是"循环少处理了末尾一项"的常见来源。

**"边遍历列表边 `remove` 元素很安全。"** 不安全。删除会让后面的元素前移，而循环的下标还在往前走，于是有元素被跳过：

```python
nums = [1, 2, 2, 3]
for n in nums:
    if n == 2:
        nums.remove(n)
print(nums)
```

```
[1, 2, 3]
```

两个 2 只删掉一个。要筛掉元素，用推导式生成新列表：

```python
nums = [1, 2, 2, 3]
kept = [n for n in nums if n != 2]
print(kept)
```

```
[1, 3]
```

**"`while` 的条件不变，它自己也会停。"** 不会。循环体里没有东西改变条件，就会一直转。网络重试尤其要注意，除了次数上限，还要有总时间上限，因为有的请求会卡住不返回。

**"循环的 `else` 和 `if` 的 `else` 是一回事。"** 不是。`for...else` 的 `else` 在循环正常结束、没有遇到 `break` 时执行：

```python
for n in [1, 2, 3]:
    if n == 4:
        break
else:
    print("没找到 4")
```

```
没找到 4
```

这段不是"一次都没循环才执行 else"。把 `break` 触发一次，`else` 就会被跳过。

## 早返回省掉的缩进值得吗 {#early-return}

函数里先处理异常情况，再写主流程，能少掉几层缩进：

```python
def record(amount):
    if amount == 0:
        return "试算，不记账"
    if amount < 0:
        return "退款"
    return "正常记账"
```

三个 `return` 各自结束函数，读的人从上往下就能看到所有出口。代价是出口变多了，每个出口都要保证资源已经收尾。用 `with` 打开文件时，`return` 也会正常关闭；手工打开的资源则要配 `try/finally`。

循环本身也有代价。直白的 `for` 加几个 `if` 通常最好调试，每一轮发生了什么都能手算。列表推导式适合简单的筛选和转换，把复杂分支、打印、修改外部状态塞进一行，反而更难读。

选 `for` 还是 `while`，选 `break` 还是 `return`，都看你想表达什么：是"处理完这批数据"，还是"找到就结束"。写法应该让停止条件一眼可见。

写完用几组小输入手算一遍：空列表、边界值、第一条就命中的情况、一条都不命中的情况。循环的错，大多藏在这几种输入里。

## 三道手算流程的题 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：把 ledger.py 里第一个 `continue` 换成 `break`，输出是什么？

> **答案**
>
> ```
> 周一 记入 12
> 本周合计 12
> ```
>
> `break` 在处理"上周五"时结束了整个循环，后面的"周三 记入 35"不会再执行。`continue` 只跳过那一轮，所以原来的版本是 47。

**第 2 题**：下面这段打印什么？为什么第二个分支没有机会执行？

```python
for amount in [10, 60]:
    if amount > 5:
        print("A")
    elif amount > 50:
        print("B")
```

> **答案**
>
> 打印两行 `A`。
>
> 10 和 60 都大于 5，第一分支都成立，`elif` 不再检查。若想让 60 打印 B，得把 `amount > 50` 的判断放到前面。

**第 3 题**：在函数里找到了符合条件的记录，为什么通常写 `return` 而不是 `break`？

> **答案**
>
> `return` 直接把结果交给调用处并结束函数；`break` 只结束循环，循环后面的代码还会继续执行。
>
> 如果函数的任务就是"找到就返回"，用 `return` 最清楚：
>
> ```python
> def first_big(expenses, limit):
>     for day, amount in expenses:
>         if amount >= limit:
>             return day
>     return None
> ```
>
> 用 `break` 的话，还得在循环外准备变量、判断有没有找到，再 `return` 一次。

## 从流程走向变量和函数 {#related}

- [变量、值与类型](/learn/python-values)
- [函数、参数与返回值](/learn/python-functions)
- [列表、元组、字典与集合](/learn/python-containers)

## 版本与资料 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
