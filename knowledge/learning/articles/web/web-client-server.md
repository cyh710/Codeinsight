# 浏览器、前端与后端

## 界面动了，数据没动 {#overview}

学完这一篇，你能说清一次点击在浏览器和服务器之间走了哪几步，并在 Network 面板里看到那次请求的请求行和状态码。

留言板上，你输入“第一条留言”，点提交。按钮立刻变绿，看着像成功了。刷新页面，列表却是空的。

按钮变绿这件事，和留言有没有存下来，是两件不同的事。

## 页面住在浏览器，数据住在服务器 {#two-sides}

打开一个网页，浏览器先把 HTML、CSS、JavaScript 下载到本机。下载完，这三样东西在浏览器里执行：HTML 变成 DOM，CSS 决定样子，JS 改 DOM、发请求。你看到的按钮、输入框、那列留言，全在这个标签页的内存里。

后端是另一个进程。它没有按钮，也不管颜色，管的是这条留言该不该收、放到哪、下次谁看得到。

| 事情 | 浏览器里做 | 服务器上做 |
|---|---|---|
| 按钮变色、输入框清空 | 是 | 不需要 |
| 检查输入不能为空 | 可以，挡掉手滑 | 必须再查，挡住绕过页面的人 |
| 判断谁能删留言 | 只能把按钮藏起来 | 决定请求收不收 |
| 把留言存下来 | 只能发请求请服务器存 | 是 |
| 让另一个用户看到 | 不能 | 是 |

这两边各有自己的内存。浏览器里 `document.querySelector("#list")` 拿到的是 DOM 节点；服务器里 `messages` 是一个 Python 列表。往 DOM 里塞一个 `li`，不会让 `messages` 多一项；往 `messages` 里 append，也不会自动让任何人的页面多一个 `li`。

这一篇的例子把两边放在同一台电脑上：一个 `server.py`，一个 `index.html`，都通过本机地址访问。但它们是两个进程，内存互不相通。

## 让留言板发一次真实的请求 {#hands-on}

新建一个文件夹，放进去两个文件。

`server.py`：

```python
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

messages = []  # 只放在内存里，进程一停就没了


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/":
            with open("index.html", "rb") as f:
                body = f.read()
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/api/messages":
            body = json.dumps(messages, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/messages":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        text = json.loads(raw)["text"]
        messages.append(text)
        self._send(201, "application/json", b'{"ok": true}')

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
```

`index.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>留言板</title>
</head>
<body>
  <h1>留言板</h1>
  <input id="text" placeholder="写点什么">
  <button id="send">提交</button>
  <p id="status"></p>
  <ul id="list"></ul>

  <script>
    const button = document.querySelector("#send");
    const input = document.querySelector("#text");
    const status = document.querySelector("#status");
    const list = document.querySelector("#list");

    button.addEventListener("click", async () => {
      // 这一行只改浏览器里的样式，和后端没有关系
      button.style.background = "#b7f0c0";
      status.textContent = "正在保存…";

      try {
        const response = await fetch("/api/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: input.value })
        });

        if (!response.ok) {
          status.textContent = "后端拒绝了这次保存：" + response.status;
          return;
        }

        const li = document.createElement("li");
        li.textContent = input.value;
        list.append(li);
        input.value = "";
        status.textContent = "已保存";
      } catch (error) {
        status.textContent = "请求没发出去，后端可能没开";
      }
    });
  </script>
</body>
</html>
```

在文件夹里运行：

```bash
python server.py
```

然后打开 `http://127.0.0.1:8000/`。端口被占用时 Python 会报地址已被占用，把代码里的 8000 换成 8001，地址也换成 8001。

你应该看到：一个“留言板”标题、一个输入框、一个提交按钮，下面没有内容。输入“第一条留言”再点提交，按钮变成浅绿色，状态文字先显示“正在保存…”，再变成“已保存”（本机请求很快，中间那一步可能一闪而过），列表里多出“第一条留言”，输入框清空。

```text
标签页标题：留言板
点击前：留言板 / [写点什么] / [提交] / （空白）
点击后：按钮浅绿 / 已保存 / • 第一条留言 / 输入框为空
```

现在做个更重要的实验。回到终端按 `Ctrl+C` 停掉服务器，**不要刷新页面**。再输入“第二条留言”，点提交。

```text
按钮：仍然变绿
状态：请求没发出去，后端可能没开
列表：没有新增
```

按钮照样响应，因为改颜色是浏览器自己做的。服务器已经停了，请求送不到，留言当然没存。这两个结果出现在同一个动作里，互不矛盾。

