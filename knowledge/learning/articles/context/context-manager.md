# 上下文管理器：把进入与退出配对

## 手动关文件漏掉了哪一步 {#overview}

学完这一篇，你能用 with 替掉手写的 try/finally，也能自己写上下文管理器，知道异常是怎么从 with 里出去的。

小林给记账脚本加了一段：打开 `notes.txt`，写一行，然后 `close()`。平时没问题。后来他在中间加了校验，金额格式不对就抛异常：

```python
f = open("notes.txt", "w", encoding="utf-8")
f.write("早餐 12 元\n")
raise ValueError("金额格式不对")
f.close()          # 执行不到
```

`close()` 被异常跳过。CPython 的垃圾回收有时候会替他关掉文件，但那是"迟早会"，不是"现在"；在长跑的服务里，句柄会一直累积，Windows 上还可能让别的进程删不掉这个文件。

他改成 `try/finally`：

```python
f = open("notes.txt", "w", encoding="utf-8")
try:
    f.write("早餐 12 元\n")
    raise ValueError("金额格式不对")
finally:
    f.close()
```

不管正常结束还是抛异常，`close()` 都执行。代价是每次打开文件都要写这套骨架。

`with` 把"进入时拿资源、离开时还资源"这段骨架收进了对象自己身上。写成 `with open(...) as f:` 之后，你只需要关心中间那几行真正要做的事。

## 把 try/finally 换成 with {#example}

新建 `notes_with.py`：

```python
def manual():
    f = open("notes.txt", "w", encoding="utf-8")
    try:
        f.write("早餐 12 元\n")
        print("写入时 closed =", f.closed)
    finally:
        f.close()
    print("finally 之后 closed =", f.closed)


def using_with():
    with open("notes.txt", "w", encoding="utf-8") as f:
        f.write("早餐 12 元\n")
        print("写入时 closed =", f.closed)
    print("with 之后 closed =", f.closed)


manual()
using_with()
```

```bash
python notes_with.py
```

你应该看到：

```
写入时 closed = False
finally 之后 closed = True
写入时 closed = False
with 之后 closed = True
```

对比两份代码，`using_with` 里少掉了这些：`f =`、`try:`、`finally:`、`f.close()`，还有往外缩进的那一层。行为没有变：块里 `closed` 是 `False`，离开块就变成 `True`。

`as f` 拿的是 `open(...)` 的 `__enter__` 返回值。文件对象的 `__enter__` 返回它自己，所以 `f` 就是文件对象；换个对象，`as` 后面拿到的不一定是它本身，下面会看到。

`with` 不是"帮你在末尾插一句 close"。它调用的是对象自己的退出方法；文件对象选择关闭，锁对象选择释放，数据库连接选择提交或回滚。这个区别决定了你不能看到 `with` 就假设"肯定保存好了"。

## with 的三个动作：进入、交给你、退出 {#walkthrough}

自定义一个类，把三个动作打印出来：

```python
class Tracked:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        print("进入", self.name)
        return self.name

    def __exit__(self, exc_type, exc_value, traceback):
        print("退出", self.name, "| 异常类型:", exc_type)
        return False


with Tracked("正常") as name:
    print("使用", name)

try:
    with Tracked("出事") as name:
        print("使用", name)
        raise ValueError("金额格式不对")
except ValueError as e:
    print("外面接到:", e)
```

运行后你应该看到：

```
进入 正常
使用 正常
退出 正常 | 异常类型: None
进入 出事
使用 出事
退出 出事 | 异常类型: <class 'ValueError'>
外面接到: 金额格式不对
```

三个动作对应三件事：

**进入。** `with` 先调用对象的 `__enter__()`。它的返回值绑给 `as` 后面的名字；没有 `as`，返回值直接丢掉。`Tracked.__enter__` 返回字符串 `"正常"`，所以 `name` 是字符串，不是对象。

**交给你。** 冒号下面的缩进块开始执行，这就是你要保护的代码。它可以正常结束，也可以 `return`、`break`、`continue`，或者抛异常。

**退出。** 离开块时调用 `__exit__(exc_type, exc_value, traceback)`。正常结束时三个参数都是 `None`；有异常时，分别是异常的类型、实例和 traceback。

`__exit__` 的返回值决定异常去留：

- 返回 `None` 或 `False`：异常继续往外传。上面 `Tracked` 返回 `False`，所以外面能接到 `ValueError`。
- 返回 `True`：异常被吞掉，`with` 后面的代码继续执行。

`return`、`break`、`continue` 也会触发 `__exit__`，它们不会被当成"成功"或"失败"传给 `__exit__`——异常参数仍然是 `None`。所以"with 块里提前 return 就跳过清理"是错的。

