# HTTP 请求与响应

## 一次留言请求包含什么 {#http-overview}

学完这一篇，你能把一次留言板请求拆成请求行、请求头、请求体和响应，并判断 200 背后业务到底成没成。

你在留言板点提交，页面转了一圈，提示“发送成功”，刷新后列表还是空的。打开浏览器 Network 面板，那条请求明明写着 200。

HTTP 是浏览器和服务器之间一来一回的消息格式。请求说明你想做什么，响应说明服务器处理到哪一步。状态码只是响应的一部分；它和响应头、响应体一起，才构成一次完整回答。

## 启动一个本地留言服务 {#http-server}

为了能反复观察同一份报文，先起一个只做留言板的小服务。它只用 Python 标准库，不需要安装依赖。

新建 `http_demo.py`：

```python
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

messages = [{"id": 1, "text": "第一条留言"}]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_json(self, status, data, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/messages":
            self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "没有这个地址"}})
            return
        self.send_json(200, {"items": messages}, headers={"Cache-Control": "no-store"})

    def do_POST(self):
        if self.path != "/messages":
            self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "没有这个地址"}})
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": {"code": "BAD_JSON", "message": "请求体不是合法 JSON"}})
            return
        if not isinstance(data, dict):
            self.send_json(400, {"error": {"code": "BAD_JSON", "message": "请求体必须是 JSON 对象"}})
            return

        text = data.get("text", "")
        if not isinstance(text, str) or not text.strip():
            self.send_json(422, {"error": {"code": "EMPTY_TEXT", "message": "留言不能为空"}})
            return
        if len(text) > 20:
            # 这里故意用 200 表示业务失败，用来说明状态码会骗人。
            self.send_json(200, {"ok": False, "error": {"code": "TEXT_TOO_LONG", "message": "留言最多 20 个字"}})
            return

        message = {"id": len(messages) + 1, "text": text}
        messages.append(message)
        self.send_json(201, {"ok": True, "message": message}, headers={"Location": f"/messages/{message['id']}"})


if __name__ == "__main__":
    print("留言服务已启动：http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
```

在一个终端里运行：

```bash
python http_demo.py
```

你应该看到：

```
留言服务已启动：http://127.0.0.1:8000
```

这个终端不要关。再开一个终端运行后面的 `curl`。服务把留言放在内存里，重启后会回到只有一条留言的状态。

示例命令写成 `curl.exe`，这是 Windows 上直接可用的名字；macOS 和 Linux 用户把 `.exe` 去掉，改用 `curl`。命令都保持一行，单引号写法适用于 PowerShell 7 和 Git Bash；cmd.exe 不支持这种引号，请换到 PowerShell 运行。下面的 JSON 正文用英文，是因为不同终端对中文参数的编码不一致；浏览器提交中文时会按页面编码发送。

## 用 curl 看请求和响应 {#curl-inspect}

先读列表：

```bash
curl.exe -i http://127.0.0.1:8000/messages
```

你应该看到类似下面这一段（每次都变的 `Server`、`Date`、`Content-Length` 已省略）：

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: no-store

{"items": [{"id": 1, "text": "第一条留言"}]}
```

`-i` 让 curl 打印状态行、响应头和空行，然后才是响应体。发一条新留言：

```bash
curl.exe -i -X POST http://127.0.0.1:8000/messages -H "Content-Type: application/json" -d '{"text":"from curl"}'
```

应该得到：

```http
HTTP/1.1 201 Created
Content-Type: application/json; charset=utf-8
Location: /messages/2

