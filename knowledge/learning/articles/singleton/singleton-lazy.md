# 延迟初始化与缓存工厂

## 数据库连接什么时候建 {#overview}

读完这一篇，你能把启动时建好的连接推迟到第一次调用，并知道它在多线程、多进程和测试里会在哪里失灵。

小林的项目在模块顶部写了一行 `db = connect()`。这样一来，任何 `import` 都会连数据库：跑一个只算价格的单元测试，也要等连接；CI 机器没配数据库，测试收集阶段就挂了。

连接本身又很贵，不能每次用都新建。于是问题变成两个：什么时候建，以及建好以后给谁用。

延迟初始化把“建”推迟到第一次需要时。缓存工厂把建好的对象存起来，下次直接返回。两者叠在一起，看起来就是一个进程内共享的实例。

## 导入时就连接的写法 {#eager}

新建 `eager_db.py`：

```python
class Database:
    def __init__(self):
        print("建立数据库连接")
        self.rows = []


print("模块加载开始")
db = Database()
print("模块加载结束")
```

运行 `python eager_db.py`：

```
模块加载开始
建立数据库连接
模块加载结束
```

Python 导入模块时，会把文件从上到下执行一遍。`db = Database()` 不在函数里，导入动作一发生，连接就建了。

这里的 `db` 已经是一个模块级实例，同一个进程里所有 `import eager_db` 的地方拿到的是同一个模块对象，也就拿到同一个 `db`。模块只完整执行一次，后续导入从 `sys.modules` 里取缓存，不会重新建连接。这就是“模块级实例本质上就是单例”的原因。

代价也很直接。导入变慢；导入会失败；失败发生在程序还没开始处理请求的时候。测试只想用一个纯函数，也被迫承担连接成本。配置还没读、环境变量还没设的时候，连接就已经发出去了。

## 第一次用到才建 {#lazy}

新建 `lazy_db.py`，把构造挪进函数：

```python
class Database:
    def __init__(self):
        print("建立数据库连接")
        self.rows = []


_db = None


def get_db():
    global _db
    if _db is None:
        _db = Database()
    return _db


print("模块加载完成，还没有连接")
get_db().rows.append("第一条")
get_db().rows.append("第二条")
print("共", len(get_db().rows), "条")
```

运行 `python lazy_db.py`：

```
模块加载完成，还没有连接
建立数据库连接
共 2 条
```

第一次 `get_db()` 看到 `_db is None`，调用 `Database()`，把对象存进模块全局变量。第二次、第三次直接返回它，所以“建立数据库连接”只打印一次。

`global _db` 不能省。不声明 `global` 时，函数里的 `_db` 会被当成局部变量；第一行 `if _db is None` 还没给它赋值，直接抛 `UnboundLocalError`。加了 `global`，读写的才是模块里的那个 `_db`。

这个版本仍然是一个进程内单例：模块加载一次，`_db` 就一份。它只解决了“什么时候建”，没解决“同时有两个人第一次调用”。

## 用 lru_cache 缓存工厂 {#lru-cache}

`functools.lru_cache` 可以把“按参数缓存返回值”直接套在工厂函数上：

```python
from functools import lru_cache


class Database:
    def __init__(self):
        print("建立数据库连接")
        self.rows = []


@lru_cache(maxsize=1)
def get_db():
    return Database()


get_db()
get_db()
info = get_db.cache_info()
print(f"命中 {info.hits} 次，未命中 {info.misses} 次")
get_db.cache_clear()
print("清空后大小：", get_db.cache_info().currsize)
get_db()
print("清空后重建，未命中：", get_db.cache_info().misses)
```

输出：

```
建立数据库连接
命中 1 次，未命中 1 次
清空后大小： 0
建立数据库连接
清空后重建，未命中： 1
```

第一次调用未命中，建对象并缓存。第二次调用命中，直接返回缓存的对象，不再打印连接。`maxsize=1` 表示缓存最多保留一组参数的结果；这个函数没有参数，所以只有一组。

`cache_clear()` 清掉缓存，下一次调用会重新构造。注意 `cache_info()` 里的命中/未命中计数也被一起清零了，所以重建后的 `misses` 又从 1 开始，不是 2。

有参数时，缓存键就是参数组合。`get_db("primary")` 和 `get_db("replica")` 会各建一个对象。这时它不再是“单例工厂”，而是“带键的对象缓存”，两者的共享范围完全不同。

`maxsize` 还意味着淘汰。设成 2、请求三种参数时，旧对象可能被挤出去；下次同一个参数再来，又会新建。要“永远同一个”，通常写 `maxsize=None`（无上限），但那样缓存只增不减，键很多时会一直占内存。

`lru_cache` 本身是线程安全的，但并发首次未命中时，包装函数可能被执行两次：两个线程都发现没缓存，都进去构造，其中一个结果会被另一个覆盖。它保证的是缓存结构不坏，不是“构造只发生一次”。

