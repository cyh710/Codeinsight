# 线程池：受控执行阻塞工作

## 线程在等什么 {#overview}

学完这一篇，你能用 ThreadPoolExecutor 提交并收集任务，把阻塞调用移出异步事件循环，并用锁保护多线程共享的计数器。

一个整理账单的命令要读一批文件。它的大部分时间在等磁盘，解析本身很快；串行做下来，等待一段接一段。时间几乎都花在等，而不是算。

线程能在这段等待里做别的事。线程池再往前一步：不每次新建线程，而是维持固定数量的工作线程，任务提交到队列，谁空了谁取。它同时限制最多有多少任务在跑。

线程池解决“怎么受控地等”，不解决“怎么让 Python 计算并行”。这两件事经常被混在一起。

## GIL 下的两段计时 {#gil-timing}

新建 `thread_timing.py`：

```python
import time
from concurrent.futures import ThreadPoolExecutor

N = 8_000_000

def burn(n):
    total = 0
    for i in range(n):
        total += i * i
    return total

def wait(_):
    time.sleep(0.5)

started = time.perf_counter()
burn(N)
burn(N)
print(f"CPU 任务，顺序两遍：{time.perf_counter() - started:.1f} 秒")

started = time.perf_counter()
with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(burn, [N, N]))
print(f"CPU 任务，两个线程：{time.perf_counter() - started:.1f} 秒")

started = time.perf_counter()
for _ in range(4):
    wait(None)
print(f"等待任务，顺序四次：{time.perf_counter() - started:.1f} 秒")

started = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(wait, range(4)))
print(f"等待任务，四个线程：{time.perf_counter() - started:.1f} 秒")
```

运行 `python thread_timing.py`，你会看到类似：

```
CPU 任务，顺序两遍：0.9 秒
CPU 任务，两个线程：0.9 秒
等待任务，顺序四次：2.0 秒
等待任务，四个线程：0.5 秒
```

前两行几乎一样。`burn` 是纯 Python 循环，两个线程各算一遍，总时间没有减半。CPython 的标准构建有全局解释器锁（GIL），同一时刻只允许一个线程执行 Python 字节码。另一个线程可以持有数据、可以等在 I/O 上，但不能同时跑 Python 计算。

后两行差四倍。`time.sleep` 是等待，不是计算。线程进入睡眠时会释放 GIL，另外三个线程可以继续进入睡眠；四个 0.5 秒的等待重叠起来，总时间接近 0.5 秒。

真实网络请求、磁盘读写、数据库查询也是等待。它们大多会在底层系统调用期间释放 GIL，所以线程池能提高这类任务的吞吐。

这条边界要记清楚：线程适合“等”，不适合“算”。纯 Python 的 CPU 密集任务换成进程更有效；如果某个 C 扩展在自己的计算里释放 GIL，多线程可能有用，但那是扩展的行为，不是 Python 线程的普遍保证。

## 提交、取结果与队列 {#submit-and-result}

`ThreadPoolExecutor` 有两种常用接口：`submit` 返回 `Future`，`map` 按输入顺序返回结果。

```python
import time
from concurrent.futures import ThreadPoolExecutor

def load(name):
    time.sleep(0.3)
    return f"{name} 已读取"

with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(load, name) for name in ("账单", "收据", "合同")]
    for future in futures:
        print(future.result())
```

输出：

```
账单 已读取
收据 已读取
合同 已读取
```

三个任务只有两个工作线程。`submit` 立刻返回 `Future`，不等待函数执行完；第三个任务先排队。前两个各睡 0.3 秒，第三个等其中一个线程空出来。总耗时约 0.6 秒。

`future.result()` 会阻塞调用线程，直到这个任务完成；如果任务抛了异常，`result()` 会把异常重新抛出来。只 `submit` 不取结果，异常可能一直没人看见。

离开 `with` 时会调用 `shutdown(wait=True)`，等待已提交任务结束。想取消尚未开始的任务，可以显式调用 `pool.shutdown(wait=True, cancel_futures=True)`。但 `Future.cancel()` 只能取消还在队列里的任务；已经开始执行的线程函数没有强制终止的办法，需要函数自己检查取消标志。

这里有一个容易忽略的容量问题：`max_workers` 限制同时执行的数量，不限制提交的数量。`ThreadPoolExecutor` 的内部工作队列没有公开的容量上限。你循环提交十万个任务，线程仍只开 2 到 4 个，剩下十万个会在队列里等着，内存和延迟一起涨。

