# 列表、元组、字典与集合

## 小林的一周开销 {#overview}

学完这一篇，你能用列表记账、用字典按名字取值、用元组打包一条记录、用集合去重，也能判断眼前这件事该用哪种容器。

小林在记这一周的午饭钱。第一天他写 `lunch = 28`，第二天写 `lunch2 = 31`，到周五变量名已经排到了 `lunch5`。

真正想回答的问题不在这五个变量里：这周一共花了多少？最贵的是哪笔？哪几家店重复去过？

要把多笔开销放在一起，才有这些问题。容器就是**让一个名字装下多个值**的东西。Python 里常用的四种，各自回答的问题不一样。

## 往列表里加、删、排、切 {#list-moves}

新建 `expenses.py`：

```python
expenses = [12, 4, 28]

expenses.append(18)
print("加完:", expenses)

expenses.remove(4)
print("删完:", expenses)

expenses.sort()
print("排完:", expenses)

print("前两笔:", expenses[:2])
```

运行：

```bash
python expenses.py
```

你会看到：

```
加完: [12, 4, 28, 18]
删完: [12, 28, 18]
排完: [12, 18, 28]
前两笔: [12, 18]
```

逐行看。

**第一步，`[12, 4, 28]` 按位置存。** 三个值有固定顺序。`expenses[0]` 是 12，`expenses[1]` 是 4，最后一个是 `expenses[-1]`，这种负号写法从末尾数。

**第二步，`append(18)` 往末尾加。** 它改的是原来那个列表，不返回一个新列表。打印出来是四个值，顺序就是加进去的顺序。

**第三步，`remove(4)` 按值删。** 它删掉第一个等于 4 的元素。如果列表里有两个 4，只会删掉一个；如果要按位置删，用 `pop(1)` 这种写法。

**第四步，`sort()` 原地排序。** 排的是列表自己，从小到大的顺序。注意它不返回排好的列表——这件事下面会单独说。

**第五步，`[:2]` 切出前两个。** 切片取的是下标 0 和 1，结果是新列表 `[12, 18]`。原来的 `expenses` 还是三个值，没被切短。

列表擅长的事情都围绕位置：第几个、前几个、插在哪、按什么顺序排。

## 列表不会替你复制里面的东西 {#copy-traps}

小林想把一份三天的空账模板复制三份，写成这样：

```python
print([1, 2] * 3)

row = [0, 0, 0]
grid_bad = [row] * 3
grid_bad[0][0] = 9
print(grid_bad)

grid_ok = [[0, 0, 0] for _ in range(3)]
grid_ok[0][0] = 9
print(grid_ok)
```

输出：

```
[1, 2, 1, 2, 1, 2]
[[9, 0, 0], [9, 0, 0], [9, 0, 0]]
[[9, 0, 0], [0, 0, 0], [0, 0, 0]]
```

`[1, 2] * 3` 看起来像复制，其实只是把元素排列重复了三遍。这里装的是整数，整数改不了，所以没出问题。

`[row] * 3` 就不一样了。`row` 是一个列表对象，重复三次得到的是**三个指向同一个列表的引用**。改第一行的第一个格子，三行一起变，因为它们本来就是同一行。

用列表推导式 `[[0, 0, 0] for _ in range(3)]`，每轮循环都重新执行一次 `[0, 0, 0]`，才会得到三个不同的内层列表。

同样的道理也发生在赋值和复制上：

```python
x = [1, 2]
y = x
y.append(3)
print("x:", x)
```

输出：

```
x: [1, 2, 3]
```

`y = x` 没有复制列表，只是给同一个列表又起了一个名字。`x.append` 和 `y.append` 动的是同一个对象。

要复制外层，用 `a.copy()`、`list(a)` 或 `a[:]`。但这三种都是**浅拷贝**：

```python
import copy

a = [[1, 2], [3, 4]]
b = a.copy()
b.append([5, 6])
print(a)
b[0].append(99)
print(a)

c = copy.deepcopy(a)
c[1].append(7)
print(a)
print(c)
```

输出：

