# 事件总线：发布事件与订阅处理

## 保存留言之后要做的三件事 {#overview}

读完这一篇，你能把保存留言后的一串直接调用改成订阅，并知道同步发布在顺序、异常和送达上给出的保证。

小林的留言板加了保存功能。一条留言写进数据库以后，界面要更新未读数，日志要记一笔，关注者要收到通知。三件事都不复杂，直接写在保存函数里就行。

加到第四件事——记一条发送指标——他得回头改保存函数。日志服务偶尔超时，通知就跟着发不出去。测试保存逻辑时，日志和通知也被一起触发。

这些副作用和“保存留言”本身并不强绑定。保存成功是事件，更新未读数、写日志、发通知是对事件的反应。把反应从保存函数里拿出去，就是事件总线在做的事。

## 三段写死在一起的保存流程 {#direct-calls}

新建 `direct.py`，先看没有事件总线时的版本：

```python
def update_badge():
    print("未读数：1")


def write_log(text):
    print(f"日志：保存了 {text}")


def send_notification(text):
    print(f"通知：收到新留言「{text}」")


def save_message(text):
    print(f"保存：{text}")
    update_badge()
    write_log(text)
    send_notification(text)


save_message("你好")
```

运行 `python direct.py`：

```
保存：你好
未读数：1
日志：保存了 你好
通知：收到新留言「你好」
```

`save_message` 知道三件事的全部细节：谁被调用、按什么顺序、传什么参数。加第四件事，就改它；删通知，也改它。

调用顺序被写死在函数体里。测试 `save_message` 时，三个副作用都会执行，你没法只验证“保存”这一步。

异常的影响也写死了。如果 `write_log` 抛异常，后面的 `send_notification` 不会执行，异常继续往上抛给调用方。留言已经保存了，通知却没发，系统处在半完成状态。

## 用二十行写一个事件总线 {#minimal-bus}

事件总线把“谁关心”与“发生了”分开。新建 `bus.py`：

```python
class EventBus:
    def __init__(self):
        self._handlers = {}

    def subscribe(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def unsubscribe(self, event, handler):
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event, **payload):
        for handler in list(self._handlers.get(event, [])):
            handler(**payload)


bus = EventBus()


def update_badge(**payload):
    print("未读数 +1")


def write_log(**payload):
    print(f"日志：保存了 {payload['text']}")


def send_notification(**payload):
    print(f"通知：收到新留言「{payload['text']}」")


bus.subscribe("message.saved", update_badge)
bus.subscribe("message.saved", write_log)
bus.subscribe("message.saved", send_notification)


def save_message(text):
    print(f"保存：{text}")
    bus.publish("message.saved", text=text)


save_message("你好")
```

运行 `python bus.py`：

```
保存：你好
未读数 +1
日志：保存了 你好
通知：收到新留言「你好」
```

`_handlers` 是一个字典：事件名映射到处理函数列表。`subscribe` 把函数追加进去；同一个事件可以挂很多个。

`publish` 查出这个事件的处理函数，逐个调用，并把 `text` 作为关键字参数传进去。`handler(**payload)` 的意思是“把字典拆成关键字参数”，所以每个处理函数都写 `def xxx(**payload)`，从里面取自己关心的字段。

`save_message` 现在只做两件事：保存，发布。它不知道未读数怎么更新，也不知道通知怎么发，甚至不知道有几个订阅者。

`list(...)` 那层复制值得保留。如果某个处理函数在运行中调用 `unsubscribe` 移除自己或别人，直接遍历原列表会跳过元素；遍历副本，当前这次发布仍按开始时的名单走。

## 发布者不再知道谁在听 {#decoupling}

加一个指标订阅者，不用碰 `save_message`。把下面几行加到 `bus.py` 末尾再跑：

```python
def record_metric(**payload):
    print("指标：message_saved +1")


bus.subscribe("message.saved", record_metric)
save_message("第二条")

bus.unsubscribe("message.saved", write_log)
save_message("第三条")
```