还有一个小细节：`__exit__` 自己也可能抛异常。比如关闭文件时 `flush` 失败。这时新异常会取代块里原来的异常，原异常挂在它的 `__context__` 上。排查问题时要看异常链，不要只盯最外层那一行。

## 返回 True 会把异常吞掉 {#suppress}

把 `__exit__` 的返回值改成 `True`：

```python
class Swallow:
    def __enter__(self):
        print("进入")

    def __exit__(self, exc_type, exc_value, traceback):
        print("看到了", exc_type.__name__)
        return True


try:
    with Swallow():
        raise ValueError("金额格式不对")
    print("with 后面继续执行")
except ValueError:
    print("不会到这里")
```

你应该看到：

```
进入
看到了 ValueError
with 后面继续执行
```

`ValueError` 没有传到外面的 `except`，`with` 后面的 `print` 照常执行。对外层来说，这个块"成功结束"了。

为什么通常不该这么写？因为调用方失去了判断依据。块里可能只写了一半，文件可能只写进一行，但 `with` 出来之后一切照常。上面这个例子至少还打印了"看到了"，如果连日志都没有，异常就彻底消失了。

合理的抑制要窄。`contextlib.suppress` 是标准写法：

```python
from contextlib import suppress
from pathlib import Path

with suppress(FileNotFoundError):
    Path("临时文件.tmp").unlink()
```

这里的意思很明确：文件不在就算了。它只吞 `FileNotFoundError`，其他异常照常抛。你写 `__exit__` 时也照这个标准：默认返回 `False`；只有"这个异常是预期内的，而且正确做法就是什么都不做"时，才返回 `True`，并把异常类型限定清楚。

`__exit__` 返回 `True` 也不能让块里的副作用回滚。已经写出去的一半数据、已经发出去的请求，都还在。抑制异常只改变控制流，不改变已经发生的事。

## 用 @contextmanager 写一个计时器 {#contextmanager}

每次都写一个类太啰嗦。`contextlib.contextmanager` 允许你用生成器写：

```python
import time
from contextlib import contextmanager


@contextmanager
def timer(label):
    start = time.perf_counter()
    try:
        yield
    finally:
        used = time.perf_counter() - start
        print(f"{label}: {used:.2f} 秒")


with timer("求和"):
    total = sum(range(1_000_000))
    print("总和", total)
```

你会看到类似：

```
总和 499999500000
求和: 0.01 秒
```

耗时每次不同，可能是 0.01、0.02 或更久，但两行的顺序固定：块里的 `print` 先执行，退出时才打印耗时。

这个生成器的执行方式值得拆开：

- `yield` 之前的代码在 `__enter__` 时运行，也就是 `start = ...`。
- `yield` 的值交给 `as` 后面的名字。这里没写 `as`，值被丢掉；`yield "句柄"` 的话，`as handle` 会拿到 `"句柄"`。
- 块结束时，生成器从 `yield` 处恢复，继续执行 `finally` 里的代码。
- 块里抛异常时，异常被抛进生成器的 `yield` 位置。没有被捕获的话，`finally` 仍然执行，异常继续往外传。

`try/finally` 不能省。写成：

```python
@contextmanager
def timer(label):
    start = time.perf_counter()
    yield
    print("耗时", time.perf_counter() - start)
```

正常退出没问题；块里一抛异常，生成器在 `yield` 处收到异常，后面那行 `print` 不执行，清理逻辑就漏了。`finally` 保证它执行，和你手写 `try/finally` 的道理一样。

`@contextmanager` 本身就是一个装饰器。它把生成器函数换成一个包装函数；每次调用包装函数，都会创建一个 `_GeneratorContextManager` 对象，由它保存生成器。`with` 进入时调用这个对象的 `__enter__`，驱动生成器跑到 `yield`。所以 `with` 的行为没有变，只是你不用手写类了。

## with 不负责让事情成功 {#pitfalls}

**"进了 with，操作就成功了。"** `with` 只保证退出逻辑会执行，不保证块里的事成功。数据库连接最典型：

```python
import sqlite3

conn = sqlite3.connect(":memory:")
conn.execute("create table t(x)")
with conn:
    conn.execute("insert into t values (1)")
print(conn.execute("select count(*) from t").fetchone())
```

输出：

```
(1,)
```

`with conn` 提交了这次事务，但没有关闭连接——退出之后还能继续查询。`sqlite3` 把连接对象当成"事务边界"，不是"资源所有权边界"。换一个库、换一个对象，`__exit__` 做的事可能完全不同：有的提交，有的回滚，有的关闭，有的只释放锁。看到 `with` 之后，还要看对象的文档或源码。

如果你只想保证关闭、不想让 `with` 顺手提交事务，`contextlib.closing(conn)` 更明确：退出时只调用 `close()`。