```
[[1, 2], [3, 4]]
[[1, 2, 99], [3, 4]]
[[1, 2, 99], [3, 4]]
[[1, 2, 99], [3, 4, 7]]
```

`b.append` 只往 `b` 的外层加了一项，`a` 没变。`b[0].append` 改的是两个列表共用的内层列表，`a` 就看见了。

`deepcopy` 会一层层往下复制，所以 `c` 再改也碰不到 `a`。代价是更慢、更占内存；如果列表里只有数字和字符串，`.copy()` 就够了。

## 名字对价格：字典 {#dict-lookup}

列表能回答“第几笔花了多少”，回答不了“地铁多少钱”。后一个问题得从头扫，直到找到名字叫“地铁”的那一项。

字典直接建立名字到值的对应：

```python
prices = {"早餐": 12, "地铁": 4, "午餐": 28}

print(prices["午餐"])
print(prices.get("打车", 0))
print(list(prices))

records = [("早餐", 12), ("地铁", 4), ("午餐", 28)]
by_name = {name: amount for name, amount in records}
print(by_name["地铁"])
```

输出：

```
28
0
['早餐', '地铁', '午餐']
4
```

`prices["午餐"]` 按键取到 28，不需要知道“午餐”排第几。

`prices.get("打车", 0)` 在键不存在时返回 0。换成 `prices["打车"]` 会抛 `KeyError`，因为字典不会猜你想要什么。这两种写法要按场景选：缺键是正常情况，用 `get`；缺键说明数据有问题，就让 `[]` 抛错。

最后一段把“名字、金额”的列表转成了“名字到金额”的字典，之后每次按名字查都不用再扫列表。这就是查找表。

字典保留插入顺序，`list(prices)` 打印出来的键按加入的先后排列。但按键取值和按位置取值是两件事，`prices[0]` 会去找键 `0`，不是第一项。

字典的键要能算出一个稳定的哈希值。字符串、数字、只含不可变值的元组都可以；列表不行，因为列表内容会变。

## 元组打包一条记录，集合去掉重复 {#tuple-and-set}

一条开销有名字有金额，这两个值最好别被拆散。元组做的就是这件事：

```python
expense = ("午餐", 28)
name, amount = expense
print(f"{name} 花了 {amount} 元")

try:
    expense[1] = 30
except TypeError as e:
    print(e)
```

输出：

```
午餐 花了 28 元
'tuple' object does not support item assignment
```

`name, amount = expense` 把两个位置的值分别交给两个变量。位置本身就是含义：第一个是名字，第二个是金额。换顺序可以，但含义就错了。

元组建好以后不能改某一项，所以它适合“这组值代表一条固定记录”。只有一项的元组要写成 `(5,)`，那个逗号不能省；`(5)` 只是加了括号的数字 5。

元组里的值如果本身不可变，元组就能当字典的键，例如用 `("2026-10-25", "午餐")` 去对应一笔账。

集合解决的是另一个问题：去重。

```python
places = ["公司", "家", "公司", "超市", "家"]
store_names = set(places)

print(len(places), len(store_names))
print(store_names == {"公司", "家", "超市"})
print("超市" in store_names)
print(sorted(store_names))
```

输出：

```
5 3
True
True
['公司', '家', '超市']
```

原列表有 5 项，转成集合后只剩 3 个不同的名字。重复的“公司”和“家”被合并了。

集合不保存顺序，也不能用下标取。`sorted(store_names)` 能排出一个固定顺序，是因为排序时新建了列表，不是因为集合本身有序。直接打印集合，顺序不保证，别指望它按你想要的顺序出现。

**去重之前先问一句：重复是不是信息。** 一周的购物明细里，“地铁”出现两次说明你坐了两趟，不能先去重；只有“去过哪些店”这种问题才可以把重复压掉。

## 按什么标准挑容器 {#choosing}

| 你要做的事 | 用它 | 原因 |
|---|---|---|
| 按加入顺序一笔笔处理，允许重复 | 列表 | 位置稳定，重复保留 |
| 用名字或编号取一个值 | 字典 | 按键找，不用扫 |
| 只问“在不在”，顺便去重 | 集合 | 重复合并，成员判断不用逐项看 |
| 一组固定位置、不打算改的值 | 元组 | 不可变，能当字典键 |

