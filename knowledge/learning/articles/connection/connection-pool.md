# 连接池：复用连接并限制并发

## 每次请求都重新连一次 {#overview}

学完这一篇，你能测出新建连接的成本，手写一个借还连接的小池子，并看懂池耗尽、泄漏和死连接各自意味着什么。

你写了一个小查询服务，每个请求都做同一串动作：连上服务端、发一句、收一句、断开。单人测试时它很快，因为一次只有一个请求，等待也不长。

并发一上来，问题就换位置了。每次请求都要重新握手，服务端要为新连接分配状态，TLS、认证、会话参数这些步骤也可能重来。真正处理请求只占一小段，剩下都是重复准备。

连接池把这段准备抽出来：先建好固定数量的连接，放在空闲队列里。请求来了借一条，用完还回去，下个请求接着用同一条。

它还是一道上限。池里只有 5 条连接，数据库就最多同时收到这套服务发来的 5 条连接。性能和容量边界是同一件事的两面。

## 量一次建连开销 {#new-connection-cost}

先别急着写池子。用一个本机回环地址上的回声服务，分别测“每次新建连接”和“复用同一条连接”各发 2000 次请求，差多少一眼就能看到。

新建 `connect_cost.py`：

```python
import socket
import threading
import time
from socketserver import BaseRequestHandler, ThreadingTCPServer

HOST = "127.0.0.1"
REQUESTS = 2000

class Echo(BaseRequestHandler):
    def handle(self):
        while data := self.request.recv(1024):
            self.request.sendall(b"ok")

server = ThreadingTCPServer((HOST, 0), Echo)
server.daemon_threads = True  # 客户端没关干净时，进程也能退出
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]

def one_request():
    with socket.create_connection((HOST, port)) as sock:
        sock.sendall(b"ping")
        return sock.recv(2)

started = time.perf_counter()
for _ in range(REQUESTS):
    one_request()
new_time = time.perf_counter() - started

with socket.create_connection((HOST, port)) as sock:
    started = time.perf_counter()
    for _ in range(REQUESTS):
        sock.sendall(b"ping")
        sock.recv(2)
    reuse_time = time.perf_counter() - started

print(f"{REQUESTS} 次请求，每次新建连接：{new_time:.1f} 秒")
print(f"{REQUESTS} 次请求，复用一条连接：{reuse_time:.1f} 秒")

server.shutdown()
server.server_close()
```

运行 `python connect_cost.py`。数字每次会浮动，你会看到类似：

```
2000 次请求，每次新建连接：1.6 秒
2000 次请求，复用一条连接：0.1 秒
```

这段代码里有两个循环，做的事几乎一样。

第一个循环的 `one_request` 每次都执行 `socket.create_connection`，然后退出 `with`，连接关闭。客户端要和服务端完成一次 TCP 建连，服务端也要接受一个新 socket。

第二个循环先连一次，之后在同一条连接上反复 `sendall` 和 `recv`。没有新的握手，没有新的 accept。

这不是在说“建连一定贵”。它是在同一台机器、同一段时间里做了对照：在这组输出中，2000 次多出来的约 1.5 秒，摊到每次大约 0.75 毫秒。真实数据库还要加上网络往返、TLS、认证和会话初始化，不能拿这个毫秒数直接当生产估算。但“每个请求都重新准备一遍”这件事确实有成本。

## 借出、归还、耗尽与泄漏 {#borrow-return}

池子内部通常就是一个空闲队列。借出时从队列取一条，归还时放回队尾。池子负责记住“现在有几条在外面”，并保证不会超过上限。

上限有两种表达方式。手写池常用固定长度队列，比如 2 条。SQLAlchemy 用 `pool_size` 表示常驻池大小，`max_overflow` 允许高峰期临时多开几条。`pool_timeout` 则是借不到时愿意等多久。

队列空了，也就是池耗尽，通常有两个选择。

**等。** 调用方阻塞在队列上，等别人归还。这会增加延迟，但不会把数据库压垮。等太久也不行，请求会堆在服务里。

**立刻失败。** 设一个很短的超时，借不到就抛 `TimeoutError`，让上层决定重试还是降级。失败得快，至少不会无声地卡住。

