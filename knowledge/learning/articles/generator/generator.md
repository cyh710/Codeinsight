# 生成器：按需产生一串值

## 读一个装不进内存的文件 {#overview}

读完这一篇，你能把一次性读入改成边读边处理，也知道生成器什么时候会失效。

日志文件有 200 万行。你写 `lines = f.readlines()`，程序跑了几秒，内存一路涨，机器开始换页。文件在磁盘上只有几十 MB，读进 Python 以后却完全不同：每一行都是一个独立的字符串对象，200 万行就是 200 万个对象。

处理这类数据不必先准备更大的内存。读一行、处理一行、丢掉一行，同时只留一行在手上就够了。生成器就是 Python 里表达这种“按需产生”的工具。

## 让 readlines 把内存吃满 {#readlines}

新建 `bigfile.py`，先造 100 万行数据，再用两种方式读。100 万行比 200 万行跑得快，现象一样。

```python
def make_lines(n):
    for i in range(n):
        yield f"line {i:07d}\n"

with open("demo.log", "w", encoding="utf-8") as f:
    f.writelines(make_lines(1_000_000))

with open("demo.log", encoding="utf-8") as f:
    lines = f.readlines()
print(f"readlines 版本：{len(lines)} 行都在内存里")
del lines


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            yield line.rstrip("\n")

count = 0
for line in read_lines("demo.log"):
    count += 1
print(f"生成器版本：{count} 行，峰值只持有一行")
```

运行：

```bash
python bigfile.py
```

你应该看到：

```
readlines 版本：1000000 行都在内存里
生成器版本：1000000 行，峰值只持有一行
```

拆开看这段代码。

第一步，`make_lines` 自己就是个生成器。`f.writelines(make_lines(1_000_000))` 每要一行才生成一行，不会先在内存里拼出一个 100 万元素的列表。

第二步，`f.readlines()` 一次性返回列表。`len(lines)` 能直接算出 100 万，是因为这 100 万个字符串此刻全在列表里；`del lines` 把它们放掉，后面的对比才不会被这份列表干扰。

第三步，`read_lines` 里没有 `return`，而是 `yield`。每次循环向它要下一行，它读到一行、交出去、暂停；`count += 1` 做完，再要下一行。整个文件读完，内存里也没有出现过 100 万行的列表。

`readlines` 不是坏函数。文件只有几百行时，它简单直接。问题在于**它的内存用量跟文件大小成正比**，而生成器版本的用量跟“一行有多长”有关，跟“一共有多少行”无关。

## yield 停在半路，下次接着走 {#yield-pause}

新建 `countdown.py`：

```python
def countdown(n):
    print("开始")
    while n > 0:
        print(f"准备交出 {n}")
        yield n
        print(f"恢复，n 还是 {n}")
        n -= 1
    print("结束")

g = countdown(2)
print("拿到生成器，函数体还没运行")
print(next(g))
print("回到主程序")
print(next(g))
try:
    next(g)
except StopIteration:
    print("没有更多值")
```

运行 `python countdown.py`：

```
拿到生成器，函数体还没运行
开始
准备交出 2
2
回到主程序
恢复，n 还是 2
准备交出 1
1
恢复，n 还是 1
结束
没有更多值
```

`countdown(2)` 这一行没有打印“开始”。它只创建了一个生成器对象，函数体一行都没执行。

第一次 `next(g)` 才真正进去：打印“开始”，走到 `yield n`，把 `n` 的值 2 交回调用处，然后**停在那里**。局部变量 `n`、循环位置、执行到哪一行，全都保留着。

主程序打印“回到主程序”之后，第二次 `next(g)` 从暂停点继续：先打印“恢复”，把 `n` 减 1，再回到循环顶部，交出 1，又停住。

第三次 `next(g)` 恢复后 `n` 变成 0，循环结束，打印“结束”。函数正常返回，生成器抛出 `StopIteration`，告诉调用方没有下一项了。`for` 循环会自动捕获这个信号，所以平时看不到异常。

暂停点只能往前走。生成器一旦走完，不会自己回到开头：

```python
def three():
    yield 1
    yield 2
    yield 3

g = three()
print(sum(g))
print(sum(g))
```

输出：

```
6
0
```

第二次的 `sum(g)` 拿到的是 0，因为生成器已经耗尽。想要再来一遍，得重新调用 `three()` 得到一个全新的生成器对象；或者第一次就用 `list(g)` 把结果存下来，同时接受这份内存。

## send 送值进去，close 收尾 {#send-close}

`yield` 不只是往外吐值，它本身是一个表达式，可以接收调用方送进来的值。

