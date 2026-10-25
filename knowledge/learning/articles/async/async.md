# 异步编程：等待期间让出执行机会

## 等网络时，整个程序停住了 {#overview}

学完这一篇，你能用 asyncio 并发等待多个网络请求，看懂事件循环何时切换协程，并识别会堵死循环的阻塞调用。

留言板服务要查三个依赖：用户资料、留言列表、通知数量。每次查询都要等 1 秒，串行做就是 3 秒。可这 3 秒里，程序大部分时间只是在等网络，CPU 并没有忙。

同步代码的表达方式很直接：做完第一步，等结果；再做第二步，等结果。等待期间，当前线程被占住，别的请求也排在这条线后面。

异步编程换了一个调度方式。遇到需要等待的操作，它先把当前任务挂起，让事件循环去做别的任务；等结果回来，再接着执行 `await` 后面的代码。

它不会让单次等待变短。三次各等 1 秒，并发做仍然至少要 1 秒，只是不用把三段等待首尾相接。

## 三次一秒的等待 {#gather-experiment}

新建 `async_demo.py`：

```python
import asyncio
import time

async def wait_one(name):
    print(f"{name} 开始")
    await asyncio.sleep(1.0)
    print(f"{name} 结束")

async def serial():
    started = time.perf_counter()
    for name in ("甲", "乙", "丙"):
        await wait_one(name)
    return time.perf_counter() - started

async def concurrent():
    started = time.perf_counter()
    await asyncio.gather(*(wait_one(name) for name in ("甲", "乙", "丙")))
    return time.perf_counter() - started

async def main():
    serial_time = await serial()
    print(f"串行总耗时：{serial_time:.1f} 秒\n")

    concurrent_time = await concurrent()
    print(f"并发总耗时：{concurrent_time:.1f} 秒")

asyncio.run(main())
```

运行 `python async_demo.py`，你会看到类似：

```
甲 开始
甲 结束
乙 开始
乙 结束
丙 开始
丙 结束
串行总耗时：3.0 秒

甲 开始
乙 开始
丙 开始
甲 结束
乙 结束
丙 结束
并发总耗时：1.0 秒
```

并发那一段，三个“开始”几乎同时出现，三个结束在 1 秒后陆续出现。结束的先后可能不同，但总时间接近 1 秒。

`gather` 把三个协程都排进事件循环。第一个执行到 `await asyncio.sleep(1.0)` 时停住，控制权回到循环；第二个、第三个也依次走到同一个等待点。三个定时器几乎同时开始计时，1 秒后逐个恢复。

串行版每次要等上一个 `await` 完成，才进入下一轮循环，所以 1 + 1 + 1 = 3 秒。

例子用 `asyncio.sleep` 代替网络等待。真实请求要使用支持异步的客户端，但调度方式和这里一样。

`gather` 返回的结果顺序和传入顺序一致，和谁先完成无关。这一点在三个任务耗时不同时很重要：别拿结果列表的顺序当完成顺序。

## async def、await 和事件循环 {#event-loop}

`async def` 只是定义了一个协程函数。调用它，得到的是协程对象，函数体还没有执行：

```python
import asyncio

async def hello():
    print("协程开始")
    await asyncio.sleep(0.1)
    print("协程结束")

coro = hello()
print(type(coro).__name__)
asyncio.run(coro)
```

输出：

```
coroutine
协程开始
协程结束
```

`coro` 是协程对象，不是结果。真正执行它的是 `asyncio.run`。如果创建了协程却不 `await`、不交给事件循环，Python 不会执行函数体，还可能给出 “coroutine was never awaited” 的警告。

事件循环可以想成一个单线程调度器，维护着待运行的任务和定时器。一个任务一直跑到 `await` 一个真正需要等待的操作，才把控制权交回去。循环从就绪队列里拿下一个任务继续跑。

`await` 不是“开一个新线程”。它表示“这里可能要等，先把执行权让出去”。如果被 `await` 的协程一路没有挂起点，它就只是同步地跑完，不会自动变成并发。`await asyncio.sleep(0)` 是一个常用的主动让出点。

`asyncio.run(main())` 负责创建事件循环、运行主协程、收尾并关闭循环。所以在普通脚本里，它通常只在最外层调用一次。

