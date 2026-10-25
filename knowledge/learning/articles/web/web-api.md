# URL、JSON 与 API 契约

## 一个字段名对不上，页面就安静了 {#api-overview}

学完这一篇，你能为留言板写出请求和响应的契约，分清路径参数与查询参数，并在改字段时判断哪些客户端会坏。

前端写完提交：`fetch` 返回 200，JSON 也解析成功，但列表里新留言不显示。查了半天才发现，后端返回的字段叫 `content`，前端读的是 `text`。两边都觉得“接口已经通了”。

JSON 只保证文本能解析，不保证字段名、类型和含义对得上。API 契约把 URL、方法、请求体、响应体、错误形状和字段稳定性写清楚，让两端拿同一份约定写代码。

## 把留言板的契约写成请求和响应 {#contract-example}

先看创建一条留言的请求：

```http
POST /messages HTTP/1.1
Host: 127.0.0.1:8001
Content-Type: application/json

{"text":"from contract client"}
```

成功响应：

```http
HTTP/1.1 201 Created
Content-Type: application/json; charset=utf-8
Location: /messages/2

{
  "id": 2,
  "text": "from contract client",
  "createdAt": "2026-10-25T07:32:09Z"
}
```

`201` 表示创建成功，`Location` 指向新资源。响应里的 `createdAt` 是服务端生成的 UTC 时间，每次运行都会不同；形状不变，值会变。

请求内容不合法时，响应长这样：

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/json; charset=utf-8

{
  "error": {
    "code": "TEXT_TOO_LONG",
    "message": "留言最多 20 个字",
    "field": "text"
  }
}
```

这份契约里有几项明确的约定：

- 创建留言只接受 `text`，它是字符串，去掉首尾空格后长度在 1 到 20 之间。未知字段可以忽略，但不会写进资源。
- `id` 是整数，`text` 是非空字符串，`createdAt` 是 UTC 时间的 ISO 8601 字符串。
- 错误响应固定放在 `error` 对象里。`code` 给程序判断，`message` 给人看，`field` 指出哪个字段有问题；没有对应字段时可以没有 `field`。
- `Content-Type` 为 `application/json; charset=utf-8`。请求和响应都按 UTF-8 编码 JSON。
- 路径 `/messages` 表示留言集合。创建成功返回 `201`；请求格式错返回 `400`；内容不符合规则返回 `422`；地址不存在返回 `404`。

读取列表的约定是另一个形状：

```http
GET /messages?limit=2 HTTP/1.1
Host: 127.0.0.1:8001
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8

{
  "items": [
    {"id": 1, "text": "第一条留言", "createdAt": "2026-10-24T08:00:00Z"},
    {"id": 2, "text": "from contract client", "createdAt": "2026-10-25T07:32:09Z"}
  ],
  "nextCursor": null
}
```

列表没有直接返回一个裸数组，而是包在 `items` 里。这样以后要加 `total`、`nextCursor` 或别的分页信息，就有地方放。`nextCursor: null` 表示没有下一页；以后游标分页真的启用时，它会变成字符串。

`POST /messages` 和 `GET /messages` 用的是同一个路径，语义由方法区分：GET 读集合，POST 往集合里加一条。路径不变，动作变，客户端的路由也更稳定。

## 路径说是什么，查询说哪一批 {#path-query}

URL 里能放参数的位置不止一个，分工要定清楚。

```text
协议 + 主机：http://127.0.0.1:8001
路径：       /messages/42
查询：       ?limit=2
片段：       #newest
```

路径回答“访问哪个资源”。`/messages` 是留言集合，`/messages/42` 是其中一条留言。查询串回答“这批结果怎么选”：`limit=2` 限制数量，`before=42` 可以表示游标位置，`sort=newest` 表示排序。片段以 `#` 开头，通常只给客户端自己定位，普通 HTTP 请求不会把它发给服务器。

这篇的演示服务只实现了集合读取。`/messages/42` 是设计上的单条资源地址，服务端要另加一条路由才能返回它；路径该怎么分，和演示代码有没有实现，是两件事。

| 需求 | 放哪里 | 例子 |
|---|---|---|
| 哪一类资源 | 路径 | `/messages` |
| 哪一条资源 | 路径 | `/messages/42` |
| 返回多少条、怎么排、从哪继续 | 查询参数 | `/messages?limit=20&sort=newest` |
| 新留言的内容 | 请求体 | `{"text":"..."}` |

路径里的一个段如果本身包含 `/`，要编码后再拼进去：