```python
def accumulator():
    total = 0
    try:
        while True:
            value = yield total
            if value is None:
                break
            total += value
    finally:
        print("生成器清理完毕")

acc = accumulator()
print(next(acc))
print(acc.send(10))
print(acc.send(5))
acc.close()
```

输出：

```
0
10
15
生成器清理完毕
```

`next(acc)` 等价于 `acc.send(None)`。它把生成器推到第一个 `yield total`，此时 `total` 是 0，于是返回 0，停在赋值语句中间——`value = ...` 还没拿到值。

`acc.send(10)` 恢复执行，把 10 作为 `yield total` 这个表达式的结果赋给 `value`，累加后循环到下一次 `yield`，返回 10。

`acc.send(5)` 同理，返回 15。

`acc.close()` 在暂停点抛出 `GeneratorExit`。`try/finally` 里的清理代码执行，打印“生成器清理完毕”，然后生成器结束。`close()` 之后不能再 `send`。

有个限制：刚创建、还没启动的生成器不能直接 `send(非 None 值)`，会报 `TypeError`。先用一次 `next()` 把它推到第一个 `yield`，这叫“预热”。

不调用 `close()` 会怎样？在 CPython 里，生成器对象没有引用时通常会被回收，回收过程会触发清理。但这依赖引用计数和垃圾回收时机，文件句柄、数据库游标这类资源不该靠它。你要么把生成器读完，要么在 `finally` 里显式 `close()`，要么交给能托管生命周期的上下文管理器。

## 生成器表达式与 yield from {#expressions-yield-from}

列表推导和生成器表达式长得像，求值时机完全不同。

```python
nums = [1, 2, 3, 4]
squares_list = [n * n for n in nums]
squares_gen = (n * n for n in nums)
print("列表立刻算完：", squares_list)
print("生成器只算第一项：", next(squares_gen))
print("剩下的：", list(squares_gen))
print("第二次遍历：", list(squares_gen))
print("直接求和：", sum(n * n for n in nums))
```

输出：

```
列表立刻算完： [1, 4, 9, 16]
生成器只算第一项： 1
剩下的： [4, 9, 16]
第二次遍历： []
直接求和： 30
```

方括号的 `[n * n for n in nums]` 当场建出完整列表；圆括号的 `(n * n for n in nums)` 只返回生成器对象，`next` 时才计算第一项。第二项 `list(...)` 把剩下的 4、9、16 拿走，于是第二次遍历得到空列表。

生成器表达式作为函数的唯一参数时，外层括号可以省掉：`sum(n * n for n in nums)` 和 `sum((n * n for n in nums))` 一样，都不建中间列表。

`yield from` 用来把一个可迭代对象整个委托出去：

```python
def rows(prefix, values):
    for value in values:
        yield f"{prefix}{value}"

def all_rows():
    yield from rows("A-", [1, 2])
    yield from rows("B-", [3])

for row in all_rows():
    print(row)
```

输出：

```
A-1
A-2
B-3
```

`yield from rows(...)` 相当于写了一个 `for row in rows(...): yield row`，但它还会把外层的 `send`、`close` 转发给子生成器，并且整个表达式的结果是子生成器的 `return` 值。拼接多个数据源时，它比手写嵌套循环清楚。

## 把过滤、转换、写出接成管道 {#pipeline}

生成器可以串起来：每一段只负责一件事，数据从上游流到下游。新建 `pipeline.py`：

```python
def read_numbers(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            yield int(line)


def keep_even(numbers):
    for n in numbers:
        if n % 2 == 0:
            yield n


def double(numbers):
    for n in numbers:
        yield n * 2


def write_lines(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(f"{line}\n")


with open("numbers.txt", "w", encoding="utf-8") as f:
    f.writelines(f"{i}\n" for i in range(1, 7))

write_lines("evens.txt", double(keep_even(read_numbers("numbers.txt"))))
print(open("evens.txt", encoding="utf-8").read(), end="")
```

运行 `python pipeline.py`：

```
4
8
12
```

`write_lines` 开始循环时，向 `double` 要一项；`double` 向 `keep_even` 要一项；`keep_even` 向 `read_numbers` 要一项；`read_numbers` 才从文件读第一行。一个数字穿过四层，写完，再要下一个。

没有任何一层持有完整的 1 到 6。`numbers.txt` 即使有 200 万行，管道里同时流动的也只是一个数字。

这条链的清理也值得看一眼：

```python
def read_numbers(path):
    f = open(path, encoding="utf-8")
    try:
        for line in f:
            yield int(line)
    finally:
        f.close()
        print("文件句柄已关闭")

g = read_numbers("numbers.txt")
print("第一行：", next(g))
print("提前停止")
g.close()
```

输出：

```
第一行： 1
提前停止
文件句柄已关闭
```