{"ok": true, "message": {"id": 2, "text": "from curl"}}
```

再读一次列表：

```bash
curl.exe -s http://127.0.0.1:8000/messages
```

```json
{"items": [{"id": 1, "text": "第一条留言"}, {"id": 2, "text": "from curl"}]}
```

`201` 表示新资源建成了，`Location` 给出它的地址。这个演示服务返回 `{"ok": true, "message": ...}`；真实接口也可能直接返回新对象，形状由契约决定。

如果你重复提交过几次，`id` 会比 2 大，`Location` 也会跟着变。服务重启后从 1 开始。

## 请求行、头和体各管什么 {#request-parts}

`curl -i` 只显示响应。把上面那条 POST 命令的请求部分摊开，它实际发出的内容相当于：

```http
POST /messages HTTP/1.1
Host: 127.0.0.1:8000
User-Agent: curl/8.7.1
Accept: */*
Content-Type: application/json
Content-Length: 20

{"text":"from curl"}
```

`User-Agent` 的版本号会随 curl 安装变化，其他行由命令和地址决定。

**请求行**是第一条：方法 `POST`、请求目标 `/messages`、协议版本 `HTTP/1.1`。主机名不在请求行里，而在 `Host` 头中。请求目标是路径，不是完整 URL；真实请求常带查询串，例如 `/messages?limit=2`。

**请求头**每行一个“名字: 值”。`Host` 告诉服务器访问哪个站点，HTTP/1.1 里通常必须有。`Content-Type` 说明请求体是什么格式，这里告诉服务器“正文按 JSON 解析”。

`Content-Length` 是正文的字节数，不是字符数；中文在 UTF-8 里占多个字节，长度会更大。`Accept` 是客户端希望收到的响应格式，服务器可以满足，也可以不满足。

**空行**把头和正文分开。没有这个空行，服务器会把后面的 JSON 当成又一个头。

**请求体**是空行之后那段 JSON。HTTP 本身不规定它必须是 JSON，是 `Content-Type` 给了服务器解析线索。没有这个头，服务器也许仍能猜到，但不该靠猜。

响应也按同样的结构拆：

**状态行** `HTTP/1.1 201 Created` 里，`201` 是给程序判断的，`Created` 只是给人看的说明，客户端不该依赖这段英文。

**响应头**里的 `Content-Type` 声明响应体格式，`Content-Length` 是响应体字节数，`Location` 是新建资源的地址。

**响应体**才是那段 JSON。

请求方法和动作语义有关，和参数放在哪里没有关系：

| 方法 | 这页里的动作 | 重复发送会怎样 | 说明 |
|---|---|---|---|
| GET | 读留言列表 | 状态通常不变 | 应可安全重复，可被缓存 |
| POST | 新建一条留言 | 可能创建多条 | 不天然幂等，重试要小心 |
| PUT | 整体替换一条留言 | 结果通常相同 | 幂等，但本页没用到 |
| DELETE | 删除一条留言 | 第一条之后通常仍是已删除 | 幂等，但本页没用到 |

“幂等”说的是重复执行后，资源状态和只执行一次一样；响应内容可以不同。GET 是安全方法，语义上不修改资源。POST 没有这个保证，所以连续发两次会得到两条留言，而不是一条。

## 200 也可能是业务失败 {#status-trap}

让留言超过 20 个字：

```bash
curl.exe -i -X POST http://127.0.0.1:8000/messages -H "Content-Type: application/json" -d '{"text":"this message is definitely longer than twenty characters"}'
```

响应是：

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8

{"ok": false, "error": {"code": "TEXT_TOO_LONG", "message": "留言最多 20 个字"}}
```

这里发生了两件不同的事。HTTP 层成功完成了：请求被接收，服务器生成了响应，客户端拿到了完整的 JSON。业务层拒绝了：留言太长，没有创建。

**200 只说明这次 HTTP 交互成功，不说明业务动作成功。** 这个演示服务故意把业务失败写成 200，用来暴露客户端只检查状态码的问题。更清楚的接口会让这里返回 `422` 或 `400`，让状态码本身也表达“请求内容不符合规则”；下一篇的契约就改成这样。

不管服务端用哪种方式，客户端都要按契约同时检查两层：

```javascript
const response = await fetch("http://127.0.0.1:8000/messages", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: "from fetch" }),
});
const data = await response.json();

if (!response.ok || data.ok === false) {
  throw new Error(data.error?.message ?? "请求失败");
}
```

把这段存成 `post.mjs`，启动上面的服务后用 Node 18+ 运行 `node post.mjs`。它假设当前这个 `ok` 形状；如果换成下一篇的资源响应，就没有 `ok` 字段，检查条件也要跟着契约走。不能把某一种错误形状硬套到所有接口上。

还有一层容易漏：`response.json()` 成功只证明响应体是合法 JSON。它不证明字段存在、类型正确，也不证明业务成功。一个 `200` 加 `{"ok": false}` 能顺利解析，仍然是一次失败的业务操作。

## 状态码、缓存和重试的边界 {#http-boundaries}

状态码按第一位分族：

| 范围 | 含义 | 这页附近的例子 |
|---|---|---|
| 2xx | 请求已被接受并处理 | `200` 读取成功，`201` 已创建，`202` 已受理，`204` 成功但无正文 |
| 3xx | 需要跳转或使用缓存副本 | `301` 永久跳转，`304` 资源未修改 |
| 4xx | 按当前请求，服务端无法完成 | `400` 格式错误，`401` 未认证，`403` 无权限，`404` 找不到，`422` 内容不合法 |
| 5xx | 服务端处理时失败 | `500` 内部错误，`502` 上游响应无效，`503` 暂时不可用 |

`401` 和 `403` 不是一回事。`401` 表示缺少有效身份，应该去登录或换凭证；`403` 表示身份已经识别，但不允许这个操作。`404` 也不总是你写错了路径，反向代理前缀配错、路由没挂上，都会从服务端产生 404。

**4xx 和 5xx 的分工看“谁能改什么”，不是看谁该挨骂。** 4xx 通常意味着原样重发没用，要改请求、补认证或换地址；5xx 通常意味着服务端出了问题，可以在安全的前提下退避重试。服务端自己写错验证逻辑，也可能错误地回 4xx；状态族只告诉你先去哪边查，最终还要看响应体和日志。

`Cache-Control` 决定响应能不能被存、能存多久。演示服务返回 `no-store`，浏览器和中间缓存都不该保存这份留言列表，所以刚发完留言再读能看到新数据。

`no-cache` 和它的名字相反：允许保存，但每次使用前必须向服务器确认。`max-age=60` 表示 60 秒内可以直接使用缓存副本，不必问服务器。服务器还可以用 `ETag` 给资源一个版本标识；客户端下次带 `If-None-Match` 来问，没变就回 `304`，没有正文，省一次传输。静态图片和带哈希文件名的脚本适合长缓存，经常变化的私人留言列表不适合。

超时也不等于服务端没做事。客户端 5 秒没等到响应就断开，服务器可能已经插入了留言，只是响应在路上丢了。此时重发 POST 可能创建第二条。

要安全重试，客户端得带一个服务端认识的幂等键，服务端对同一个键只执行一次，或者返回第一次的结果。GET 可以更放心地重试；POST 不能只靠“再点一次”。

异步任务还要多一层区分。接口返回 `202 Accepted` 加一个任务 ID，只表示“受理了”，不表示“做完了”。后续要有一个能查询任务状态的地址或订阅通道，否则调用方拿不到最终结果。

流式响应也类似。响应体分块到达时，一个块不一定是一条完整消息；客户端要按协议解析完整事件，还要区分“暂时没有新数据”和“连接已经结束”。在流结束前把整个响应当成一个 JSON 去 `json()`，通常会失败。

## 四个容易漏看的协议信号 {#http-pitfalls}

**“HTTP 请求成功了，业务就成功了。”** 上面已经撞过一次：`200` 加 `{"ok": false}`，传输完整，业务被拒。先按契约检查状态码，再检查响应体里的业务结果，两个都过才算完成。

**“GET 和 POST 的区别就是把参数放在 URL 还是请求体。”** 方法写的是语义。GET 应只读，代理和浏览器可能预取、缓存；POST 表示提交处理，不保证幂等。连续跑两次 POST，列表里会出现两条内容相同的留言，因为服务器每次都在创建新资源：

```bash
curl.exe -s -X POST http://127.0.0.1:8000/messages -H "Content-Type: application/json" -d '{"text":"again"}'
curl.exe -s -X POST http://127.0.0.1:8000/messages -H "Content-Type: application/json" -d '{"text":"again"}'
```

两次返回的 `id` 不同。相反，同样的 GET 重复执行不会增加留言。不要用 GET 偷偷改数据，缓存和预取会让这种副作用变得不可预测。

**“4xx 一定是前端写错了。”** 4xx 只说明按当前请求完成不了。令牌过期是 401，权限不足是 403，路由前缀漏配可能是 404，服务端改了验证规则会把原本能过的请求变成 422。先读响应体里的错误码，再去对应的日志和契约里找，不要只凭数字猜责任。

**“fetch 收到 404 会直接抛异常。”** 不会。断网、DNS 失败、请求被取消或跨域被拦截这类情况才会让 `fetch` 拒绝；HTTP 404 仍是一个正常到达的响应。需要自己检查：

新建 `check-fetch.mjs`，启动上面的服务后运行：

```javascript
const response = await fetch("http://127.0.0.1:8000/nope");
console.log(response.status, response.ok);
```

运行 `node check-fetch.mjs`，输出：

```
404 false
```

所以 `await fetch(...)` 外面必须有状态检查，不能只靠 `catch` 判断接口失败。

## 三道抓包小题 {#self-check}

**第 1 题**：服务器返回 `200`，正文是 `{"ok": false}`。这次请求算成功吗？

> **答案**
>
> 分两层看。HTTP 交互成功，客户端拿到了完整响应；业务动作失败，服务端明确说没有完成。页面不能只凭 200 显示“发送成功”。
>
> 客户端应按契约检查正文里的失败标志；更合理的服务端设计是返回 `422`，让状态码和业务结果一致。修复前，重试同一条超长留言不会变得合法。

**第 2 题**：提交按钮被点了两次，为什么列表里出现两条同样的留言？只把按钮禁用能解决吗？

> **答案**
>
> 每次 POST 都可能创建一条新资源，POST 不保证幂等。按钮禁用只能挡住一部分重复点击，挡不住超时后的自动重试，也挡不住刷新页面后再次提交。
>
> 真正安全的做法是让服务端按幂等键去重：同一个键的重复请求只创建一次，后续请求返回第一次的结果。客户端还要在失败后先查清状态，不要盲目重发不确定是否成功的写请求。

**第 3 题**：下面几种情况，分别更适合哪个状态码：请求体不是合法 JSON、没有登录、登录了但不能删除别人的留言、留言超长、服务端代码抛异常？

> **答案**
>
> 非法 JSON 是 `400`；没有有效身份是 `401`；身份有效但无权限是 `403`；格式合法但内容不符合业务规则是 `422`；未捕获的服务端异常是 `500`。
>
> 这些数字是分类，不是最终判决。还要给稳定的错误码和可读说明，并确认真实原因；服务端逻辑写错时，也可能错误地产生 4xx。

## 顺着网络请求继续读 {#related}

- [浏览器、前端与后端](/learn/web-client-server)
- [URL、JSON 与 API 契约](/learn/web-api)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 协议资料的出处 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