```javascript
const id = "a/b";
console.log(encodeURIComponent(id));
```

输出：

```
a%2Fb
```

不编码的话，`/messages/a/b` 会被当成三级路径。查询参数用 `URLSearchParams` 拼，别手工拼字符串再加 `?` 和 `&`，否则空格、中文和 `&` 都可能破坏参数边界。

内容不要塞进查询串。留言正文可能很长，URL 会进浏览器历史、服务器访问日志和代理日志；用 POST 请求体承载更合适。GET 的查询适合筛选条件，不适合提交新内容。

## 跑一遍创建和读取 {#api-walkthrough}

新建 `api_demo.py`：

```python
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import parse_qs, urlparse

messages = [
    {"id": 1, "text": "第一条留言", "createdAt": "2026-10-24T08:00:00Z"}
]


def error(code, message, field=None):
    detail = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    return {"error": detail}


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
        parsed = urlparse(self.path)
        if parsed.path != "/messages":
            self.send_json(404, error("NOT_FOUND", "没有这个地址"))
            return

        raw_limit = parse_qs(parsed.query).get("limit", ["20"])[0]
        try:
            limit = int(raw_limit)
        except ValueError:
            self.send_json(400, error("BAD_LIMIT", "limit 必须是整数", "limit"))
            return
        if not 1 <= limit <= 100:
            self.send_json(422, error("LIMIT_OUT_OF_RANGE", "limit 必须在 1 到 100 之间", "limit"))
            return

        self.send_json(200, {"items": messages[-limit:], "nextCursor": None})

    def do_POST(self):
        if urlparse(self.path).path != "/messages":
            self.send_json(404, error("NOT_FOUND", "没有这个地址"))
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, error("BAD_JSON", "请求体不是合法 JSON"))
            return
        if not isinstance(data, dict):
            self.send_json(400, error("BAD_JSON", "请求体必须是 JSON 对象"))
            return

        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            self.send_json(422, error("EMPTY_TEXT", "留言不能为空", "text"))
            return
        if len(text) > 20:
            self.send_json(422, error("TEXT_TOO_LONG", "留言最多 20 个字", "text"))
            return

        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        message = {
            "id": messages[-1]["id"] + 1,
            "text": text,
            "createdAt": created_at,
        }
        messages.append(message)
        self.send_json(201, message, headers={"Location": f"/messages/{message['id']}"})


if __name__ == "__main__":
    print("契约服务已启动：http://127.0.0.1:8001")
    ThreadingHTTPServer(("127.0.0.1", 8001), Handler).serve_forever()
```

在一个终端启动：

```bash
python api_demo.py
```

应该看到：

```
契约服务已启动：http://127.0.0.1:8001
```

另建 `client.mjs`：

```javascript
const base = "http://127.0.0.1:8001";

async function readJson(response) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(`${response.status} ${data.error.code}: ${data.error.message}`);
  }
  return data;
}

function assertMessage(value) {
  if (
    !Number.isInteger(value.id) ||
    typeof value.text !== "string" ||
    typeof value.createdAt !== "string"
  ) {
    throw new Error("响应不符合契约");
  }
}

const response = await fetch(`${base}/messages`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: "from contract client" }),
});

const created = await readJson(response);
assertMessage(created);
console.log(created.id, created.text);

const listResponse = await fetch(`${base}/messages?limit=2`);
const list = await readJson(listResponse);
list.items.forEach(assertMessage);
console.log(list.items.length, list.nextCursor ?? "no more");
```

运行：

```bash
node client.mjs
```

输出：

```
2 from contract client
2 no more
```

如果运行 `client.mjs` 之前已经提交过别的留言，`id` 会从更大的数开始；`createdAt` 每次不同，所以客户端没有打印它。重点是第一行拿到了新建对象的字段，第二行证明列表响应里的每一条都通过了字段检查。

服务端的两个分支对应两条约定。GET 先用 `urlparse` 分开路径和查询串，路径不是 `/messages` 就回 404；`limit` 取不到时用默认值 20，转不成整数回 400，超出 1 到 100 回 422；`messages[-limit:]` 取最近的若干条，再用 `send_json` 包成 `items` 和 `nextCursor`。

POST 先按 `Content-Length` 读完请求体，解析 JSON，确认它是一个对象，再检查 `text` 是否存在、非空、长度不超过 20。任何一步失败都返回错误对象；全部通过才追加 `id`、`createdAt`，回 201 和 `Location`。