并发在这里指多个任务交替推进，不是多个线程同时执行 Python 字节码。单个事件循环线程一次只跑一个任务。

## 一个 time.sleep 堵死全场 {#blocking-call}

协程里最容易犯的错，是在该让出的时候调用了同步阻塞函数。

```python
import asyncio
import time

async def heartbeat():
    for i in range(1, 5):
        await asyncio.sleep(0.2)
        print(f"心跳 {i}")

async def blocking_work():
    print("开始 time.sleep")
    time.sleep(0.7)
    print("结束 time.sleep")

async def yielding_work():
    print("开始 asyncio.sleep")
    await asyncio.sleep(0.7)
    print("结束 asyncio.sleep")

async def run(work):
    ticker = asyncio.create_task(heartbeat())
    await work()
    await ticker

async def main():
    print("--- 在协程里调用 time.sleep ---")
    await run(blocking_work)

    print("\n--- 换成 await asyncio.sleep ---")
    await run(yielding_work)

asyncio.run(main())
```

输出：

```
--- 在协程里调用 time.sleep ---
开始 time.sleep
结束 time.sleep
心跳 1
心跳 2
心跳 3
心跳 4

--- 换成 await asyncio.sleep ---
开始 asyncio.sleep
心跳 1
心跳 2
心跳 3
结束 asyncio.sleep
心跳 4
```

第一段里，心跳任务已经创建了，但在 `time.sleep(0.7)` 期间一次都没打印。因为 `time.sleep` 占住了事件循环所在的线程，循环没有机会去跑心跳任务。睡眠结束，控制权回到事件循环，四个心跳才补上。

第二段换成 `await asyncio.sleep(0.7)`，心跳在第 0.2、0.4、0.6 秒左右插进来。等待期间循环能继续调度其他任务。

`requests.get`、同步数据库驱动、阻塞式文件读取，都会造成同样的问题。`response = requests.get(url)` 这个调用本身已经堵住了，前面再写 `await` 也来不及。

修法有两种。库有异步版本就用异步版本，比如 HTTP 客户端用 `httpx.AsyncClient` 或 `aiohttp`，数据库用对应的异步驱动。库只有同步版，就把它挪到线程里，写成 `await asyncio.to_thread(requests.get, url, timeout=5)`。

`to_thread` 让阻塞函数在另一个线程执行，事件循环在等待它时还能跑别的任务。它不会让阻塞函数本身变快，也会占用一个线程；如果每个请求都开一个，默认线程池会成为新的上限。

## 计算任务不会因为 async 变快 {#cpu-bound}

异步优化的是“等”，不是“算”。把一段纯 Python 计算放进协程和线程里，总时间不会因为 `async` 缩短：

```python
import asyncio
import time

N = 8_000_000

def burn(n):
    total = 0
    for i in range(n):
        total += i * i
    return total

async def main():
    started = time.perf_counter()
    burn(N)
    burn(N)
    serial = time.perf_counter() - started

    started = time.perf_counter()
    await asyncio.gather(
        asyncio.to_thread(burn, N),
        asyncio.to_thread(burn, N),
    )
    threaded = time.perf_counter() - started

    print(f"顺序计算两遍：{serial:.1f} 秒")
    print(f"两个线程各算一遍：{threaded:.1f} 秒")

asyncio.run(main())
```

你会看到类似：

```
顺序计算两遍：0.9 秒
两个线程各算一遍：0.9 秒
```

两者差不多，甚至线程版会略慢。CPython 有全局解释器锁（GIL），同一时刻只有一个线程在执行 Python 字节码。两个线程只是轮流算，没有真正并行；线程切换和调度还会加一点开销。

这段代码的事件循环没有被完全堵死，因为 `to_thread` 把计算放到了其他线程。但总 CPU 工作量没变，两个循环抢同一个解释器锁，墙钟时间自然下不来。

纯 Python 的 CPU 密集任务要换进程，而不是换 `async`。`ProcessPoolExecutor` 或 `multiprocessing` 能绕开 GIL，代价是进程间传输数据。某些 C 扩展在自己的计算循环里释放 GIL，那种情况下多线程可能有效，但这取决于库，不能默认成立。

所以判断标准很朴素：任务大部分时间在等 I/O，异步有空间；任务大部分时间在算，异步不解决。

