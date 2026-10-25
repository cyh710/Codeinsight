# 依赖注入：把需要的能力交进来

## 测试时换不掉的那行连接 {#overview}

学完这一篇，你能把数据库连接、时钟这类难替换的依赖交到调用方手里，并在测试里换掉它们。

小林写了个保存留言的函数。函数一进去就自己连数据库：

```python
import sqlite3

def save_message(text):
    conn = sqlite3.connect("messages.db")   # 路径写死在函数里
    conn.execute("CREATE TABLE IF NOT EXISTS messages (text TEXT)")
    conn.execute("INSERT INTO messages (text) VALUES (?)", (text,))
    conn.commit()
    conn.close()
```

功能没问题。麻烦出在测试：调一次 `save_message("测试")`，项目目录里就多出一个 `messages.db`，里面真的躺着一行。想确认写没写对，还得再打开那个文件查。测试跑两次，剩两行；换台机器跑，路径又不一样。

问题不在 sqlite。问题在 `save_message` 把"连哪个库、怎么连"关在了自己肚子里。调用方只能给文本，给不了别的。

## 把连接当参数传进来 {#example}

把"存到哪里"变成参数。新建 `di_demo.py`：

```python
import sqlite3


class SqliteStore:
    def __init__(self, path=":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS messages (text TEXT)")
        self.conn.commit()

    def add(self, text):
        cur = self.conn.execute("INSERT INTO messages (text) VALUES (?)", (text,))
        self.conn.commit()
        return cur.lastrowid

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]


def save_message(store, text):
    return store.add(text)


store = SqliteStore()
print(save_message(store, "第一条"))
print(save_message(store, "第二条"))
print(store.count())
```

运行：

```bash
python di_demo.py
```

你应该看到：

```
1
2
2
```

三行输出分别是两次插入的 id 和总条数。`cur.lastrowid` 是 SQLite 给刚插入那行分配的编号，所以第一次是 1，第二次是 2。`save_message` 只做一件事：把文本交给 `store.add`。它不知道 `store` 是 `SqliteStore` 还是别的东西，也不负责关连接。

现在换一个只存在内存里的假仓库，测试不需要碰磁盘：

```python
class FakeStore:
    def __init__(self):
        self.rows = []

    def add(self, text):
        self.rows.append(text)
        return len(self.rows)


fake = FakeStore()
save_message(fake, "测试消息")
print(fake.rows)
```

输出：

```
['测试消息']
```

同一个 `save_message`，生产时拿到 `SqliteStore`，测试时拿到 `FakeStore`。**这就是注入**：需要的能力从外面传进来，而不是在函数里造出来。

## 构造函数注入与它的生命周期 {#constructor}

参数注入是最小形式。当好几个方法都要用同一个依赖时，把它存到对象上，叫构造函数注入：

```python
class MessageService:
    def __init__(self, store):
        self.store = store

    def post(self, text):
        if not text.strip():
            raise ValueError("消息不能为空")
        return self.store.add(text)


service = MessageService(SqliteStore())
print(service.post("你好"))
try:
    service.post("   ")
except ValueError as exc:
    print("拒绝：", exc)
```

你应该看到：

```
1
拒绝： 消息不能为空
```

`MessageService` 里没有 `import sqlite3`。它只知道传进来的东西有一个 `add` 方法。数据库换类型、测试换假实现，都不用改这个类。

**生命周期是另一个决定：这个 `store` 活多久。** 每次请求新建，隔离好，但每次都要握手；全局只建一个，省资源，可多个线程共用同一个连接时，很多驱动并不安全，连接断了也不会自己恢复。

```python
from functools import lru_cache

class Probe:
    made = 0
    def __init__(self):
        Probe.made += 1

@lru_cache(maxsize=1)
def get_shared_probe():
    return Probe()

print(Probe.made)        # 0，函数还没调用
a = get_shared_probe()
b = get_shared_probe()
print(Probe.made)        # 1，只构造了一次
print(a is b)            # True
```

输出：

```
0
1
True
```

`lru_cache` 把一个函数变成"第一次调用时创建、以后复用"的提供者。Web 服务里更常见的做法是**每个请求一个连接或会话**，请求结束就关；连接本身从连接池借，借还的成本比重新握手低得多。

## FastAPI 的 Depends 做了什么 {#fastapi-depends}

`Depends` 不是自动扫描你的类。它做一件事：看处理函数的参数上写了什么，替你调用那个提供者，把返回值塞进参数。

这段需要先 `pip install fastapi`：

```python
from fastapi import Depends, FastAPI

app = FastAPI()


def get_store():
    store = SqliteStore("app.db")   # 每请求一个连接；生产通常从连接池借
    try:
        yield store          # 请求处理期间用这个
    finally:
        store.conn.close()   # 响应发完后关闭


@app.post("/messages")
def create_message(text: str, store: SqliteStore = Depends(get_store)):
    return {"id": store.add(text)}
```

框架看到 `Depends(get_store)`，就调用 `get_store`。如果它用了 `yield`，框架先拿到 `store`，等请求结束再执行 `finally`。这就是"依赖的生命周期挂在请求上"的具体含义。

测试时不必真的起数据库：

```python
app.dependency_overrides[get_store] = lambda: FakeStore()
```

