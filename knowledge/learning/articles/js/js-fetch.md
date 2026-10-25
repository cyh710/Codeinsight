# 网络请求、取消与失败处理

## 一次请求可能在哪几步失败 {#overview}

学完这一篇，你能把一次请求的失败拆成四层分别处理，并在用户切换频道时取消或丢弃迟到的旧结果。

留言板一打开就要向后端要数据。用户盯着空白列表，可能遇到的情况不止一种：网线断了、服务器返回 404、返回的是一页 HTML、接口返回 `{ ok: false }`。这四种失败发生在不同位置，长着不同的样子。

`fetch` 只回答一个问题：有没有拿到响应。拿到之后，状态码对不对、正文能不能解析、业务上算不算成功，都得你自己判断。把它们混进一个 `catch`，用户只会看到一句没用的“请求失败”。

## 向公开接口要五条留言 {#first-request}

先不搭后端，用 JSONPlaceholder 这个公开测试接口。打开浏览器控制台，跑：

```js
fetch('https://jsonplaceholder.typicode.com/comments?postId=1')
  .then(res => {
    console.log(res.status, res.ok);   // 200 true
    return res.json();                 // 读正文，也要等
  })
  .then(data => {
    console.log(data.length);          // 5
    console.log(data[0].email);        // Eliseo@gardner.biz
  })
  .catch(err => console.error('请求失败：', err.message));
```

你应该看到：

```
200 true
5
Eliseo@gardner.biz
```

第一行来自响应对象：`status` 是 HTTP 状态码，`ok` 在 200–299 时为 `true`。此时正文还没读——`fetch` 在收到响应头时就兑现了，不等整个响应体下载完。

`res.json()` 才开始读正文并解析。它返回的又是一个 Promise，所以要 `return` 出去，让下一个 `.then` 接住解析后的数据。这一步失败，会走到 `.catch`。

把这个流程包成函数，加上四种失败的出口：

```js
async function loadMessages() {
  let response;
  try {
    response = await fetch('https://jsonplaceholder.typicode.com/comments?postId=1');
  } catch (err) {
    // 根本没拿到响应
    return { kind: 'network', message: err.message };
  }

  if (!response.ok) {
    // 服务器回了，但状态码不是 2xx；fetch 不会为它抛错
    return { kind: 'http', message: `HTTP ${response.status}` };
  }

  let data;
  try {
    data = await response.json();
  } catch (err) {
    return { kind: 'parse', message: '返回的不是合法 JSON' };
  }

  // JSONPlaceholder 直接给数组；真实后端常包一层，这里统一成 { ok, data }
  const payload = Array.isArray(data) ? { ok: true, data } : data;

  if (payload.ok === false) {
    return { kind: 'business', message: payload.error ?? '操作失败' };
  }

  return { kind: 'ok', data: payload.data };
}

loadMessages().then(result => {
  console.log(result.kind);          // ok
  console.log(result.data.length);   // 5
});
```

```
ok
5
```

函数不抛异常，而是把“哪种失败”当成返回值交出去。调用方拿到 `kind`，就能决定显示什么、要不要给重试按钮。若你更习惯抛异常，也可以给每层包一个自定义错误类，但别把四层压成一句 `catch`。

## 把四种失败拆成四条出口 {#four-failures}

| 失败在哪 | 怎么发现 | 典型原因 |
|---|---|---|
| 没拿到响应 | `fetch` 抛出 `TypeError` | 断网、域名解析失败、被 CORS 拦下 |
| 拿到响应但状态码不对 | `res.ok === false` | 404、500、502 |
| 正文不是合法 JSON | `res.json()` 抛出 `SyntaxError` | 服务器返回了 HTML 错误页 |
| JSON 合法但业务失败 | `data.ok === false` | 参数校验失败、没权限、内容为空 |

四种情况可以各自验证。404 不会进 `catch`：

```js
fetch('https://jsonplaceholder.typicode.com/comments/999999')
  .then(res => console.log(res.status, res.ok));   // 404 false
```

```
404 false
```

正文不是 JSON 时，`res.json()` 才报错。用 `Response` 构造一个假的响应就能试：

```js
new Response('<html>出错了</html>', { status: 200 })
  .json()
  .catch(err => console.log(err.name));   // SyntaxError
```