## 五个容易混的点 {#pitfalls}

**“`async def` 函数一调用就会执行。”** 不会。调用只得到协程对象，必须 `await` 或交给事件循环。前面 `coro = hello()` 打印出的类型就是 `coroutine`，函数体在 `asyncio.run` 时才跑。

**“`await` 会开一个新线程去执行。”** 不会。`await` 是把当前任务挂起，让同一个事件循环去跑别的任务。异步代码默认还是单线程。

**“协程里写 `requests.get` 也没关系，反正外面有 `await`。”** 有关系。阻塞发生在调用那一行，事件循环当时已经被占住，`await` 还没轮到。上面心跳实验里四个心跳全部迟到，就是这个结果。

**“`create_task` 创建完就不用管了。”** 任务需要有人保存引用、等待结果或处理异常。循环关闭时仍未完成的任务会被取消；未取回的异常也可能被忽略。简单场景用 `asyncio.gather`，需要取消和清理时用 `asyncio.TaskGroup` 或显式 `await`。

**“用了 async，CPU 任务就能并行。”** 不能。`asyncio.to_thread` 也跑不赢 GIL，纯 Python 计算换进程更实际。异步让等待重叠，不让计算并行。

## 什么时候别用 async {#tradeoffs}

| 场景 | 更直接的做法 |
|---|---|
| 一次性脚本、少量请求 | 同步代码 |
| 大量网络或流式等待，依赖库支持异步 | `asyncio` |
| 只有同步库，且无法替换 | 线程或 `asyncio.to_thread` |
| 纯 Python CPU 密集计算 | 进程池或原生扩展 |

先看依赖链。只要有一个关键步骤是同步阻塞的，整条异步链就会在那一行卡住。要么换异步库，要么在那个边界用 `to_thread`，别在协程中间随手调用阻塞函数。

并发数要有上限。`gather` 一次排一万个请求，会同时占掉 socket、内存和下游连接。用 `asyncio.Semaphore` 限制同时进行的数量，或者利用连接池和限流器，让排队发生在你能看见的地方。

超时和取消要写进流程。`asyncio.timeout` 可以给一段等待设上限；任务取消后，清理代码要放在 `finally` 或上下文管理器中。取消等待者不等于撤销外部系统已经执行的动作，比如已经发出的写请求。

协程之间仍然会共享状态。一个任务在 `await` 处让出后，另一个任务可能修改同一个字典或列表。不要在 `await` 前后假设变量没变；需要共享可变状态时，用锁或把状态限制在单个任务里。

看指标比看关键字有用。异步有没有收益，取决于等待占比、并发上限和下游能力，不取决于代码里出现了多少 `async`。记录事件循环延迟、请求排队时间和吞吐，比背“异步更快”有用。

## 判断谁会堵住循环 {#self-check}

**第 1 题**：三个各等 2 秒的 `await asyncio.sleep(2)`，串行等待和用 `gather` 并发等待，总时间分别大约多少？

> **答案**
>
> 串行约 6 秒，并发约 2 秒。并发不是把每个 2 秒缩短，而是让三段等待重叠。总时间由最长的那次等待决定，不是三次之和。

**第 2 题**：在一个 `async def` 函数里直接写 `response = requests.get(url)`，会有什么问题？

> **答案**
>
> `requests.get` 是同步阻塞调用，会占住事件循环线程；等待网络时，其他协程都跑不了。
>
> 它返回的 `Response` 本身也不能被 `await`。想保留 `requests`，应当用 `await asyncio.to_thread(requests.get, url, timeout=5)`；更彻底的做法是换成异步 HTTP 客户端。

**第 3 题**：调用一个 `async def` 函数但忘记 `await`，函数体会执行吗？

> **答案**
>
> 不会。调用只创建协程对象，函数体要等它被 `await` 或交给事件循环后才开始执行。
>
> 如果一直不处理这个协程对象，通常还会看到 “coroutine was never awaited” 的警告。

## 从协程走向线程 {#related}

- [Promise 与 async/await](/learn/js-async)
- [线程池：受控执行阻塞工作](/learn/thread-pool)
- [HTTP 请求与响应](/learn/web-http)
- [URL、JSON 与 API 契约](/learn/web-api)

## 异步编程的参考文档 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