## 两个线程同时第一次调用 {#double-checked}

先看没有锁时会怎样。五个线程同时进来，都看到“还没建”：

```python
import threading
import time


class Database:
    count = 0

    def __init__(self):
        Database.count += 1
        time.sleep(0.02)
        self.rows = []


created = []
gate = threading.Barrier(5)


def unsafe_get():
    gate.wait()
    if not created:
        created.append(Database())


threads = [threading.Thread(target=unsafe_get) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print("无锁时构造了", Database.count, "次")

Database.count = 0
db = None
lock = threading.Lock()
gate = threading.Barrier(5)
results = []


def get_db():
    global db
    gate.wait()
    if db is None:
        with lock:
            if db is None:
                db = Database()
    return db


def worker():
    results.append(get_db())


threads = [threading.Thread(target=worker) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print("双检锁后构造了", Database.count, "次")
print("所有线程拿到同一个对象：", all(item is results[0] for item in results))
```

输出：

```
无锁时构造了 5 次
双检锁后构造了 1 次
所有线程拿到同一个对象： True
```

`threading.Barrier(5)` 让五个线程都到齐再往下走，这样才容易看到竞争。没有锁时，五个线程几乎同时判断 `not created`，都得到 `True`，然后各自进去构造。`Database.__init__` 里的 `sleep` 模拟连接耗时，期间释放 GIL，别的线程正好挤进来。

有 GIL 也不保证安全。GIL 只保证同一时刻有一个线程执行 Python 字节码，不保证“检查 + 构造 + 赋值”这一串是原子的。构造里有 I/O、`sleep`、网络请求时，GIL 会被释放，窗口就出现了。

双检锁的写法是两层判断：

- 外层 `if db is None` 在没必要时不加锁，已经建好后每次调用只读一次变量。
- 进入 `with lock` 后再判断一次。第一个线程构造期间，其他线程可能在锁外排过队；等它们拿到锁，`db` 已经不是 `None`，内层检查把它们挡住。

外层检查单独不够，因为多个线程可以同时通过；内层检查单独也能工作，但每次调用都要抢锁。两个一起用，才有“只构造一次”和“平时不加锁”。

## 测试里的全局对象换不掉 {#testing}

全局单例最烦的地方在测试。下面的 `_store` 在模块导入时创建，所有测试共用：

```python
class Store:
    def __init__(self):
        self.rows = []


_store = Store()


def add(text):
    _store.rows.append(text)


add("测试 A 的数据")
add("测试 B 的数据")
print("测试 B 看到：", _store.rows)
```

输出：

```
测试 B 看到： ['测试 A 的数据', '测试 B 的数据']
```

测试 B 本来只想看自己写进去的数据，却看到了测试 A 留下的。单独跑 B 能过，和 A 一起跑就失败；调整测试顺序，失败又消失。这类问题很难从断言信息里看出来。

换掉也不总是换得干净：

```python
import sys

_db = "旧连接"


def get_db():
    return _db


me = sys.modules[__name__]
early = _db
me._db = "测试用的假连接"

print("get_db() 拿到：", get_db())
print("早先导入的名字：", early)
```

输出：

```
get_db() 拿到： 测试用的假连接
早先导入的名字： 旧连接
```

`me._db = ...` 改的是模块属性，`get_db` 每次通过全局名查找，所以看到新值。`early = _db` 相当于 `from module import _db`，它绑定的是当时那个对象；模块属性后来换了，这个提前绑定的名字还指着旧的。测试里混用两种导入方式，就会出现“我明明 patch 了，怎么没生效”。

就算 patch 对了，同一个进程里并行跑测试也会互相踩：两个测试同时改同一个全局对象，谁先谁后不确定。要么在每个测试后重置，要么把依赖从外面传进去，让每个测试拿自己的实例。

## 单例什么时候变成坏设计 {#bad-design}

共享一个无状态、线程安全的对象，通常没问题。坏在把“进程内只有一个”当成“所有数据都可以放进去”。

先看共享可变状态：

```python
class Cart:
    def __init__(self):
        self.items = []


cart = Cart()


def add(user, item):
    cart.items.append(item)
    print(f"{user} 购物车：{cart.items}")


add("小林", "牛奶")
add("阿杰", "钢笔")
```

输出：

```
小林 购物车：['牛奶']
阿杰 购物车：['牛奶', '钢笔']
```

阿杰看到了小林的牛奶。真实服务里，两个请求交错执行，问题会更隐蔽：A 刚写入，B 读到的就是 A 的数据。

三个信号说明这个单例该拆了：

**隐式全局状态。** 任何函数都能改 `cart.items`，改的地方可能离读取的地方很远。读代码时看不到数据从哪来，只能全局搜索变量名。