**"`close()` 之后数据一定在磁盘上。"** `close()` 会把 Python 的缓冲区刷给操作系统，但不等于落盘。机器掉电时，还在页缓存里的数据可能丢失。要求掉电也不丢，得显式 `f.flush()` 再 `os.fsync(f.fileno())`；如果还要原子替换文件，再配合临时文件和 `os.replace()`。

**"`__exit__` 返回 True 更安全。"** 它只会让异常消失，不会让失败消失。调用方拿不到错误，日志里也没有，排查时只剩"数据怎么少了一半"。默认让它返回 `False`，只在异常类型明确且处理方式真的是"忽略"时才抑制。

**"with 块里 return 会跳过 `__exit__`。"** 不会。`return`、`break`、`continue`、异常，四种离开方式都会触发退出方法。验证一下：

```python
class T:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        print("退出")
        return False


def f():
    with T():
        return "值"


print(f())
```

输出：

```
退出
值
```

先打印"退出"，再把返回值交给调用方。

## 什么时候别把东西塞进 with {#tradeoffs}

`with` 让边界好看，但它不会缩短边界。把一次网络请求、一次用户确认放进 `with FileLock(...)` 或数据库事务，锁和事务就被拉长了；代码看起来整齐，其他进程或连接却在排队。能放到块外的计算、IO、校验，尽量放到块外。

嵌套太多也会遮住重点。一个请求处理函数里套四层 `with`，读代码的人很难判断哪一层提交、哪一层回滚、哪一层只是关闭。事务和锁的边界是业务语义，值得显式写出来，不要藏在三层工具函数里。

自己写上下文管理器时，先想清楚谁拥有资源。一个函数如果从调用方接收连接，就不该用 `with conn` 把它提交掉；除非接口文档明确说"这个函数会结束事务"。资源的开启和关闭最好在同一层，否则调用方很难判断什么时候还能用。

简单的前后成对逻辑用 `@contextmanager` 就够了，计时、临时目录、环境变量切换都属于这类。需要保存状态、提供多个方法、支持重复进入或异步协议时，再写类。为五行代码造一个类，不会让代码更清楚。

异步资源用 `async with`，它调用的是 `__aenter__` / `__aexit__`，不是把普通 `with` 加个 `async` 就能用。用错了会在进入时直接报 `TypeError`，不会悄悄降级成同步。

还有一点：`with` 不等于错误处理。你仍然要决定异常是往外传、在块外捕获，还是在退出时转换。`with` 只负责"离开时一定调用退出方法"这一件事。

## 练习：退出、吞异常与生成器 {#self-check}

**第 1 题**：下面这段代码打印什么？异常会传出去吗？

```python
class Q:
    def __enter__(self):
        print("A")
        return 1

    def __exit__(self, *exc):
        print("B")
        return True


with Q() as v:
    print(v)
    raise RuntimeError("x")
print("C")
```

> **答案**
>
> 依次打印 `A`、`1`、`B`、`C`。
>
> `__enter__` 返回 1，绑给 `v`；块里抛出的 `RuntimeError` 进入 `__exit__`，返回 `True` 把它吞掉；所以 `with` 后面的 `print("C")` 正常执行，没有 traceback。

**第 2 题**：`with open(...)` 的块里抛异常，文件会关吗？异常还会往外传吗？

> **答案**
>
> 会关，也会传。
>
> 文件对象的 `__exit__` 关闭文件，并返回 `None`（假值），所以异常继续往外抛。可以这样验证：
>
> ```python
> try:
>     with open("notes.txt", "w", encoding="utf-8") as f:
>         raise RuntimeError("写失败了")
> except RuntimeError:
>     print("f.closed =", f.closed)
> ```
>
> 输出 `f.closed = True`。`f` 在 `with` 之前就已经绑定，异常被捕到之后仍然能访问。

**第 3 题**：用 `@contextmanager` 写一个上下文管理器，进入时打印"开始 名字"，退出时打印"结束 名字"，名字通过参数传入。

> **答案**
>
> ```python
> from contextlib import contextmanager
>
> @contextmanager
> def step(name):
>     print("开始", name)
>     try:
>         yield name
>     finally:
>         print("结束", name)
>
> with step("对账") as label:
>     print("处理", label)
> ```
>
> 输出：
>
> ```
> 开始 对账
> 处理 对账
> 结束 对账
> ```
>
> `yield name` 的值交给 `as label`；`finally` 保证块里抛异常时"结束"仍会打印。

## 继续阅读：异常、文件与事务 {#related}

- [异常与错误处理](/learn/python-exceptions)
- [文件、路径与资源生命周期](/learn/python-files)
- [文件锁：协调对共享文件的访问](/learn/file-lock)
- [数据库事务：一致完成状态转换](/learn/db-transaction)

## 资料来源 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