新增的输出是：

```
保存：第二条
未读数 +1
日志：保存了 第二条
通知：收到新留言「第二条」
指标：message_saved +1
保存：第三条
未读数 +1
通知：收到新留言「第三条」
指标：message_saved +1
```

第二次发布时，四个订阅者按注册顺序执行。第三次发布前，`write_log` 被取消订阅，所以“日志”那一行消失了，其他处理不受影响。

订阅顺序就是列表顺序，也就是 `subscribe` 的调用顺序。这个保证来自当前实现，不是事件总线这个概念本身。换一个库、换异步投递，顺序可能变。

发布者与订阅者之间只剩一份载荷约定：事件名 `message.saved`，字段 `text`。发布者不导入订阅者的模块，订阅者也不导入发布者。加功能时改的是订阅端，保存流程不动。

这份约定需要写清楚。字段名改了、类型变了、允许缺失还是必填，都是接口变更。处理函数从 `payload["text"]` 取值，键不存在就会 `KeyError`，而发布者可能根本不知道有人依赖它。

## 一个处理函数抛异常会怎样 {#errors}

上面的 `publish` 没有异常隔离。一个处理函数失败，后面的处理函数直接不执行。新建 `errors.py`：

```python
class EventBus:
    def __init__(self):
        self._handlers = {}

    def subscribe(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def publish(self, event, **payload):
        for handler in self._handlers.get(event, []):
            handler(**payload)


def update_badge(**payload):
    print("未读数 +1")


def write_log(**payload):
    raise RuntimeError("日志库连不上")


def send_notification(**payload):
    print(f"通知：{payload['text']}")


bus = EventBus()
bus.subscribe("message.saved", update_badge)
bus.subscribe("message.saved", write_log)
bus.subscribe("message.saved", send_notification)

try:
    bus.publish("message.saved", text="你好")
except RuntimeError as exc:
    print("publish 中断：", exc)


class SafeBus(EventBus):
    def publish(self, event, **payload):
        for handler in list(self._handlers.get(event, [])):
            try:
                handler(**payload)
            except Exception as exc:
                print(f"{handler.__name__} 出错：{exc}")


safe = SafeBus()
safe.subscribe("message.saved", update_badge)
safe.subscribe("message.saved", write_log)
safe.subscribe("message.saved", send_notification)
safe.publish("message.saved", text="你好")
```

运行 `python errors.py`：

```
未读数 +1
publish 中断： 日志库连不上
未读数 +1
write_log 出错： 日志库连不上
通知：你好
```

普通 `EventBus` 里，`update_badge` 执行完，`write_log` 抛错，循环中断，`send_notification` 没跑。异常从 `publish` 冒到 `save_message`，再冒到调用方。留言已经保存，副作用只完成了一部分。

`SafeBus` 给每个处理函数单独包 `try/except`。`write_log` 失败只打印一行，后面的通知照常执行，`publish` 正常返回。

两种行为对应两种需求：

- 副作用必须一起成功或一起失败，就让异常向上冒，由调用方决定回滚或重试。比如扣库存和生成订单。
- 每个副作用互相独立，失败一个不影响其他，就隔离异常，但要把错误记进日志或监控。比如通知、指标、缓存失效。

`SafeBus` 的写法也有代价：`publish` 返回了，但某个处理其实失败了。调用方如果只看“没抛异常”，会以为都成功了。至少要把失败次数记下来，别让错误只停留在控制台。

## 同步投递与异步投递不是一回事 {#async-delivery}

同步发布是 `publish` 直接调用处理函数：调用返回时，处理函数已经跑过（或者抛了异常）。它简单，顺序确定，但慢处理会卡住发布者。

异步发布把处理丢进队列或线程池，`publish` 先返回。新建 `async_send.py`：