需要背压时，在提交端加限制：用 `BoundedSemaphore` 控制未完成任务数，或者用有界 `queue.Queue` 让生产者等消费者。不要指望把 `max_workers` 调大来解决积压，那只是把压力更快地推给下游。

## 把阻塞调用挪出事件循环 {#to-thread}

在线程池里等 I/O 没问题，在异步事件循环里直接等 I/O 则会堵住所有协程。`asyncio.to_thread` 把阻塞函数交给默认线程池，事件循环继续调度别的任务。

```python
import asyncio
import time

async def heartbeat():
    for i in range(1, 5):
        await asyncio.sleep(0.2)
        print(f"心跳 {i}")

def blocking_io():
    print("开始 time.sleep")
    time.sleep(0.7)
    print("结束 time.sleep")

async def main():
    ticker = asyncio.create_task(heartbeat())
    await asyncio.to_thread(blocking_io)
    await ticker

asyncio.run(main())
```

输出：

```
开始 time.sleep
心跳 1
心跳 2
心跳 3
结束 time.sleep
心跳 4
```

`blocking_io` 在另一个线程里睡眠 0.7 秒，事件循环没有停。心跳任务按 0.2 秒的节奏插进来。

如果写成 `await blocking_io()` 会怎样？Python 会先执行这个普通函数，阻塞 0.7 秒，然后因为返回的 `None` 不能 `await` 而报 `TypeError`。写成 `blocking_io()` 则只是同步阻塞当前线程，心跳全部推迟。`to_thread` 的关键不是“线程一定更快”，而是把阻塞从事件循环线程挪到工作线程。

代价也在那里。每次调用会占用默认线程池里的一个线程，池满后其他 `to_thread` 调用要排队；线程切换和上下文搬运也有成本。库本身提供异步接口时，优先用异步接口，别把同步库硬塞进 `to_thread` 再假装全链路异步。

取消也要小心。`asyncio.wait_for` 超时只会取消等待，已经进入线程的函数通常还会继续执行。`to_thread` 适合幂等或可以安全重试的阻塞调用；需要严格停止的外部操作，得靠库自身支持超时和取消。

线程安全也是边界。不要把主线程创建的数据库连接直接交给多个工作线程；SQLite 默认会检查连接创建线程，跨线程使用会报错。让每个线程在里面建立自己的资源，或者用连接池按线程借出。

## 计数器为什么少了 {#thread-safety}

线程池提供线程，不提供线程安全。下面这个计数器在八个线程里各加一次，一次不加锁，一次加锁：

```python
import threading
from concurrent.futures import ThreadPoolExecutor

def bump_unsafe(counter, barrier):
    value = counter["value"]
    barrier.wait()  # 强制所有线程先读到旧值，让竞争稳定复现
    counter["value"] = value + 1

def bump_locked(counter, lock, barrier):
    barrier.wait()
    with lock:
        counter["value"] += 1

def count(bump, locked):
    counter = {"value": 0}
    barrier = threading.Barrier(8)
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=8) as pool:
        if locked:
            list(pool.map(lambda _: bump(counter, lock, barrier), range(8)))
        else:
            list(pool.map(lambda _: bump(counter, barrier), range(8)))
    return counter["value"]

print(f"不加锁的计数：{count(bump_unsafe, False)}")
print(f"加锁后的计数：{count(bump_locked, True)}")
```

输出：

```
不加锁的计数：1
加锁后的计数：8
```

八个线程都执行一次 `+1`，不加锁最后却只有 1。原因在 `counter["value"] = value + 1` 不是一条不可分割的操作：先读，再算，再写。`Barrier` 让八个线程都停在读完 `0` 的地方，然后一起写 `1`。最后一次写覆盖了前面的写。

真实代码里的竞争通常没这么整齐。线程可能在任意两条字节码之间切换，所以结果可能是 7、6 或其他数字，甚至偶尔正好正确。不能因为测试跑对了一次就认为安全。

加锁版把读、加、写都放进 `with lock`，八个线程只能一个接一个完成这三步，最后是 8。锁的范围要覆盖整个不变量，只锁赋值那一行没有用。

锁不要包住慢操作。持锁期间做网络请求、读大文件或等待另一个锁，会让其他线程排长队，还可能死锁。共享计数器、共享缓存这类短小的状态修改适合加锁；如果每个任务只处理自己的数据，就不需要锁。`queue.Queue` 本身是线程安全的，适合在生产者和消费者之间传数据。

## 五个关于线程的错判 {#pitfalls}

**“线程数越多越快。”** 不。CPU 计算受 GIL 限制，多开线程只是增加切换；I/O 任务也要看下游连接数和限流。上面的 CPU 两线程没有比串行快，等待任务变快是因为等待重叠，不是因为线程数量本身。

