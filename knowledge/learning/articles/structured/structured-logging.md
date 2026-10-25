# 结构化日志：记录可以关联的事件

## 两个请求混在一起的日志 {#overview}

学完这一篇，你能让每条日志都带上请求 ID 和耗时，并把一次请求的多行记录串起来查。

线上服务同时处理两个索引任务。你在代码里插了几行 `print`，跑完一看终端，六行字混在一起：两条"开始索引"、两条"读取文件"、两条"索引完成"。哪条完成属于哪个请求？不看代码顺序根本分不出来。

再加到二十个并发请求，日志会变成一锅粥。要查"7 号项目的任务为什么慢"，你得按时间猜哪几行是它的。加上用户报障只给了个大致时间，猜都没法猜。

日志的问题不是"写得不够多"，是**每行都没有身份**。

## 先用 print 跑一次 {#print-problem}

新建 `log_print.py`：

```python
import threading
import time


def index(project_id):
    print(f"开始索引项目 {project_id}")
    time.sleep(0.02)
    print(f"读取项目 {project_id} 的文件")
    time.sleep(0.02)
    print(f"项目 {project_id} 索引完成")


threads = [threading.Thread(target=index, args=(pid,)) for pid in (7, 8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

运行：

```bash
python log_print.py
```

你会看到类似：

```
开始索引项目 8
开始索引项目 7
读取项目 7 的文件
读取项目 8 的文件
项目 8 索引完成
项目 7 索引完成
```

顺序每次可能不同，但问题是一样的：六行文本，没有时间、没有级别、没有请求标识、没有耗时。你能从文字里认出 `7` 和 `8`，是因为这个例子只有两个任务、每条都恰好写了项目号。

真实日志长这样：

```
索引完成
读取文件
开始索引
```

一个函数只负责打日志，不负责把上下文拼进字符串，它根本不知道项目号。这时候只能靠行文顺序推断，而并发下顺序不可靠。

## 换成一行一个 JSON {#json-lines}

把 `print` 换成 `logging`，再给每条记录加上字段。新建 `log_json.py`：

```python
import json
import logging
import sys
import threading
import time


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ("request_id", "project_id", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("indexer")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def index_project(request_id, project_id):
    started = time.perf_counter()
    logger.info("index_started", extra={"request_id": request_id, "project_id": project_id})
    time.sleep(0.02)
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "index_finished",
        extra={"request_id": request_id, "project_id": project_id, "duration_ms": elapsed},
    )


threads = [
    threading.Thread(target=index_project, args=("req-1", 7)),
    threading.Thread(target=index_project, args=("req-2", 8)),
]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

运行：

```bash
python log_json.py
```

你会看到类似：

```
{"time": "2026-10-25T15:31:53", "level": "INFO", "event": "index_started", "request_id": "req-1", "project_id": 7}
{"time": "2026-10-25T15:31:53", "level": "INFO", "event": "index_started", "request_id": "req-2", "project_id": 8}
{"time": "2026-10-25T15:31:53", "level": "INFO", "event": "index_finished", "request_id": "req-1", "project_id": 7, "duration_ms": 20.7}
{"time": "2026-10-25T15:31:53", "level": "INFO", "event": "index_finished", "request_id": "req-2", "project_id": 8, "duration_ms": 20.5}
```

时间戳和耗时每次不一样，行的先后顺序也可能变。**每一行仍然是独立完整的事件**，多行之间没有缩进或续行。这就是 JSON Lines：一行一条记录，日志收集器可以逐行解析，`grep` 和 `jq` 也能直接用。

把输出存下来，按请求过滤：

```bash
python log_json.py > app.log
grep '"req-1"' app.log
```

Windows PowerShell 里把第二条命令换成 `Select-String -Pattern '"req-1"' app.log`。你会拿到 `req-1` 的开始和结束两行，`req-2` 的不会再混进来。

## 每行都自带身份 {#fields}

逐项看这一行里的字段。

**`time`** 是日志产生的时间。这里用的是本地时间，格式精确到秒。多个服务一起排查时，最好统一成 UTC 并保留时区，否则跨机器对时间会出错。

**`level`** 是级别，后面单独说。

**`event`** 是事件名，用过去式短语，比如 `index_started` 和 `index_finished`。事件名要稳定、短、可枚举，别把变量拼进去。`index_finished project=7 took 20ms` 这种自由文本，下周加个字段就得改所有查询。

**`request_id`** 是关联 ID。它在请求入口生成一次，这次请求里所有日志都用同一个值。你在入口生成它，传给需要写日志的函数，或者存进 `contextvars`，再用一个 `logging.Filter` 自动塞进每条记录——后者不用层层传参，线程和协程里也能取到。

同一个 `request_id` 还能回给客户端，放在响应头 `X-Request-ID` 里。用户报障时带上它，你就能直接捞出这一次请求的全部日志，不用猜时间窗。

**`project_id`** 是业务键。它回答"这是哪个项目的事"，和 `request_id` 是两条正交的查询维度：按请求看一遍流程，或按项目看历史。

**`duration_ms`** 是耗时，单位写在字段名里，值是数字不是字符串。这样日志系统能做平均值和分位数，写成 `"20.7ms"` 就只能当文本看。

这些字段是怎么进到日志里的？`logger.info("index_started", extra={...})` 的 `extra` 会被附加到 `LogRecord` 对象上，成为它的属性。`JsonFormatter` 用 `hasattr` 检查有没有这个属性，有就写进 JSON。