**生命周期不清。** 连接、文件句柄、线程池都占资源。单例一旦创建，谁负责关闭？进程退出时操作系统会回收，但优雅关闭、刷新缓冲、提交事务都没人做。

**并发下共享可变数据。** 单例让所有请求指向同一个对象，锁就得覆盖每一次读写。漏一处，数据就串。把状态限制在请求内，或者每个用户一个对象，往往比给全局对象加锁简单。

多进程还会打破“只有一个”的假设。两个 uvicorn worker 是两个进程，各自导入一次模块，各有一个 `db`，内存里的缓存、锁、计数器都不共享。要跨进程共享，得上外部存储或专门的缓存服务。

更清楚的替代方案是显式生命周期：应用启动时初始化资源，交给容器或依赖注入，请求处理函数接收它，应用关闭时统一释放。测试里传入假实现，不需要动全局变量。

## 单例的四个误判 {#pitfalls}

**“模块级对象是全局唯一。”** 只在单个进程内成立。多进程、多解释器、多台机器各有各的模块和对象。名字一样，内存不共享。

**“套上 `@lru_cache` 就是严格单例。”** 只对无参数工厂、单进程、缓存不被清空的情况成立。`cache_clear()`、`maxsize` 淘汰、不同参数都会产生新对象；并发首次未命中还可能构造两次。

**“延迟初始化自动线程安全。”** 不会。`if _db is None: _db = Database()` 是读、判断、写三步，线程可以在中间切走。要保证只构造一次，锁和二次检查都得到位。

**“单例省资源，所以能共享就共享。”** 单例把对象的寿命拉到进程级。连接、缓存、大列表长期不释放，内存和句柄都涨；对象状态还会跨请求、跨测试保留。共享只适合无状态或只读的东西。

## 延迟初始化的代价 {#tradeoffs}

延迟初始化的好处是启动快、可选依赖不拖累主流程。代价是把首次延迟和首次失败推到用户操作时：第一个请求要等连接建立；配置错了，错误不在启动日志里，而在某个用户点击之后。

要做判断，可以问三个问题：

- 这个资源是必需的吗？必需就在启动时初始化，配置错误立刻暴露，别等到线上第一个请求。
- 首次调用能接受多慢？几十毫秒的连接可以懒加载；几秒的模型加载、索引构建，最好在启动阶段做掉或显示进度。
- 谁负责关闭？有句柄、连接、线程的资源，需要明确的生命周期。懒加载解决“何时建”，不解决“何时关”。

适合做成模块级共享的，通常是只读配置、无状态的客户端、线程安全的连接池。不适合的是请求上下文、用户会话、购物车、当前登录用户这类带可变状态的东西。

测试友好度也是判断标准。一个全局单例如果没法在测试里替换、重置，就会把测试顺序变成隐式依赖。用依赖注入、工厂参数或显式的 `init`/`close` 接口，比在测试里到处 patch 模块属性可靠。

## 练习 {#self-check}

**第 1 题**：下面的 `get_db()` 被调用三次，为什么“建立数据库连接”只打印一次？

```python
_db = None

def get_db():
    global _db
    if _db is None:
        _db = Database()
    return _db
```

> **答案**
>
> 第一次调用把新对象赋给模块全局变量 `_db`。后面两次判断 `_db is None` 为假，直接返回同一个对象。`global` 保证赋值写回模块作用域，而不是创建一个函数局部的 `_db`。

**第 2 题**：`get_db` 被 `@lru_cache(maxsize=1)` 装饰。先调用一次，保存返回对象为 `old`，再 `get_db.cache_clear()`，然后调用得到 `new`。`old is new` 是什么？一共构造了几次？

> **答案**
>
> `False`，一共构造两次。`cache_clear()` 只清缓存，不会销毁已经返回的对象；`old` 还被变量引用着。下一次调用缓存为空，重新构造出 `new`。缓存统计也会清零。

**第 3 题**：两个线程同时第一次调用 `get_db()`，为什么只在外层判断 `_db is None` 不够？正确的锁结构是什么？

> **答案**
>
> 两个线程可能同时看到 `_db is None`，都进入构造，结果建出两个对象。需要在锁内再判断一次：
>
> ```python
> _lock = threading.Lock()
>
> def get_db():
>     global _db
>     if _db is None:
>         with _lock:
>             if _db is None:
>                 _db = Database()
>     return _db
> ```
>
> 外层避免每次调用都抢锁，内层保证只有一个线程真正构造。构造过程如果有 I/O 或 `sleep`，GIL 会被释放，竞争窗口是真实存在的。

## 继续阅读 {#related}

- [依赖注入：把需要的能力交进来](/learn/dependency-injection)
- [连接池：复用已经建立的连接](/learn/connection-pool)
- [Redis 缓存：复用可以重建的结果](/learn/redis-cache)
- [模块、包与导入](/learn/python-modules)

## 参考资料 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
