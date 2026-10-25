# 重试与幂等：失败后怎样安全再来一次

## 一次超时，两条订单 {#overview}

学完这一篇，你能分清哪些失败值得重试，并用幂等键让重试不会多写一条订单。

你在做一个下单接口。用户点了"支付"，客户端发出请求，等了三秒没收到响应，界面上跳出"网络超时，请重试"。用户又点了一次。

结果是：服务器其实在第一次就写成功了，只是响应在回来的路上丢了。第二次请求又写了一条。

**超时只说明你没等到响应，不说明服务器没执行。** 把"没收到"当成"没发生"，是重试最常踩的坑。

## 复现多出来的那条 {#example}

新建 `retry_demo.py`：

```python
class Server:
    def __init__(self):
        self.orders = []
        self.calls = 0

    def create_order(self, amount):
        self.calls += 1
        self.orders.append(amount)
        return {"ok": True}


class FlakyClient:
    """服务器写成功了，但第一次的响应在返回路上丢了。"""

    def __init__(self, server):
        self.server = server

    def create(self, amount):
        result = self.server.create_order(amount)
        if self.server.calls == 1:
            raise TimeoutError("等响应超时")
        return result


server = Server()
client = FlakyClient(server)

try:
    client.create(99)
except TimeoutError as exc:
    print("第一次失败：", exc)

client.create(99)  # 直接重试
print("订单条数：", len(server.orders))
print("订单内容：", server.orders)
```

运行：

```bash
python retry_demo.py
```

你应该看到：

```
第一次失败： 等响应超时
订单条数： 2
订单内容： [99, 99]
```

`FlakyClient.create` 先调用 `server.create_order`，订单已经写进去了，然后才抛超时。这一行代码模拟的是网络边界：**服务器做完事，客户端没收到回执。** 客户端看到异常就重试，服务端并不知道这两次是不是同一笔业务，于是照写不误。

超时可能发生在三个位置，后果完全不同：

| 超时发生在 | 服务器状态 | 盲目重试的后果 |
|---|---|---|
| 请求还没到服务器 | 什么都没做 | 安全，补一次就行 |
| 请求到了，处理到一半失败 | 可能写了一半 | 取决于有没有事务 |
| 处理完了，响应丢了 | 已经写成功 | 重复写入 |

客户端从异常里分不出是哪一种。所以写操作的重试，不能靠"应该没事"。

## 哪些错误值得再试 {#retryable}

不是所有失败都该重试。重试一个注定失败的请求，只是把同样的错误再犯几次，还多占一份资源。

| 情况 | 能重试吗 | 原因 |
|---|---|---|
| 等待响应超时 | 能，但写操作要带幂等键 | 服务端可能已执行 |
| 连接被拒绝、连接重置 | 能 | 通常是瞬时网络问题 |
| HTTP 429 | 能，按 `Retry-After` 等 | 被限流，等一会儿有配额 |
| HTTP 502 / 503 / 504 | 能 | 网关或上游临时不可用 |
| HTTP 500 | 谨慎，最多一两次 | 可能是瞬时故障，也可能是每次必现的 bug |
| HTTP 400 / 401 / 403 / 404 / 422 | 不能 | 请求、身份或资源本身不对 |
| HTTP 409 | 不能盲目重试 | 状态冲突，得先弄清现状 |
| 自己代码里的 `ValueError` | 不能 | 参数错了，重试还是错 |

判断可以压成一句话：**失败可能是暂时的，并且这次操作重复执行不会造成额外后果，才重试。**

第二个条件对读操作很宽松。查询没有副作用，重试几次通常没问题。写操作不一样：创建订单、发消息、扣款，每一次都可能留下痕迹。要么给它加幂等键，要么别自动重试。

还要看调用方等不等得起。用户点支付，你的接口总共只有五秒预算，重试三次每次等两秒，第四次还没发出去用户已经关页面了。**重试的时间不能超过整个请求的截止时间。**

## 等待时间要越拉越长 {#backoff}

失败后立刻重试，通常没意义：对方刚拒绝你，下一秒大概率还是拒绝。固定间隔也不行：一百个客户端同时失败，一秒钟后同时回来，把刚恢复的服务再打垮一次。

做法是**指数退避加随机抖动**。新建 `retry_delay.py`：