```
SyntaxError
```

网络层失败，`fetch` 直接拒绝：

```js
fetch('https://no-such-host.invalid/')
  .catch(err => console.log(err.name));   // TypeError
```

```
TypeError
```

所以 `fetch` 的 `catch` 只负责第一层。第二层要自己看 `res.ok`，第三层要包住 `res.json()`，第四层要读业务字段。少一层，用户就会在应该报“内容为空”的时候看到“请求失败”，或者更糟——程序把错误页当成数据继续渲染。

## 切换频道时，迟到的响应会盖掉新界面 {#stale-response}

留言板顶部有两个频道按钮：A 和 B。用户点 A，请求发出去；网络慢，用户等不及，又点 B；B 的响应很快回来了，列表显示 B 的留言。过一会儿 A 的响应才到，代码照常渲染——列表变成 A 的内容，可按钮还停在 B。

这不是请求失败，是**响应迟到了**。发起顺序和到达顺序不一致，后到的旧结果覆盖了新界面。

```js
const list = document.querySelector('#list');
const errorBox = document.querySelector('#error');

let activeChannel = null;
let currentController = null;

function render(messages) {
  list.replaceChildren(...messages.map(text => {
    const li = document.createElement('li');
    li.textContent = text;
    return li;
  }));
}

function showError(text) {
  errorBox.textContent = text;
}

async function showChannel(id) {
  activeChannel = id;
  currentController?.abort();              // 上一路还在等，就取消它

  const controller = new AbortController();
  currentController = controller;

  try {
    const response = await fetch(`/api/channels/${id}/messages`, {
      signal: controller.signal,
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const messages = await response.json();

    if (activeChannel !== id) return;      // 迟到的旧频道，不碰界面
    render(messages);
  } catch (err) {
    if (err.name === 'AbortError') return; // 自己取消的，不当成错误
    if (activeChannel !== id) return;      // 旧频道的失败也别提示
    showError(`加载失败：${err.message}`);
  }
}
```

两个防线各管一件事。

`controller.abort()` 让**旧请求尽早停下**。它在发请求前就把上一路的 controller 取消掉，A 的 `fetch` 会以 `AbortError` 拒绝，后面的解析和渲染都不再发生。

`if (activeChannel !== id) return;` 保证**结果属于当前频道才允许上屏**。abort 有覆盖不到的情况：A 的响应可能已经完整到达，甚至 `res.json()` 也已经完成，只是 `await` 后面的代码还没轮到；这时 abort 拦不住一个已经落定的结果。也可能别的代码路径发的请求根本没接 signal。标识检查是兜底的一道闸，和取消机制是否生效无关。

没有这两道防线，只靠“后到的响应就是最新的”这种直觉，迟早会串数据。另一种等价写法是给每次请求编号，回来时比对编号；项目 id、查询条件、URL 都能当这个标识。

## AbortController 停掉的是等待，不是服务器 {#abort-controller}

`AbortController` 只有一个有用的属性 `signal` 和一个方法 `abort()`。把 `signal` 交给 `fetch`，`abort()` 一调用，这个请求就像被本地掐断：Promise 以 `AbortError` 拒绝（`err.name` 是 `'AbortError'`），后续的 `then` 不再执行。

```js
const controller = new AbortController();
controller.abort();        // 信号先置为已取消，请求不会发出去

fetch('https://jsonplaceholder.typicode.com/comments?postId=1', {
  signal: controller.signal,
}).catch(err => console.log(err.name));   // AbortError
```

```
AbortError
```

平时是请求发出后再调 `abort()`，效果一样：Promise 以 `AbortError` 拒绝。在 `abort()` 之前请求已经完成，就什么也不会发生；取消不会倒转已经做完的事。`signal.aborted` 可以直接查当前是否已取消。

取消是客户端的动作。请求可能早已到达服务器，服务器也可能已经把数据写进数据库——你只是不等结果了。**读取**请求取消掉通常没什么后果；**创建、付款、保存**这类写操作，取消不等于撤销。要防重复，得靠幂等键或服务端状态查询，而不是指望 `abort()`。

整页卸载时也要清理：`window.addEventListener('beforeunload', () => controller.abort())` 之类的收尾，或者把取消放进组件的清理函数。否则旧页面还在后台等结果，回来时操作已经不存在的节点。