看完这个对比，重新运行 `python server.py`，刷新页面。服务器里的 `messages` 已经随进程结束清空，这是内存存储的代价；后面还要在 Network 里看一次成功的请求。

## 在 Network 面板里抓住这次请求 {#network}

按 `F12`，或者 `Ctrl+Shift+I`，切到 Network（网络）面板。勾上 Preserve log（保留日志），过滤器选 Fetch/XHR。

输入“第一条留言”，再点一次提交，Network 列表里会多出一行，名字是 `messages`。点开它：

| 位置 | 你会看到 |
|---|---|
| Headers → Request URL | `http://127.0.0.1:8000/api/messages` |
| Headers → Request Method | `POST` |
| Headers → Status Code | `201 Created` |
| Payload（载荷） | `{"text":"第一条留言"}` |
| Response（响应） | `{"ok": true}` |

把过滤器切回 All，还能看到页面刚打开时对 `/` 的 `GET`，那是浏览器来取 HTML 的。中间可能夹着 `favicon.ico` 的 404，和保存留言无关。你要找的是点击提交之后新出现的 POST。

这次请求本身只是一段文本。去掉浏览器自动加的几个头，它大致长这样：

```http
POST /api/messages HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{"text": "第一条留言"}
```

服务器返回：

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"ok": true}
```

请求第一行是方法、路径、协议版本。`Host` 说明找哪台机器上的哪个服务。`Content-Type` 告诉服务器“正文按 JSON 解析”，所以 Python 那边可以直接 `json.loads`。空行把头部和正文分开，空行下面是 JSON。

响应第一行是协议版本、状态码、短语。`201` 表示服务器说“创建了”。正文是 `{"ok": true}`，前端这段代码只看状态码，没有读它。

状态码按百位分组：`2xx` 表示服务器接受了，`4xx` 表示请求本身有问题，`5xx` 表示服务器处理时出错。这里的 POST 成功是 `201`，GET 是 `200`，路径不对是 `404`。

## 点击和保存之间，隔着三份状态 {#mechanism}

把点击后的这一小段过程拆开看，有三份状态在各自变化。

**第一份是输入框的 `value`。** 它只存在于浏览器内存里。你还没点提交时，服务器什么都不知道。

**第二份是 DOM 里的 `li`。** 服务器返回 201 后，`document.createElement("li")` 建一个节点，`list.append(li)` 把它挂到 `ul` 下面。页面因此多一行字。

**第三份是服务器里的 `messages` 列表。** `do_POST` 读完请求体，`json.loads(raw)["text"]` 取出字符串，`messages.append(text)` 把它加进 Python 列表。

三份状态由不同的代码改。只有服务器那一行让数据离开了浏览器：

1. 点击触发事件处理函数，`button.style.background = ...` 改的是按钮的样式，没有网络。
2. `fetch` 按你给的 method、headers、body 组一个请求，返回一个 Promise。
3. 请求到达 Python，`do_POST` 被调用，`Content-Length` 告诉它要读多少字节。
4. `messages.append(text)` 执行，服务器内存变了。
5. `_send` 写回 `201` 和 JSON 正文。
6. `await` 拿到响应，`response.ok` 为 true，前端才建 `li`、清空输入框。

停掉服务器时，第 3 步失败，第 4 到 6 步都不发生。但第 1 步已经跑完了，所以按钮是绿的。**界面成功和保存成功，卡在第 3 步这个边界上。**

还要知道一件事：`fetch` 在服务器返回 404 或 500 时**不会**抛异常。它只在网络层失败（连不上、被断开）时 reject。所以代码里必须检查 `response.ok`；不检查的话，一个 500 响应也会被当成成功，继续往列表里加留言。

刷新页面后列表空了，可能有两种完全不同的原因：

- 服务器重启过，`messages` 是内存列表，数据没了。
- 服务器里还有数据，但这个页面打开时根本没去请求 `/api/messages`，它只是重新画了一个空 `<ul>`。

区分方法很直接：新开一个标签页访问 `http://127.0.0.1:8000/api/messages`。那里有 JSON 数组而页面是空的，就是第二种；那里是 `[]`，就是第一种或根本没存进去。

## 五个关于请求的错误结论 {#pitfalls}

**“按钮变绿了，后端一定收到了。”** 绿是 `button.style.background` 改的，这行代码在 `fetch` 前面。停掉服务器再点，按钮照样绿。要判断后端收没收到，看 Network 里的状态码。

**“页面和接口都写本机地址，所以它们肯定在同一台机器。”** `127.0.0.1` 和 `localhost` 都表示“当前进程所在的这台机器”。浏览器和服务器都跑在你的电脑上时，它们是同一个地方；服务器跑在 Docker 容器或虚拟机里时，容器里的 `localhost` 是容器自己。这时需要端口映射或把地址换成宿主机地址。不同端口也代表不同服务，`8000` 和 `3000` 不是一回事。