最怕的是没有上限：请求一多就无限新建连接，数据库的连接数、内存和锁竞争一起上来，最后所有请求都变慢。池子把排队从数据库挪到了应用里，前提是这个队列有边界。

连接泄漏是另一种耗尽。代码借了连接，却因为异常、提前 `return` 或忘了写释放逻辑，没有归还。池子以为它还在外面，空闲队列越来越短，最后所有请求都借不到。借出的连接可能已经空闲，数据库也不忙，但池子无法再使用它。

写代码时用 `try/finally`，或者用库提供的上下文管理器，例如 SQLAlchemy 的 `with engine.connect() as conn:`。退出 `with` 时，无论正常结束还是抛异常，连接都会归还。归还前还要清掉未提交事务和会话状态；否则下一个借到它的人会继承上一段工作的残留。SQLAlchemy 的池会做这部分重置，手写池通常没有。

还有一种情况是连接失效。数据库重启、防火墙断开空闲连接、代理设置了空闲超时，池里那条看起来空闲的 socket 其实已经死了。借出前应该探活，比如发一条 `SELECT 1` 或 ping。探活和真正查询之间仍有时间窗，所以生产代码还要处理“刚探活完就断开”的错误，必要时对幂等操作重试一次。

## 写一个只做四件事的池子 {#minimal-pool}

下面这个池子只做四件事：固定上限、借出、归还、借出前探活。它用 `queue.Queue` 保存空闲连接，用本机回声服务当数据库。

新建 `pool_demo.py`：

```python
import queue
import select
import socket
import threading
from socketserver import BaseRequestHandler, ThreadingTCPServer

HOST = "127.0.0.1"

class Echo(BaseRequestHandler):
    def handle(self):
        while data := self.request.recv(1024):
            self.request.sendall(b"ok")

server = ThreadingTCPServer((HOST, 0), Echo)
server.daemon_threads = True
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]

def connect():
    return socket.create_connection((HOST, port))

def call(sock):
    sock.sendall(b"ping")
    return sock.recv(2).decode()

class PooledConnection:
    def __init__(self, serial, sock):
        self.serial = serial
        self.sock = sock

class SimplePool:
    def __init__(self, factory, size, timeout=0.2):
        self.factory = factory
        self.timeout = timeout
        self.idle = queue.Queue(maxsize=size)
        self.created = 0
        self.lock = threading.Lock()
        for _ in range(size):
            self.idle.put(self._new())

    def _new(self):
        with self.lock:
            self.created += 1
            serial = self.created
        # 编号只用于观察哪条连接被替换
        return PooledConnection(serial, self.factory())

    @staticmethod
    def _alive(conn):
        try:
            readable, _, _ = select.select([conn.sock], [], [], 0)
            if not readable:
                return True
            return bool(conn.sock.recv(1, socket.MSG_PEEK))
        except (OSError, ValueError):
            return False

    def borrow(self):
        try:
            # 空闲队列空时等一会儿，超时就明确失败，别无限挂住
            conn = self.idle.get(timeout=self.timeout)
        except queue.Empty:
            raise TimeoutError(f"{self.timeout} 秒内没有空闲连接") from None
        if not self._alive(conn):
            print(f"连接 #{conn.serial} 已失效，替换成新的")
            conn.sock.close()
            conn = self._new()
        return conn

    def release(self, conn):
        # 真实池子会在这里回滚未提交事务并重置会话状态
        self.idle.put(conn)

    def close(self):
        while True:
            try:
                conn = self.idle.get_nowait()
            except queue.Empty:
                break
            conn.sock.close()

pool = SimplePool(connect, size=2)

first = pool.borrow()
print(f"借到连接 #{first.serial}，收到 {call(first.sock)}")
pool.release(first)

second = pool.borrow()
print(f"再次借到连接 #{second.serial}")
third = pool.borrow()
print("两条连接都在手里")

try:
    pool.borrow()
except TimeoutError as exc:
    print(f"第三次借用失败：{exc}")

second.sock.close()
third.sock.close()
pool.release(second)
pool.release(third)

for _ in range(2):
    fresh = pool.borrow()
    print(f"再次借到连接 #{fresh.serial}，收到 {call(fresh.sock)}")
    pool.release(fresh)

pool.close()
server.shutdown()
server.server_close()
```