只传 `extra` 不配格式化器，字段不会出现在默认输出里。默认格式只打印级别、logger 名和消息（很多项目会再加时间），`extra` 里的东西你看不见。**字段能被查询，前提是格式化器把它写出来了。**

## 级别不是情绪 {#levels}

级别决定这条日志会不会被输出、会不会触发告警。用错级别，日志要么全是噪音，要么真出事时找不到。

| 级别 | 记什么 | 例子 |
|---|---|---|
| `DEBUG` | 开发时看的分支细节、变量值 | 用了哪个缓存键、SQL 参数 |
| `INFO` | 正常的状态变化 | 请求开始与结束、配置加载完成 |
| `WARNING` | 预期之外但已经处理 | 第一次调用失败、重试后成功、回退到缓存 |
| `ERROR` | 这次操作失败了，需要人看 | 写库失败、外部接口连续返回 5xx |
| `CRITICAL` | 进程级问题，服务没法继续 | 端口监听失败、必需配置全部缺失 |

几条实际判断：

- 用户输入不合法被你拒绝了，这是正常流程，用 `INFO`。别用 `ERROR`，否则每天的脏数据都会触发告警。
- 重试一次后成功了，用 `WARNING`。它值得被统计，但不需要半夜叫人。
- 同一个循环里每个文件都打一条 `INFO`，一万个文件就是一万行。要么降级到 `DEBUG`，要么只在开始、结束和失败时各打一条。

级别是给机器看的，用来决定"这条要不要留、要不要报警"，不是用来表达你当时有多惊讶。

## 不能写进日志的字段 {#sensitive}

日志会离开你的进程：写到磁盘、被采集器转发、进第三方平台、被索引、保存几个月。能看到日志的人，通常比能看到数据库的人多。所以下面这些东西不该出现：

- 密码、验证码、重置令牌
- `Authorization` 头、Cookie、会话 ID
- API key、数据库连接串里的密码
- 完整的身份证号、银行卡号、手机号
- 带用户名的完整文件路径，比如 `/home/xiaolin/...`
- 包含个人信息的完整请求体

截断也不安全。`sk-live-abcd...` 露出的前缀经常足以定位账号。要么写 `***`，要么干脆不记录这个字段。

记录结构化字段时，在**组装字段之前**就过滤：

```python
SENSITIVE = {"password", "token", "authorization"}


def clean(fields):
    return {k: ("***" if k.lower() in SENSITIVE else v) for k, v in fields.items()}


print(clean({"user": "小林", "password": "hunter2", "token": "abc123"}))
```

输出：

```
{'user': '小林', 'password': '***', 'token': '***'}
```

注意过滤的是字段名，不是值里含不含"password"。用户把密码设成 `mypassword123`，值过滤会误伤；字段名是你能控制的。

还有一处常见泄露：为了排查，把整个 `Settings` 对象序列化进日志。里面有 `api_key` 和数据库地址，整个配置就跟着日志走遍所有下游。

## 日志的存储与隐私成本 {#tradeoffs}

每行日志都要占磁盘、占网络、占索引空间。量大时，存储和索引的成本会很难忽略。所以不是越多越好。

优先记这三类：**状态转移**（开始、完成、失败）、**外部调用结果**（请求了谁、花了多久、什么状态码）、**可恢复的错误**（重试、降级、超时）。这些是排查时真正会查的。

采样和缓冲会让日志缺失。你看到一百条请求只有三条有日志，不代表另外九十七条没执行——可能被采样了、可能还在缓冲区里、可能级别没开。**没有某条日志，不能当作"这条路径没走"的证据。**

日志也不是万能的。指标看整体趋势（错误率、P99 延迟），日志看具体事件（这次请求为什么失败），追踪看跨组件链路（时间花在哪个服务）。三者互补，别指望日志同时干完三件事。

还有一点：日志写"成功"不能代替实际检查返回状态。记录应该发生在你知道结果之后，而不是在发出请求的同时。超时这种结果不确定的情况，日志里就该写"结果未知"，不要写成成功或失败。

## 练习 {#self-check}

**第 1 题**：为什么这里用 `index_started` 和 `index_finished` 两条事件，而不是一条"开始索引，完成后……"？

> **答案**
>
> 一条日志只能表示一个时刻的状态。开始和结束之间可能隔了几十秒，中间可能异常退出。分成两条，`duration_ms` 才有地方放；只有开始没有结束，也正好说明这次请求没走完。
>
> 事件名用过去式，是为了让人一眼看出"这条记录发生时，动作已经到哪一步"。

**第 2 题**：`logger.info("hello", extra={"name": "boom"})` 会发生什么？

> **答案**
>
> 抛 `KeyError`，信息是 `"Attempt to overwrite 'name' in LogRecord"`。
>
> `name`、`message`、`asctime`、`levelname` 这些是 `LogRecord` 自带的属性，`extra` 不能覆盖它们。换个名字，比如 `user_name` 或 `service_name`。

**第 3 题**：一个重置密码的接口为了排查，把请求体完整写进日志。问题在哪？怎么改？

> **答案**
>
> 请求体里有新密码或重置令牌。日志会被转发、长期保存，能看到日志的人比能看到数据库的人多，这等于把凭据扩散出去。
>
> 只记安全字段：用户 ID、请求 ID、结果状态；请求体里只保留字段名，值统一写成 `***`。已经写出去的历史日志要清理，相关令牌要作废。

## 继续阅读 {#related}

- [环境配置：把部署差异移出代码](/learn/config-env)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)
- [限流：保护服务不被自己人打垮](/learn/rate-limit)

## 参考资料 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
