# 重试与幂等：失败后怎样安全再来一次

## 先建立直觉 {#overview}

重试是在可能暂时失败时重新尝试，幂等是相同操作重复执行仍保持约定结果。两者经常一起设计：没有收到响应时，服务器可能已经完成写入，盲目再做一次可能产生重复副作用。检测到重试代码，不等于已经证明业务幂等。

## 原理与执行过程 {#mechanism}

重试需要限定可恢复错误、次数或总时间，并设置退避与抖动。幂等通常使用稳定业务键、唯一约束或执行记录识别重复请求；同键不同内容还应检查冲突。查询通常较容易安全重试，支付、发送消息和启动任务则需要明确去重机制。

## 跟着例子理解 {#example}

```python
def save_once(store, request_id, text):
    previous = store.get(request_id)
    if previous is not None:
        if previous != text:
            raise ValueError("同一请求 ID 的内容冲突")
        return previous
    store[request_id] = text
    return text
```

## 一步一步读懂 {#walkthrough}

request_id 表达同一次业务请求。重复且内容相同时返回既有结果，不再创建新记录。相同 ID 却不同正文时明确拒绝。本例使用内存字典，只讲去重语义，没有解决多线程、多进程或重启；真实数据库还需要把检查与写入放进可靠的约束和事务。

## 常见误解 {#pitfalls}

超时不是未执行的证明。重试全部异常可能放大永久错误或引起请求风暴。只检查去重键不检查输入内容，可能把新请求误当旧请求。重试次数相同也不代表总等待时间相同。

## 工程中的取舍 {#tradeoffs}

幂等记录增加存储与过期管理，却让失败恢复更可控。退避降低冲突但增加最坏延迟。对外部工具，应记录请求、领取与结果边界，并保留未知状态，不应在没有结果时声称执行成功。

## 接着探索 {#related}

- [数据库事务：一致完成状态转换](/learn/db-transaction)
- [HTTP 请求与响应](/learn/web-http)

## 来源与版本 {#sources}

- [Tenacity documentation](https://tenacity.readthedocs.io/en/latest/)；作者：Julien Danjou and contributors；Apache-2.0。版本：导入日网页快照; sha256:5686185039f9fdbabb83fd9264fed03f18fb5c3ebfb43d99cc25a9df315dacff。
- [PostgreSQL Tutorial](https://www.postgresql.org/docs/18/tutorial.html)；作者：PostgreSQL Global Development Group；PostgreSQL。版本：PostgreSQL 18; sha256:692fb5b8190798f89f9537a7aae3265c27b3a32dd5b9b63d4a665f009928bb3c。