运行 `python pool_demo.py`，你会看到：

```
借到连接 #1，收到 ok
再次借到连接 #2
两条连接都在手里
第三次借用失败：0.2 秒内没有空闲连接
连接 #2 已失效，替换成新的
再次借到连接 #3，收到 ok
连接 #1 已失效，替换成新的
再次借到连接 #4，收到 ok
```

第一步，`SimplePool` 初始化时直接建了两条连接，放进 `idle` 队列。真实连接池通常懒创建：第一条连接在第一次借出时才建，之后慢慢补到上限。这里为了输出简单，启动时就建好。

第二步，第一次 `borrow()` 取到 #1。`release` 把它放到队尾，所以下一次取到的是 #2。两条都在外面时，队列空了。

第三步，第三次 `borrow()` 在队列上等 0.2 秒。没人归还，`queue.Empty` 被转换成 `TimeoutError`。这就是池耗尽。如果超时设成 30 秒，这个请求会在这里停 30 秒，用户只会觉得服务挂了。

第四步，代码把 `second` 和 `third` 的底层 socket 都关掉，再归还。下一次借到死连接时，`_alive` 发现 socket 已关闭，于是新建 #3；再下一次新建 #4。真实池子的探活通常是执行一条轻量 SQL，而不是看 socket 是否可读。socket 看起来正常，不代表数据库会话还能用。

第五步，`close()` 把空闲连接关掉，`server.shutdown()` 停掉回声服务。注意 `queue.Queue` 本身是线程安全的，但一条借出的连接仍然不能同时给两个线程使用。

这段实现没有跟踪重复归还，没有处理归还时的未提交事务，也没有溢出连接、公平性和复杂的探活。它适合用来理解借还流程，不要直接搬进生产。

## SQLAlchemy 的池多了什么 {#sqlalchemy-pool}

SQLAlchemy 的引擎内部也是同一套借还模型，只是补上了更多边界条件。先装库：

```bash
pip install "sqlalchemy>=2.0"
```

```python
from sqlalchemy import create_engine

engine = create_engine(
    "sqlite:///pool_demo.db",
    pool_size=5,
    max_overflow=2,
    pool_timeout=3,
    pool_pre_ping=True,
)

with engine.connect() as conn:
    print(conn.exec_driver_sql("SELECT 1").scalar_one())

engine.dispose()
```

你应该看到：

```
1
```

`pool_size=5` 是常驻池大小，`max_overflow=2` 允许高峰时临时多开 2 条，所以同一时刻最多可能有 7 条。`pool_timeout=3` 表示借不到时最多等 3 秒。`pool_pre_ping=True` 会在借出前做一次轻量探测，发现连接已死就换一条。

`with engine.connect()` 和手写池的 `borrow` / `release` 是同一件事：进入时借出，退出时归还，即使中间抛异常也会归还。`engine.dispose()` 关闭池里的连接，通常在服务停止时调用。

SQLAlchemy 的池还会在归还时回滚未结束的事务，支持不同的池实现（例如不缓存的 `NullPool`），并按 URL 和驱动选择策略。SQLite 的文件库和内存库就可能落在不同的池类型上，具体要看 SQLAlchemy 版本和连接 URL；不要拿一个后端的行为去推另一个后端。

ORM 的 `Session` 在这一层之上。Session 执行查询时会向池子借连接，结束或关闭时归还；池子管的是网络连接，Session 管的是对象和事务。两者不是一个东西。

## 五个关于池的误会 {#pitfalls}

**“池设得越大，数据库越能扛。”** 数据库有 `max_connections`，每条连接都要内存和调度开销，锁竞争也可能更严重。4 个服务实例各开 10 条，数据库看到的是 40 条，不是 10 条。池子大只会让更多请求同时压到数据库。

**“连接归还就是关闭。”** 不是。归还是把连接放回空闲队列，TCP 连接还在，下一次可以直接用。这也是连接池省下建连成本的原因。要真正关闭，得关闭池或调用 `engine.dispose()`。