```python
from concurrent.futures import ThreadPoolExecutor
import time


def notify(text):
    time.sleep(0.05)
    return "通知已发送"


def write_log(text):
    raise RuntimeError("磁盘满")


with ThreadPoolExecutor(max_workers=2) as pool:
    f1 = pool.submit(notify, "你好")
    f2 = pool.submit(write_log, "你好")
    print("publish 已返回")
    print("通知结果：", f1.result())
    try:
        f2.result()
    except RuntimeError as exc:
        print("日志处理失败：", exc)
```

运行 `python async_send.py`：

```
publish 已返回
通知结果： 通知已发送
日志处理失败： 磁盘满
```

`pool.submit` 只是把任务排进去，`publish 已返回` 先打印。通知 50 毫秒后才完成，日志的失败要等 `f2.result()` 才浮出来。换成真正的队列，`publish` 返回时，可能连队列都还没消费。

这里要把三件事分开：

| 阶段 | 含义 | 能确认什么 |
|---|---|---|
| 事件发生 | 保存已经完成，`publish` 被调用 | 业务动作发生了 |
| 事件送达 | 处理函数被调用，或消息进入队列 | 有人会处理 |
| 处理成功 | 处理函数正常返回，副作用已提交 | 结果真的生效 |

同步总线把后两个阶段压缩在 `publish` 里，但也不等于“处理成功”：发邮件的函数返回了，邮件仍可能被退信。异步总线把三个阶段拆得更开，`publish` 返回只说明事件发生了。

持久消息队列还会引入重投、去重、消费确认。进程崩溃后消息能不能重放，重复投递时处理函数是否幂等，这些都不是一个字典加几个函数能解决的。事件总线解决的是进程内解耦，不是可靠投递。

## 用 blinker 换掉自己写的事件表 {#blinker}

Python 生态里有一个常用的进程内信号库 `blinker`。先装：

```bash
pip install blinker
```

它用命名信号和 `connect`/`send`，写法与手写总线类似。新建 `with_blinker.py`：

```python
from blinker import signal

message_saved = signal("message.saved")


def update_badge(sender, **payload):
    print(f"未读数 +1（sender={sender}）")


def write_log(sender, **payload):
    print(f"日志：保存了 {payload['text']}")


message_saved.connect(update_badge)
message_saved.connect(write_log)

message_saved.send("save_message", text="你好")
message_saved.disconnect(write_log)
message_saved.send("save_message", text="第二条")
```

在 blinker 1.9.0 上运行 `python with_blinker.py`：

```
未读数 +1（sender=save_message）
日志：保存了 你好
未读数 +1（sender=save_message）
```

`signal("message.saved")` 按名字取一个全局信号；`connect` 注册处理函数；`send` 的第一个参数是发送者，后面的关键字参数就是载荷。处理函数的第一个位置参数必须能接住 `sender`，否则会报参数错误。

`disconnect` 取消订阅后，第二条只触发了 `update_badge`。

blinker 默认用弱引用保存处理函数。模块级的普通函数一直有引用，不会消失；临时的 `lambda`、局部函数可能在发送前就被回收，于是“注册了却收不到”。需要长期保留时，用 `weak=False`：

```python
message_saved.connect(handler, weak=False)
```

异常处理和投递方式仍然由你决定。blinker 的 `send` 同步调用处理函数，默认不会替你把异常吞掉；一个处理函数抛错，后面的处理函数不会执行。它解决的是注册与分发，不解决可靠性。

## 事件总线最容易想错的地方 {#pitfalls}

**“订阅了就会收到。”** 事件名必须一致，载荷必须包含处理函数读取的字段，处理函数签名必须接得住参数。事件名拼错、`text` 键缺失、函数只接受位置参数，都会让处理落空或报错。blinker 还多一层弱引用问题。

**“`publish` 正常返回，所有处理都成功了。”** 同步版本可能中途抛异常；异步版本可能只是排了队；处理函数内部的网络请求、邮件投递失败，更不会自动变成 `publish` 的异常。要区分事件发生、送达、处理成功。

**“事件会按发生顺序到达。”** 当前同步实现按订阅顺序调用，这一点可以依赖；异步队列、多线程、多消费者都不保证完成顺序。两个事件几乎同时发布时，后发的可能先处理完。