`send_json` 每次负责三件容易忘的事：把中文按 UTF-8 编码、写对 `Content-Type`、用字节数写 `Content-Length`。少了其中一项，curl 或客户端就可能读不完整、读错编码，或者把响应体截断。

用 curl 发一条超长留言，看错误响应：

```bash
curl.exe -i -X POST http://127.0.0.1:8001/messages -H "Content-Type: application/json" -d '{"text":"this message is definitely longer than twenty characters"}'
```

看到的是：

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/json; charset=utf-8

{"error": {"code": "TEXT_TOO_LONG", "message": "留言最多 20 个字", "field": "text"}}
```

Windows 上用 `curl.exe`，macOS 和 Linux 用 `curl`。单引号写法适用于 PowerShell 7 和 Git Bash；cmd.exe 不支持这种引号，请换到 PowerShell 运行。响应里省略了会变化的 `Date`、`Server` 和 `Content-Length`。

客户端拿到 `422` 后，`readJson` 不会把响应当成成功对象继续用。它先解析错误体，再抛出带错误码的异常；这个错误体本身也必须符合契约，否则前端读 `data.error.code` 时同样会崩。

服务端用 `messages[-1]["id"] + 1` 生成编号，放在这个只有单个进程的演示里够用。多进程或多实例同时写时，这种方式会撞号；真实系统把编号交给数据库或专门的 ID 生成器。

## 加字段和改字段名的后果不同 {#versioning}

在响应里新增一个可选字段，通常最安全。加入 `author`：

```json
{
  "id": 2,
  "text": "from contract client",
  "createdAt": "2026-10-25T07:32:09Z",
  "author": null
}
```

旧客户端如果只读取自己认识的字段，会忽略 `author`，继续工作。前提是契约明确写了“客户端应忽略未知字段”。如果旧客户端对响应做严格的全字段校验，多一个字段就会失败；所以“加字段一定兼容”并不是自动成立的。

新增一个必填的请求字段就不一样了。假设要求每个请求都带 `authorId`，旧客户端仍在发 `{"text":"..."}`，服务端会返回 422。它们不是“忽略新字段”，而是没有提供必需信息，必须升级才能提交。

改字段名是另一类风险。把 `text` 悄悄改成 `content`：

```json
{
  "id": 2,
  "content": "from contract client",
  "createdAt": "2026-10-25T07:32:09Z"
}
```

JSON 仍然是合法的，状态码仍然可以是 201，旧客户端读 `data.text` 得到 `undefined`，页面看起来就是“提交成功但没有内容”。这类问题不会在语法解析阶段报错。

| 变更 | 旧客户端可能怎样 | 是否通常兼容 |
|---|---|---|
| 新增可选响应字段 | 忽略它，继续工作 | 兼容，但要看客户端是否严格校验 |
| 新增必填请求字段 | 不发送，服务端拒绝 | 不兼容 |
| 字段改名或删除 | 旧字段读到 `undefined` | 不兼容 |
| 放宽取值限制 | 原本能过的请求继续能过 | 通常兼容 |
| 把 `id` 从数字改成字符串 | 类型检查失败，排序或比较出错 | 不兼容 |

确实要改名时，通常让旧字段和新字段并存一段时间。服务端同时返回 `text` 和 `content`，文档标清废弃日期，监控旧字段的调用量；等调用方迁完再删。改动大到无法并存时，再开新版本路径，例如 `/v2/messages`，而不是让所有旧客户端在某个凌晨同时失效。

版本号不是免费的。每多一个版本，就要多维护一套测试、文档和兼容逻辑。优先做向后兼容的加法；把“改名字”留到真的无法避免的时候。

## 能 JSON.parse 不等于符合契约 {#parse-vs-contract}

`JSON.parse` 只检查语法，不检查字段。下面这段能被解析：

```javascript
const data = JSON.parse('{"id":"42","text":"你好"}');
console.log(typeof data.id);
```

输出：

```
string
```

按这篇的契约，`id` 应该是整数，`createdAt` 也必须存在。语法通过，语义已经错了。新建 `check.mjs` 写一个小检查：

```javascript
const data = JSON.parse('{"id":"42","text":"你好"}');
const problems = [];

if (!Number.isInteger(data.id)) problems.push("id 必须是整数");
if (typeof data.text !== "string") problems.push("text 必须是字符串");
if (typeof data.createdAt !== "string") problems.push("createdAt 必须是字符串");

