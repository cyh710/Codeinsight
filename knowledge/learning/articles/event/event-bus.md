# 事件总线：发布事件与订阅处理

## 先建立直觉 {#overview}

事件总线让产生事件的一方发布消息，由订阅者决定怎样响应，减少双方直接调用的耦合。例如，索引完成后可以通知界面更新或记录统计。事件发生、事件送达和处理成功是不同阶段，不能只看发布动作就认定所有响应已经完成。

## 原理与执行过程 {#mechanism}

发布者约定事件名称与载荷，订阅者注册处理函数。进程内信号系统可能同步调用订阅者，也可能由应用封装为异步队列；具体实现决定顺序、异常和交付保证。持久消息队列进一步涉及重投、去重和消费确认，不应与简单回调列表混为一谈。

## 跟着例子理解 {#example}

```python
from blinker import signal
finished = signal("index-finished")
def report(sender, **payload):
    print(payload["files"])
finished.connect(report)
finished.send("indexer", files=12)
```

## 一步一步读懂 {#walkthrough}

订阅者 report 注册到命名信号，发布者传入发送者与字段。这里的信号在进程内使用，不构成跨进程持久投递。真实应用还应约定载荷版本、订阅者异常如何影响发布者以及对象销毁时怎样解除订阅。

## 常见误解 {#pitfalls}

事件名字相同不代表跨进程共享。弱引用、订阅生命周期和重复注册会影响是否收到事件。异步处理的完成顺序可能不同于发布顺序。把所有依赖都改成事件可能让调用链更难追踪。

## 工程中的取舍 {#tradeoffs}

事件适合一对多通知与松耦合扩展；必须立即得到返回值的业务调用，直接函数接口往往更清楚。涉及关键状态时，应明确是否需要持久化、重放和幂等。知识解释应依据实际总线实现描述保证。

## 接着探索 {#related}

- [结构化日志：记录可以关联的事件](/learn/structured-logging)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 来源与版本 {#sources}

- [Blinker documentation](https://blinker.readthedocs.io/en/stable/)；作者：Jason Kirtland and contributors；MIT。版本：导入日网页快照; sha256:81d9be85b56afe212e24ad798f084e9a3ff6192a44aeecc95a2dce1be32fafa5。