`read_numbers` 暂停时，文件还开着。只要消费方提前停下又不 `close()`，这个句柄就跟着生成器一起悬着。`g.close()` 会在暂停点注入退出，`finally` 才有机会关文件。

所以管道有两件事要确认：消费方会不会读完；中途退出时，谁负责关闭上游。前者靠正常 `for` 循环，后者靠 `try/finally` 或上下文管理。别把“文件最终会被回收”当成关闭策略。

## 生成器的五个错觉 {#pitfalls}

**“生成器一定比列表省内存。”** 只在你逐项消费时成立。`list(read_lines(...))` 又把所有行放回内存，峰值跟 `readlines` 差不多。省的是同时持有的元素数，不是整个计算过程占用的总量。

**“调用生成器函数，函数体就开始执行。”** 不会。`g = countdown(2)` 只创建对象，第一段输出里的“开始”要等第一次 `next`。这个延迟可以拿来先传参数、再决定什么时候启动。

**“生成器可以反复遍历。”** 不能。上面 `sum(g)` 第二次得到 0。要重来就重新调用生成函数；或者先 `list(g)` 缓存，同时接受内存成本。

**“`yield` 只是另一种 `return`。”** `return` 结束函数，`yield` 只暂停。暂停点还能用 `send` 接收值，用 `close` 注入退出。`accumulator` 那种双向交互，靠 `return` 写不出来。

**“生成器里的错误会在创建时暴露。”** 错误在消费到那一步时才抛：

```python
def bad():
    yield 1
    raise ValueError("坏了")

g = bad()
print(next(g))
try:
    next(g)
except ValueError as exc:
    print("读取第二项时：", exc)
```

输出：

```
1
读取第二项时： 坏了
```

创建 `g` 时一切正常，第二项才炸。流式处理的异常处理要放在消费端，不能因为“生成器创建成功”就认为整条流没问题。

## 什么时候值得用生成器 {#tradeoffs}

数据是顺序处理的，就适合用生成器：读日志、解析 CSV、遍历数据库游标、做多阶段过滤和转换。它把峰值内存压到一条记录的量级，也让第一项结果更早出现。

需要 `len()`、下标、排序、随机访问，或者要反复遍历，就不适合。硬把生成器转成列表，等于把内存成本又拿回来，还多了一层绕路。几个消费者都要全部数据时，先物化或者明确各自缓存，比共享一个一次性迭代器安全。

生成器也有维护成本。调用栈里多出生成器帧，断点停的位置和普通函数不一样；异常晚到，日志里看到的现场可能离数据源很远；生命周期需要人管，尤其是消费方可能半路退出的时候。

判断标准可以很具体：如果下游写的是“对每一项做点什么”，用生成器；如果下游写的是“先看一遍全部再决定”，用列表。不要为了“看起来高级”把每个小循环都改成生成器，普通 `for` 循环读起来更直接。

## 练习 {#self-check}

先自己写答案，再对照。

**第 1 题**：下面这段代码打印的顺序是什么？

```python
def g():
    print("A")
    yield 1
    print("B")
    yield 2

x = g()
print("C")
print(next(x))
```

> **答案**
>
> 顺序是 `C`、`A`、`1`。
>
> `x = g()` 只创建生成器，函数体没跑；`print("C")` 先执行；第一次 `next(x)` 才进入函数体，打印 `A`，交回 1。`B` 要等下一次 `next` 才会出现。

**第 2 题**：为什么下面两次 `sum` 的结果不一样？怎样让它能算两遍？

```python
g = (n for n in range(3))
print(sum(g), sum(g))
```

> **答案**
>
> 输出是 `3 0`。生成器 `g` 是一次性迭代器，第一次 `sum` 把它耗尽了，第二次没有元素可加，所以是 0。
>
> 要算两遍，可以重新创建：`print(sum(n for n in range(3)), sum(n for n in range(3)))`；或者在消费之前先缓存成列表：`values = list(g)`，再 `sum(values)` 两次。缓存会占内存。

**第 3 题**：写一个生成器 `even_squares(n)`，依次产生 `0` 到 `n-1` 中偶数的平方。`list(even_squares(6))` 应该得到什么？

> **答案**
>
> ```python
> def even_squares(n):
>     for value in range(n):
>         if value % 2 == 0:
>             yield value * value
>
> print(list(even_squares(6)))
> ```
>
> 输出 `[0, 4, 16]`。`range(6)` 给出 0 到 5，偶数只有 0、2、4。

## 继续阅读 {#related}

- [上下文管理器：把进入与退出配对](/learn/context-manager)
- [文件读写：把数据放进磁盘](/learn/python-files)
- [列表、元组、字典与集合](/learn/python-containers)
- [异步编程：等待期间让出执行机会](/learn/async)

## 参考资料 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