console.log(problems.join("；"));
```

运行 `node check.mjs`，输出：

```
id 必须是整数；createdAt 必须是字符串
```

这才是“校验契约”的动作：先确认字段存在、类型正确，再检查业务约束，例如文本长度、ID 范围、时间格式。`client.mjs` 里的 `assertMessage` 只检查了三个字段的类型和 `id` 的整数性；如果契约还要求 `createdAt` 是合法时间，它也应该继续检查，而不是看到一个字符串就放行。

校验应该发生在信任边界：网络响应、用户输入、本地存储、URL 参数进入系统时。TypeScript 接口能帮你在编译期发现自家代码里的字段拼写错误，但那些类型运行时会被擦掉；服务器真发来 `id: "42"`，编译期类型不会替你拦住。

也不要用 `Number(data.id)` 把错误悄悄修好。这样页面临时能跑，契约漂移被掩盖，等某个 ID 超过安全整数范围时问题才冒出来。更好的做法是记录一条可追踪的错误，让服务端修正响应。

JSON 不是任意 JavaScript 表达式。它不支持函数、注释和循环引用，数字还有跨语言的精度边界。不要把响应文本丢给 `eval`；解析 JSON 用 `JSON.parse`，验证结构用自己的代码或 schema 库。

## 契约该严到什么程度 {#api-tradeoffs}

输入要严，输出要宽容。服务端应拒绝错误的类型、缺失的必填字段和越界值，并给出稳定的错误码；客户端读响应时应忽略新增的未知字段，但对必需字段做类型检查。两头都做“差不多能用”，问题会推迟到更难查的地方。

字段命名要一致。这篇用 `createdAt` 的 camelCase，因为客户端是 JavaScript；服务端数据库列可能叫 `created_at`，转换应该发生在边界，而不是让同一个响应里同时出现两种拼法。混合命名会让每个接口都多一层猜测。

分页形状要提前想。裸数组看起来简洁，但以后要加总数、下一页游标、错误信息就没位置。这里用 `{"items": [...], "nextCursor": null}`，代价是调用方多读一层；换来的是形状可以继续扩展。分页的细节也属于契约：`limit` 的最大值、游标失效条件、排序是否稳定，都要写。

ID 的类型也要提前定。JavaScript 的 `Number` 只能精确表示一定范围内的整数，超过边界的大整数会静默丢精度。留言板的小编号用整数很方便；如果 ID 来自会变得很大的序列，字符串更安全。这个决定一旦发布，再改类型就是破坏性变更。

契约最好有可执行的检查。OpenAPI、JSON Schema、生成的类型、端到端测试都能承担一部分；至少要有成功响应、错误响应和边界值的例子。只写“返回留言列表”不算契约，因为这句话无法告诉调用方字段叫什么、错误怎么读、少了字段算不算坏。

## 三道契约小题 {#self-check}

**第 1 题**：服务端返回 `{"id":"42","text":"你好"}`，前端 `JSON.parse` 成功。按这篇的契约，哪里不符合？

> **答案**
>
> JSON 语法合法，但 `id` 是字符串，契约要求整数；`createdAt` 也缺失。
>
> 客户端应该拒绝这条响应或上报契约错误，不能因为页面“暂时能显示”就放过。`Number(data.id)` 会把类型问题藏起来，等 ID 变大时才以更隐蔽的方式出错。

**第 2 题**：要读取一条留言和读取一页留言，URL 分别怎么写？`limit` 应该放在哪里？

> **答案**
>
> 单条用路径：`GET /messages/42`。列表用集合路径加查询：`GET /messages?limit=20`。
>
> 路径标识资源，查询限制结果。ID 拼进路径前要 `encodeURIComponent`；查询参数用 `URLSearchParams` 组合，避免特殊字符改变 URL 结构。

**第 3 题**：给响应加一个 `author` 字段，和把 `text` 改名成 `content`，对旧客户端的影响有什么不同？改名时怎么降低风险？

> **答案**
>
> 新增 `author` 是加法。旧客户端只要忽略未知字段，就能继续读 `text` 和 `createdAt`；如果它做了严格全字段校验，仍可能失败，所以契约要说明未知字段的处理方式。
>
> 改名会让旧客户端读到 `undefined`，而且 JSON 解析和状态码都不会报错。稳妥做法是让 `text` 和 `content` 并存一段时间，标记旧字段废弃，观察调用方迁移，再删除旧字段；破坏性大时开新版本路径。

## 从留言板走向其他接口 {#related}

- [HTTP 请求与响应](/learn/web-http)
- [interface、type 与结构契约](/learn/ts-interfaces)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 契约资料的出处 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