**“把提交按钮藏起来，别人就发不了这条请求。”** 隐藏按钮只改变页面。打开 Console，或者用任何能发 HTTP 的工具，请求照样能发：

```javascript
fetch("/api/messages", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: "绕过按钮" })
});
```

服务器必须自己检查“这个请求允不允许”。按钮的可见性不是权限。

**“Network 里状态是 201，就说明数据存对了。”** `201` 只说明服务器选择这样回答。它可能把内容存错了地方，可能只放进内存，也可能返回一个业务失败但状态码仍是 200 的 JSON。至少再核对三样：载荷里的 `text` 是不是你输入的、响应正文说了什么、重新读取 `/api/messages` 还能不能拿到。

**“跨源请求报 CORS 错，就是后端没启动。”** CORS 是浏览器对“这个源的脚本能不能读取那个源的响应”的限制。服务器可能正常运行，只是没给允许跨源的响应头。用 `curl` 或后端之间互相调用不受这条浏览器规则约束。CORS 也不是登录验证：允许跨源不等于允许任何人改数据。

## 哪一步该由哪一边做 {#split}

浏览器擅长立刻给反馈：按钮按下就变样、输入框清空、正在保存的提示。它也能做便宜的格式检查，比如 `required`、字数上限，让用户不用等一个来回。

服务器负责可信的判断：这个留言是不是空的、长度有没有超限、这个人有没有权限、数据最终写到哪。前端检查是给正常人省时间，后端检查是给所有人兜底。

把“先显示、再确认”推进一步，就是乐观更新：点提交就把留言画进列表，请求失败再删掉或标红。页面响应更快，代价是要写清楚失败后怎么恢复，否则用户会以为存上了。这里的代码只让按钮颜色乐观，列表仍然等服务器确认。

出问题时沿着边界走，比盯着界面猜有用：

1. Network 里有没有新请求？没有，问题在前端事件或脚本报错。
2. 有请求的话，路径、方法、载荷对不对？
3. 状态码是几开头？
4. 响应正文说了什么？
5. 页面有没有按这个响应更新？

这条顺序把“前端没触发”“请求发错地方”“后端拒绝”“界面没更新”分成了四种情况。它们看起来都像“没保存”，修法完全不同。

## 三道关于请求的判断题 {#self-check}

**第 1 题**：页面显示“已保存”，刷新后留言没了。列出至少两种可能，并说明怎么区分。

> **答案**
>
> 三种常见情况：
>
> 1. 服务器只把留言放在内存里，进程重启就没了（本页的 `server.py` 就是这样）。
> 2. 请求根本没成功，界面上的“已保存”写错了位置或没等结果。
> 3. 数据其实还在，但页面打开时没请求过 `/api/messages`，刷新只是重新画了一个空列表。
>
> 先看 Network 里 POST 的状态码和响应，再在新标签页打开 `http://127.0.0.1:8000/api/messages`。接口有数据而页面是空的，是第 3 种；接口是 `[]`，是第 1 或第 2 种。

**第 2 题**：点击提交后 Network 里一条新请求都没有。先查哪三处？

> **答案**
>
> 1. Console 有没有红色报错。选择器写错时，`document.querySelector("#send")` 返回 `null`，`addEventListener` 会立刻抛错，后面的 `fetch` 根本执行不到。
> 2. 按钮的 `id` 和 JS 里的选择器是否一致。
> 3. Network 的过滤器和保留日志设置。切到了别的类型，或者面板打开得太晚，都会让你看不见已经发出的请求。
>
> 先在 Console 里运行 `document.querySelector("#send")`，确认它拿到的是那个按钮，不是 `null`。

**第 3 题**：前端已经用 `required` 和 `if (!text) return` 拦了空留言，后端还要不要拒绝空字符串？

> **答案**
>
> 要。前端检查只保护这个页面。在 Console 里运行下面这段，就绕过了输入框和按钮：
>
> ```javascript
> fetch("/api/messages", {
>   method: "POST",
>   headers: { "Content-Type": "application/json" },
>   body: JSON.stringify({ text: "" })
> });
> ```
>
> 服务器得自己判断 `text` 是否为空、长度是否超限、这个人有没有权限。前端检查省用户时间，后端检查才是信任边界。

## 沿这条线往下读 {#related}

- [HTTP 请求、方法与状态码](/learn/web-http)
- [URL、JSON 与 API 契约](/learn/web-api)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [HTML：页面的结构与语义](/learn/web-html)

## 文档出处 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