超时也可以用同一个机制。现代浏览器支持 `AbortSignal.timeout(5000)`：

```js
async function loadWithTimeout() {
  const response = await fetch('/api/messages', {
    signal: AbortSignal.timeout(5000),
  });
  return response.json();
}
```

五秒没完成就拒绝，`err.name` 是 `'TimeoutError'`。注意它限制的是整个请求，包括读正文；如果正文是流式输出，整体超时可能把正常的慢响应也砍掉。

流式接口要边读边处理。`await res.text()` 会等整个正文到齐再一次性交出字符串，这适合小响应，不适合“来一段显示一段”。流式读取用 `res.body.getReader()` 一段段读，或者用支持异步迭代的 `for await (const chunk of res.body)`。

## 404 不抛错，重试也可能重付一次款 {#pitfalls}

**“`fetch` 遇到 404 或 500 会进 `catch`。”** 不会。只有网络层失败或请求被取消才拒绝。状态码是响应的一部分，要自己查 `res.ok` 或 `res.status`。

**“进了 `catch` 就说明服务器没收到请求。”** 不一定。请求可能到了服务器、处理完了，响应在回来的路上断了，客户端看到的也是网络错误。写操作尤其不能据此断定“没保存”。

**“调用 `abort()` 等于撤销服务器上的操作。”** 客户端停止等待而已。付款请求取消后，钱可能已经扣了。

**“失败了就重试，反正重试没有代价。”** 对查询通常没代价；对创建订单、扣款、发消息，重试可能产生第二条记录或第二次扣款。重试前先问：这个操作重复执行一次，结果一样吗？

## 什么请求可以放心重试 {#retry}

判断标准是幂等：同样的请求执行一次和执行两次，服务端状态是否相同。`GET` 查询、按 id 改成一个固定值的 `PUT`、带幂等键的创建，通常可以重试。普通的 `POST` 创建和支付不行。

通常值得重试的是这几类：网络层失败、5xx、429（被限流）。4xx 里的参数错误重试多少次都一样，除了 408 和 429 这种明确表示“现在不行、等会儿再来”的。

重试要有限度：最多几次、间隔递增（指数退避）、加一点随机抖动避免所有客户端同时重发。服务器给了 `Retry-After` 就按它等。写操作要么带幂等键，要么在失败后先查一次服务端状态，再决定要不要重发。

错误提示也分层。网络失败可以提示“检查网络后重试”；HTTP 401 该跳登录；404 该说资源不存在；业务错误直接把后端给的安全文案显示出来。把整段响应、请求头、token 原样打进日志或页面，是在给自己制造泄露事故。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：`fetch` 返回 500，`.catch` 会执行吗？应该怎么判断？

> **答案**
>
> 不会。`fetch` 只在没拿到响应时拒绝。500 是一个正常到达的响应，状态码在 `res.status`，`res.ok` 为 `false`。
>
> ```js
> async function getMessages() {
>   const res = await fetch('/api/messages');
>   if (!res.ok) throw new Error(`HTTP ${res.status}`);
>   return res.json();
> }
> ```
>
> 想让 500 走 `catch`，就自己抛。

**第 2 题**：用户快速从频道 A 切到频道 B，A 的响应最晚才回来。写出两种防止旧数据上屏的办法。

> **答案**
>
> 一是取消：切换时 `controller.abort()`，A 的请求以 `AbortError` 结束。
>
> 二是校验归属：记录当前频道 id，响应回来后比较 `if (activeChannel !== id) return;`，不属于当前频道就不渲染。
>
> 两个一起用。取消省资源，校验兜底——取消有覆盖不到的时间窗。

**第 3 题**：用户在保存留言时点了取消，为什么不能认为服务器没保存？

> **答案**
>
> `abort()` 只让浏览器停止等待结果，请求可能已经到达服务器并执行完。服务器不会因为你取消了等待就回滚。
>
> 写操作要用幂等键保证重复提交只生效一次，或者在失败后查询服务端状态再决定是否重发。

## 继续阅读 {#related}

- [HTTP 请求与响应](/learn/web-http)
- [Promise 与 async/await](/learn/js-async)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)
- [Effect、依赖与清理](/learn/react-effects)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