**“`submit` 返回了，任务就完成了。”** 不。`submit` 只是把任务放进队列并给你一个 `Future`。要完成，得等 `future.result()` 返回，或者用 `as_completed` 处理结果。忘记取结果，异常可能被静默吞掉。

**“`Future.cancel()` 能杀掉正在执行的函数。”** 不能。它只能取消还没开始的任务。已经进入线程的 Python 函数不会因为 `cancel()` 被中断，需要函数自己检查停止标志并退出。

**“用了线程池，共享对象就自动安全了。”** 线程池只负责调度，不会给被调用的函数加锁。上面的计数器不加锁就丢了 7 次更新。数据库连接、文件句柄、缓存也有各自的线程约束，不能因为“都在池里”就共享。

**“`async def` 函数可以像普通函数一样 `submit` 给线程池。”** 不能直接这样用。`submit` 会返回一个 `Future`，它的结果是协程对象，函数体没有执行，还可能出现“never awaited”警告。要么在异步上下文里 `await` 它，要么在线程里用 `asyncio.run` 单独运行（这会新建事件循环，不适合和已有循环混用）。

## 线程、进程还是协程 {#tradeoffs}

| 任务 | 更合适的选择 | 原因 |
|---|---|---|
| 阻塞 I/O，库只有同步版 | 线程池 | 等待时释放 GIL，能重叠 |
| 高并发网络，库支持异步 | 协程 | 单线程调度，任务切换开销小 |
| 纯 Python CPU 密集 | 进程池 | 绕开 GIL，真正多核 |
| 一次性、少量工作 | 同步 | 少一层调度和生命周期 |

线程池大小要从下游反推。数据库连接池只有 10 条，应用开 100 个线程去查，多出来的只会等连接，还可能把数据库拖慢。外部 API 有限流，线程数超过限额同样会失败。`max_workers` 是并发边界，不是性能旋钮。

CPU 任务用 `ProcessPoolExecutor` 时，参数和返回值要能序列化，进程启动也有成本。任务太短时，进程调度开销可能超过收益。进程之间不共享内存，计数器反而不用加锁，但要用队列或返回值传结果。

协程适合大量等待，但要求依赖链上的库也支持异步；否则一个阻塞调用就堵住整个循环。线程适合把已有的同步库包起来，代价是线程内存、切换和共享状态。两类任务最好分池，别让慢文件读写占满处理网络请求的线程。

关闭时统一处理：用上下文管理器等待任务，给阻塞调用设超时，记录队列长度和拒绝数。线程池本身不保证任何业务对象线程安全，边界处的锁和资源隔离仍然要自己写。

## 选择线程、锁或进程 {#self-check}

**第 1 题**：一台 8 核机器上跑纯 Python 的批量计算。用 `ThreadPoolExecutor(max_workers=8)` 会比单线程快 8 倍吗？

> **答案**
>
> 不会。CPython 标准构建的 GIL 让同一时刻只有一个线程执行 Python 字节码，八个线程只是轮流算，通常和单线程差不多，甚至更慢。
>
> 纯 Python CPU 任务应该用 `ProcessPoolExecutor` 或其他多进程方案；能释放 GIL 的 C 扩展是例外，需要实测。

**第 2 题**：四个互不依赖的同步 HTTP 请求各等 1 秒。用 `ThreadPoolExecutor(max_workers=4)` 和串行执行，总时间大约是多少？

> **答案**
>
> 线程池约 1 秒，串行约 4 秒。四个线程都在等网络，等待期间释放 GIL，所以四段等待可以重叠。
>
> 前提是下游能同时处理四个请求；如果连接池或服务端限流只允许一个，并发就会在别处排队。

**第 3 题**：两个线程都要执行 `counter["value"] += 1`。锁应该加在哪一行？

> **答案**
>
> 锁要包住整个“读—加—写”过程：
>
> ```python
> with lock:
>     counter["value"] += 1
> ```
>
> 只锁读取或只锁写入都不够，因为另一个线程仍可能在读和写之间插进来。锁的范围还应尽量短，不要把网络请求或文件读写包在里面。

## 从线程走向进程与协程 {#related}

- [异步编程：等待期间让出执行机会](/learn/async)
- [连接池：复用连接并限制并发](/learn/connection-pool)
- [文件锁：协调对共享文件的访问](/learn/file-lock)
- [数据库事务：一致完成状态转换](/learn/db-transaction)

## 线程池的参考文档 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