`dependency_overrides` 是一张替换表：键是原来的提供者函数，值是替代品。框架解析到 `get_store` 时先查这张表。**替换点只有一处，而且写在明面上**，这是注入最直接的收益。

同一次请求里，框架默认会缓存同一个依赖的结果。两个函数都声明 `Depends(get_store)`，拿到的是同一个对象，不会建两次连接。

## 注入能力，不注入配置值 {#capability}

初学者容易把注入理解成"把参数传进去"，于是写成这样：

```python
def save_message(db_url: str, text: str):
    conn = sqlite3.connect(db_url)
    ...
```

`db_url` 是传进来了，可"怎么连、连完谁关、用哪个驱动"还锁在函数里。测试时你还是得准备一个真能连的地址。**配置值只是原料，能力才是依赖。**

判断方法：把传进来的东西按住，问一句"我能用一个不碰外部世界的假货替换它吗？"

- `db_url="postgres://..."`：换不成假的，函数仍会真的去连。
- `store` 对象：换成 `FakeStore()` 就行。

所以配置该在启动时读一次，转成明确的值再传下去；而数据库、HTTP 客户端、时钟、随机数、文件系统这类会碰外部世界、测试时想控制的东西，才值得做成可注入的能力。

## 容易想反的四件事 {#pitfalls}

**"全局变量也算注入。"** 不算。全局变量是隐式依赖：函数签名上看不出它用了数据库，替换它要改模块级状态，测试之间还会互相污染。注入的关键是"从参数进来"，不是"不在函数里创建"。

**"`Depends` 是 FastAPI 的装饰器魔法。"** `Depends(get_store)` 只是返回一个标记对象，真正的解析发生在框架调用处理函数之前。你在普通 Python 里写 `def handler(store=Depends(get_store))` 然后直接调用 `handler()`，拿到的是那个标记，不是 `store`。离开框架，它不会自己工作。

**"名字叫 `get_db` 就是依赖注入。"** 项目里经常有同名的自定义函数。判断依据是调用点：它是被当成参数传进去的，还是在函数体里被直接调用的？后者只是换了名字的硬编码。

**"注入以后测试就一定可靠。"** 假实现如果返回生产里不可能出现的结果，测试会给你假的安心。`FakeStore.add` 永远不抛异常，而真实数据库可能超时、可能违反唯一约束——那些路径你的测试根本没走到。假货要模仿约定，包括失败。

## 多一层间接的代价 {#tradeoffs}

多一个参数，读代码时就多跳一步：`save_message(store, text)` 里的 `store` 是哪来的？要找到装配的地方。依赖链深了，这个问题会重复好几次。

所以不必给每个小函数都注入。函数只做纯计算、不碰外部世界，或者只有一个实现且永远不会替换，直接调用更清楚。真正值得注入的是边界：数据库、外部 API、文件系统、时间、随机源。这些地方一换，测试和本地开发都轻松很多。

还有一个成本是装配代码。对象不会自己出现，总得有人在入口把它们连起来：读配置、建连接池、构造 service。这部分代码集中放一处，比散落在各个函数里好找。

判断标准可以很朴素：**这个依赖在测试里会不会让你难受？** 会，就注入；不会，就先别加。

## 练习 {#self-check}

**第 1 题**：下面这个函数为什么难测试？改成可注入的写法。

```python
from datetime import datetime

def is_expired(token):
    return token["expires_at"] < datetime.now()
```

> **答案**
>
> 它直接读了系统时钟。测试想验证"刚好过期"和"还差一秒"，只能等真实时间，或者改系统时间。
>
> 把"现在几点"变成参数：
>
> ```python
> def is_expired(token, now):
>     return token["expires_at"] < now
> ```
>
> 测试传固定的 `now`，边界条件就能精确构造。

**第 2 题**：FastAPI 处理函数的参数上已经写了 `Depends(get_store)`，为什么函数体里不能再调用一次 `get_store()`？

> **答案**
>
> 再调一次会绕过框架的解析：新建一个连接，还没人负责关闭；同一次请求里用了两个不同的会话，事务也串不起来。
>
> 要用就直接用参数 `store`。`Depends` 的意义就是让框架管创建和清理，自己再建一个，等于把注入绕开了。

**第 3 题**：`db_url` 和 `db` 对象，哪个该注入？为什么？

> **答案**
>
> `db` 对象。`db_url` 只是字符串，函数拿到它还得自己决定驱动、建连接、处理关闭；测试时也无法用一个纯内存的假货替代。
>
> `db` 对象把"怎么连"关在提供者里，函数只调用约定好的方法。测试传一个实现同样方法的假对象就行。

## 继续阅读 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [抽象基类与协议：约定可以替换的能力](/learn/abstract-base)
- [ORM：用对象读写数据库](/learn/orm)
- [连接池：复用连接而不是每次重连](/learn/connection-pool)

## 参考资料 {#sources}

- [FastAPI：依赖注入与安全](https://fastapi.tiangolo.com/tutorial/dependencies/)；作者：Sebastián Ramírez and contributors；MIT。版本：导入日网页快照; sha256:ae1f492784c1ccdc3f7f85f358c3f217f710fc4993ea3759561509601a131d04。