```python
import random
import time

rng = random.Random(7)  # 固定种子方便对照；线上别固定


class TransientError(Exception):
    pass


def flaky():
    if not hasattr(flaky, "n"):
        flaky.n = 0
    flaky.n += 1
    if flaky.n < 4:
        raise TransientError(f"第 {flaky.n} 次尝试失败")
    return "成功"


def call_with_retry(fn, attempts=5, base=0.1, max_delay=10):
    for i in range(attempts):
        try:
            return fn()
        except TransientError as exc:
            if i == attempts - 1:
                raise
            delay = min(base * (2 ** i), max_delay)
            delay += rng.uniform(0, delay / 2)  # 抖动，避免客户端同时回来
            print(f"{exc}，{delay:.2f}s 后再试")
            time.sleep(delay)


print(call_with_retry(flaky))
```

运行：

```bash
python retry_delay.py
```

你会看到类似：

```
第 1 次尝试失败，0.12s 后再试
第 2 次尝试失败，0.22s 后再试
第 3 次尝试失败，0.53s 后再试
成功
```

前三次失败，第四次成功。等待时间按 `base * 2 ** i` 增长：0.1 秒、0.2 秒、0.4 秒，再各自加一段随机量。这里的随机数被固定了种子，所以你能看到上面这三个值；换掉种子或让它真随机，数字会变。

三个参数各有作用：

- `attempts` 限制次数，防止死循环。
- `max_delay` 封顶。没有封顶的话，连错十次，单次等待会到几十秒，调用方早就超时了。
- 抖动那半段随机量把同时失败的客户端打散。没有它，客户端会踩着同一个节奏回来，形成新的尖峰。

真实客户端还要加一个**总截止时间**：从第一次尝试开始计时，超过就停，不管还剩几次。收到 `Retry-After` 响应头时，按它给的时间等，通常比你自己算的更准。

重试只在一层做。网关重试、服务重试、客户端也重试，一次失败会变成九次请求。选一层负责，其他层把错误原样往上报。

## 幂等键把重试变安全 {#idempotency-key}

回到那两条订单。要安全重试，客户端得告诉服务端："这两次是同一笔业务，别再写一条。"

这个标识叫**幂等键**。客户端在发起操作时生成一次，重试时原样带上。新建 `retry_idempotent.py`：

```python
class IdempotentServer:
    def __init__(self):
        self.orders = []
        self.seen = {}

    def create_order(self, request_id, amount):
        if request_id in self.seen:
            if self.seen[request_id]["amount"] != amount:
                raise ValueError("同一个幂等键，金额不同")
            return {"duplicate": True, "order": self.seen[request_id]}
        order = {"request_id": request_id, "amount": amount}
        self.orders.append(order)
        self.seen[request_id] = order
        return {"duplicate": False, "order": order}


class FlakyClient:
    def __init__(self, server):
        self.server = server
        self.calls = 0

    def create(self, request_id, amount):
        self.calls += 1
        result = self.server.create_order(request_id, amount)
        if self.calls == 1:
            raise TimeoutError("等响应超时")
        return result


server = IdempotentServer()
client = FlakyClient(server)
try:
    client.create("order-7f3a2c", 99)
except TimeoutError as exc:
    print("第一次失败：", exc)

second = client.create("order-7f3a2c", 99)
print("第二次：", second)
print("订单条数：", len(server.orders))

try:
    server.create_order("order-7f3a2c", 100)
except ValueError as exc:
    print("拒绝：", exc)
```

运行：

```bash
python retry_idempotent.py
```

你应该看到：

```
第一次失败： 等响应超时
第二次： {'duplicate': True, 'order': {'request_id': 'order-7f3a2c', 'amount': 99}}
订单条数： 1
拒绝： 同一个幂等键，金额不同
```

第一条订单第一次就写进去了。第二次带着同一个键来，服务端查到已有记录，直接把上次的结果还回去，`orders` 仍然只有一条。第三次故意用同一个键、不同的金额，服务端明确拒绝。

三个细节决定这个机制靠不靠谱。

**键由客户端生成，而且每次业务操作只生成一次。** 不能在每次重试时重新生成，否则服务端每次看到的都是新请求。可以用 UUID，也可以用业务上天然唯一的编号（订单号），但要保证同一笔业务在多次尝试中稳定。

**同一个键、不同内容必须报错。** 直接返回旧结果会把"客户端写错了金额"悄悄吞掉。幂等是"重复的同一件事只做一次"，不是"同一个键随便传什么都行"。

**去重记录要放在能跨进程的地方。** 上面的字典只在单进程内存里有效。两个 worker、一次重启，记录就没了。生产里用数据库的唯一约束：