**“池子保证同一条连接能被多个线程同时用。”** 不保证。池子只保证一条连接在同一时刻只借给一个使用者。数据库连接对象通常不适合并发共享；SQLite 默认还会检查创建线程，跨线程使用会报 `SQLite objects created in a thread can only be used in that same thread`。

**“借了没还只是浪费一条连接。”** 一条是小事，次数多了就是耗尽。上面的输出里两条连接都被占住，第三次借用就超时了；如果泄漏发生在每个请求里，池子会稳定地卡死，重启往往只是暂时缓解。

**“`Session` 就是池里的一条连接。”** 不是。`Session` 是工作单元，可能在不同时间借用和归还连接；连接池在更下面。把 Session 当连接池，容易在错误的层级共享对象和事务。

## 池子该开多大 {#tradeoffs}

先数并发，再填数字。一个服务实例同时有多少个请求需要等数据库？数据库允许的总连接数是多少？如果部署 4 个实例，每个 `pool_size=10`，数据库看到的是 40 条，不是 10 条。超过数据库上限时，多出来的连接会在连接阶段失败，而不是变快。

池大小还要看每个请求占用连接多久。一个长事务会一直占着连接，哪怕它大部分时间在等应用处理。把事务缩短，比盲目加大池子更有效。

短脚本和一次性任务通常不需要连接池。建一条连接，做完就关，代码更少，也不会考虑超时和泄漏。长期运行的服务才需要关注借出上限、等待超时、探活和监控。

`max_overflow` 是应对短时突发的缓冲，不是常态容量。长期靠溢出连接工作，等于把上限调大却没有承认。池的指标里，借出等待时间和当前借出数比“池有多大”更能说明问题。

读项目代码时，先找 `create_engine` 的参数，再看谁持有 `connect()` 或 `Session` 的作用域。连接在哪一层被借出、哪一层归还，通常比池大小更决定它会不会泄漏。

## 三次借还的检查 {#self-check}

**第 1 题**：池大小是 1。你借出连接后，函数因为异常提前返回，没有 `release`。下一个请求来借连接，会看到什么？

> **答案**
>
> 空闲队列一直是空的。下一个请求会等到超时，然后收到 `TimeoutError`，或者一直卡住（取决于超时设置）。
>
> 正确写法是把借用放进 `try/finally`，或者使用库的上下文管理器：
>
> ```python
> conn = pool.borrow()
> try:
>     do_work(conn)
> finally:
>     pool.release(conn)
> ```

**第 2 题**：`pool_size=5`、`max_overflow=2`、`pool_timeout=3`。10 个请求同时来，前面 7 个一直不归还，剩下的 3 个会怎样？

> **答案**
>
> 前 7 个借到连接（5 条常驻 + 2 条溢出）。后 3 个在池边等待 3 秒；如果这 3 秒内没有人归还，它们会收到超时错误。若服务没有处理这个错误，用户看到的是请求失败或长时间无响应。

**第 3 题**：数据库刚重启，池里有一批空闲连接。`pool_pre_ping=True` 能保证下一次查询一定成功吗？

> **答案**
>
> 不能保证。它只是在借出前探测一次。探测通过后、真正查询前，连接仍然可能被断开。
>
> 它能减少把死连接交给业务代码的概率，但业务仍要处理连接错误。对幂等操作可以重试一次；对已经产生副作用的操作，重试前得先确认是否真的没执行。

## 从池子走向 ORM {#related}

- [ORM：对象与关系数据之间的映射](/learn/orm)
- [事务：让多步数据库修改共同完成](/learn/sql-transactions)
- [索引与查询代价](/learn/sql-indexes)
- [线程池：受控执行阻塞工作](/learn/thread-pool)

## 连接池的参考文档 {#sources}

- [SQLAlchemy ORM and Core](https://docs.sqlalchemy.org/en/20/intro.html)；作者：SQLAlchemy authors and contributors；MIT。版本：SQLAlchemy 2.0; sha256:db74e1fff59364aa035a0f11028c529ba04c3519dfe1cc9960cea4da6bda7c61。