**“事件总线是跨进程的。”** 手写字典和 blinker 信号都活在当前解释器里。多进程部署时，每个进程各有一份订阅表；A 进程发布，B 进程收不到。跨进程要上消息队列或事件流平台。

**“所有调用都改成事件就解耦了。”** 直接调用至少能顺着函数名找到下一步。改成事件后，发布点看不出谁在听，处理链藏在订阅表里，排错和追踪都更难。需要返回值的请求—响应，直接调用通常更清楚。

## 什么时候别把所有调用都改成事件 {#tradeoffs}

事件适合一对多通知、可选的附加动作、跨切面逻辑：保存后更新界面、记日志、打指标、失效缓存、给插件扩展点。发布者不需要知道订阅者的存在，加功能时不用改核心流程。

不适合的场景也很明确：调用方需要返回值；几个步骤必须一起成功或一起失败；顺序和“只处理一次”是硬要求；调用链需要一眼看懂。这些时候，直接函数调用、事务、明确的编排函数更可靠。

判断可以先问四句话：

- 发布者需要知道处理结果吗？需要，就别用单向事件。
- 处理失败能接受吗？不能，就要事务、重试或持久化，不能只靠内存里的回调列表。
- 同一个事件能重复处理吗？不能，处理函数得做幂等，或者队列去重。
- 进程崩溃后事件要还在吗？要，就用持久队列或事务性发件箱，别用进程内总线。

同步总线阻塞、顺序确定、异常会传回发布者；异步总线响应快，但把失败和顺序问题推到了后面。两者都没有“送达保证”这回事，除非底层队列明确提供确认、重投和持久化。

事件名和载荷是接口。字段增删、语义变化要有版本和文档；订阅者也要能取消订阅，否则对象提前销毁、处理函数还在表里，会收到自己不该处理的事件。

## 练习 {#self-check}

**第 1 题**：事件 `saved` 依次订阅了 `a`、`b`、`c`。`b` 抛异常，`a` 和 `c` 会执行吗？`publish` 会怎样？

> **答案**
>
> 用上面的同步实现，`a` 会执行，`b` 抛异常后循环中断，`c` 不执行，异常从 `publish` 继续向上抛。想让 `a`、`c` 都执行，可以给每个处理函数包 `try/except`，像 `SafeBus` 那样；代价是发布者不再知道有处理失败了。

**第 2 题**：`publish` 返回了，能不能说明关注者已经收到通知？

> **答案**
>
> 不能。同步实现里只能说明处理函数被调用过，不能说明邮件没退信、数据库没回滚；异步实现里 `publish` 可能只把任务放进队列，处理还没开始。事件发生、送达、处理成功是三件事，可靠投递需要队列确认、重试和幂等。

**第 3 题**：不加事件总线，怎么让“保存留言”和“记指标”解耦？加事件总线后又怎么加第四个订阅者？

> **答案**
>
> 直接调用时，可以把指标函数作为参数传进 `save_message`，或者让保存函数返回结果，由外层依次调用保存和指标——但这样编排逻辑仍在调用方。
>
> 用事件总线时，写一个新的处理函数并注册即可，保存函数不用改：
>
> ```python
> def record_metric(**payload):
>     print("指标：message_saved +1")
>
> bus.subscribe("message.saved", record_metric)
> ```
>
> 保存函数仍然只调用 `bus.publish("message.saved", text=text)`。

## 继续阅读 {#related}

- [结构化日志：记录可以关联的事件](/learn/structured-logging)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)
- [异步编程：等待期间让出执行机会](/learn/async)
- [依赖注入：把需要的能力交进来](/learn/dependency-injection)

## 参考资料 {#sources}

- [Blinker documentation](https://blinker.readthedocs.io/en/stable/)；作者：Jason Kirtland and contributors；MIT。版本：导入日网页快照; sha256:81d9be85b56afe212e24ad798f084e9a3ff6192a44aeecc95a2dce1be32fafa5。