```sql
CREATE TABLE idempotency_keys (
    key        TEXT PRIMARY KEY,
    response   TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

先尝试插入这个键，插入成功的那一方执行业务写入，两个动作放在同一个事务里；插入冲突的那一方读出已存的响应返回。唯一索引负责挡住并发下的两个同时插入，不用自己写"先查再插"——那个检查在并发时不可靠。

记录要保留多久？至少覆盖客户端可能重试的整个窗口，通常几小时到几天。过期清理要有，否则表会一直长。

这组机制和消息队列的投递语义是同一件事。队列通常保证**至少一次**：消息处理完、还没确认，消费者挂了，消息会被再投一次。想做到业务上的**恰好一次**，靠的不是队列本身，而是"至少一次投递 + 消费者幂等"：重复的消息进来，去重后只有一次副作用。broker 说自己支持 exactly-once，也只覆盖它自己的收发范围；你的数据库写入、你调的外部接口，仍然要自己去重。

## 四个把重试写坏的方式 {#pitfalls}

**"所有异常都重试。"** `ValueError`、401、404 重试一百次还是同样的结果。更糟的是，重试放大了错误：本来每秒一个坏请求，变成每秒五个。只捕获你确认可恢复的异常类型，其他原样抛出去。

**"超时就是没执行。"** 这一篇开头已经演过：服务器写完了，响应丢了。写操作超时后，状态是"未知"，不是"失败"。带幂等键重试，或者去查一次实际状态，别直接当失败处理。

**"POST 重试一下没事。"** POST 在 HTTP 语义里不保证幂等。创建订单、发消息、启动任务，重试一次就多一条。要么加幂等键，要么把这类操作改成可安全重复的形式（比如先 PUT 一个客户端生成的 ID）。GET 通常安全，PUT 和 DELETE 按语义重复执行结果一致，但也要看你的实现有没有额外副作用。

**"每次等一秒，重试五次。"** 固定间隔会让同时失败的客户端同时回来，而且总等待只有五秒，可能全撞在故障窗口里。用指数退避、抖动、封顶，再加总截止时间。次数相同不代表总时长相同，`base` 和退避策略不同，最坏延迟差很多。

## 重试的延迟账单 {#tradeoffs}

重试不是免费的。最坏情况下，一次用户请求要等完所有尝试才返回；如果每层都重试，延迟和请求量会成倍放大。

同步接口的重试要克制：预算小、用户能感知、失败时还能让用户自己再点。后台任务可以从容一些：慢慢退避，失败后进重试队列，几小时后再来。

重试还会消耗对方的配额。服务已经过载时，大量客户端一起重试会让它更慢。这时候服务端应该返回 503 和 `Retry-After`，客户端照着等；没有这个头，就自己退避，别硬冲。

幂等键带来存储成本：每条记录都要占空间，还要定过期策略。换来的是失败恢复可控——超时后敢重试，重复投递不会多扣一次钱。

还有一件事必须诚实：**结果未知就记成未知。** 超时后既不能写"成功"，也不能写"失败"，日志里应该是"已发出，未收到响应，等待对账"。靠对账或补偿把状态收敛，比在日志里编一个结论可靠。

## 练习 {#self-check}

**第 1 题**：客户端收到 401、503、400，哪些值得重试？

> **答案**
>
> 只有 503。它是"服务暂时不可用"，退避后可能恢复，注意看 `Retry-After`。
>
> 401 是身份不对，得换令牌或修认证逻辑；400 是请求格式或参数错了，重试还是同样的错。这两种重试只会浪费配额，还会把真正的错误藏在一堆重试日志里。

**第 2 题**：同一个幂等键，第二次请求的金额从 99 变成 100，服务端应该返回旧结果还是报错？

> **答案**
>
> 报错。同一个键代表同一笔业务，金额变了说明客户端复用错了键，或者请求构造有问题。
>
> 返回旧结果会让客户端以为 100 元的下单成功了，实际只有 99 元那条记录。幂等保护的是"重复的同一件事"，不是"同一个键的任何内容"。

**第 3 题**：为什么上面用字典做去重，在生产里不够？

> **答案**
>
> 字典只在当前进程的内存里。服务起多个 worker 时，请求可能落到不同进程，各自都看不到对方的记录；进程重启，记录全丢。
>
> 更隐蔽的是并发：两个请求同时查字典都发现"没记录"，然后各自写入。要用数据库的唯一约束加事务，让"检查并写入"成为一个原子操作。

## 继续阅读 {#related}

- [数据库事务：一致完成状态转换](/learn/db-transaction)
- [HTTP 请求与响应](/learn/web-http)
- [结构化日志：记录可以关联的事件](/learn/structured-logging)
- [限流：保护服务不被自己人打垮](/learn/rate-limit)

## 参考资料 {#sources}

- [Tenacity documentation](https://tenacity.readthedocs.io/en/latest/)；作者：Julien Danjou and contributors；Apache-2.0。版本：导入日网页快照; sha256:5686185039f9fdbabb83fd9264fed03f18fb5c3ebfb43d99cc25a9df315dacff。
- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