列表的 `in` 要从头看一遍。集合和字典按键找，不用逐项扫。这是它们在“判断在不在”上的主要差别，代价是集合和字典要额外占内存。

有时一句话里有两个需求。比如“按顺序列出名字，重复的只留第一次出现的”：

```python
names = ["小林", "阿敏", "小林", "阿杰"]
seen = set()
unique = []

for name in names:
    if name not in seen:
        seen.add(name)
        unique.append(name)

print(unique)
```

输出：

```
['小林', '阿敏', '阿杰']
```

列表负责顺序，集合负责“见没见过”。两个一起用，比硬选一个更直接。

挑容器前先写下三个问题的答案：顺序重要吗？重复有意义吗？是按位置取还是按名字取？答案清楚，容器基本就定了。

## 五个会咬人的细节 {#pitfalls}

**“`sort()` 会把排好序的列表返回给我。”** 不会。它原地排序，返回 `None`：

```python
expenses = [12, 4, 28]
result = expenses.sort()
print(result)
print(expenses)
```

输出：

```
None
[4, 12, 28]
```

要一个排好序的新列表，用 `sorted(expenses)`，原来的列表不动。

**“`{}` 是空集合。”** 不是，`{}` 是空字典。空集合要写 `set()`：

```python
print(type({}))
print(type(set()))
```

输出：

```
<class 'dict'>
<class 'set'>
```

**“缺键时 `d[k]` 和 `d.get(k)` 一样安全。”** 不一样。`[]` 直接抛 `KeyError`，`get` 返回 `None` 或你给的默认值：

```python
prices = {"早餐": 12}
try:
    prices["打车"]
except KeyError as e:
    print("没有这个键:", e)
print(prices.get("打车"))
```

输出：

```
没有这个键: '打车'
None
```

**“列表能当字典的键。”** 不能。列表可修改，算不出稳定的哈希值：

```python
try:
    {["早餐", 12]}
except TypeError as e:
    print(e)
```

输出：

```
unhashable type: 'list'
```

要拿一组值当键，用元组。

**“`a.copy()` 会把里面也复制一遍。”** 只复制第一层。里面装列表时，副本和原列表仍然共用那些内层对象；要彻底分开，用 `copy.deepcopy`。上面的例子已经验证过。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这段代码打印什么？

```python
items = [3, 1, 2]
result = items.sort()
print(result, items)
```

> **答案**
>
> ```
> None [1, 2, 3]
> ```
>
> `sort()` 原地排序并返回 `None`。`items` 本身已经变成 `[1, 2, 3]`，但 `result` 拿到的是 `None`。

**第 2 题**：`a` 最后是什么？

```python
a = [[1], [2]]
b = a.copy()
b[0].append(9)
print(a)
```

> **答案**
>
> ```
> [[1, 9], [2]]
> ```
>
> `a.copy()` 是浅拷贝。`b` 和 `a` 是两个外层列表，但 `b[0]` 和 `a[0]` 指向同一个内层列表。`b[0].append(9)` 改的是那个共用的内层列表，所以 `a` 也看得见。

**第 3 题**：`names = ["小林", "阿敏", "小林"]`，要按原顺序去重，结果写成 `["小林", "阿敏"]`，怎么做？

> **答案**
>
> 列表保顺序，集合记“见过没有”：
>
> ```python
> names = ["小林", "阿敏", "小林"]
> seen = set()
> unique = []
>
> for name in names:
>     if name not in seen:
>         seen.add(name)
>         unique.append(name)
>
> print(unique)   # ['小林', '阿敏']
> ```
>
> 如果顺序无所谓，直接 `list(set(names))` 也行；但要保顺序，就得自己走一遍。

## 继续阅读 {#related}

- [变量、值与类型](/learn/python-values)
- [条件与循环：程序怎样选择下一步](/learn/python-control-flow)
- [函数、参数与返回值](/learn/python-functions)
- [模块、包与导入](/learn/python-modules)

## 参考资料 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
