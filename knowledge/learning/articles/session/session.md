# Session：把多次请求关联为会话

## 登录之后又变成游客 {#guest-problem}

读完这一篇，你能说清 Cookie、session_id 和服务端会话如何配合，知道退出登录为什么立刻生效，以及什么时候该用会话而不是 JWT。

小林登录了留言板。页面刷新一下，又回到登录页。

密码没错。错的是 HTTP：它不记得上一封信里发生过什么。每个请求到了服务器，都像一个新访客。

有人会说：浏览器不是会带 Cookie 吗？会。可 Cookie 本身只是一张写着编号的便条，它不解释编号是谁。要服务器先存过"这个编号对应小林"，编号才有意义。

会话做的就是这件事：登录后服务器生成一个编号，把用户状态存在自己这边；浏览器只保存编号，之后每次请求自动带上。

## 浏览器自动带上的一张便条 {#cookie-note}

下面用一个字典当服务器、一个变量当浏览器，跑一遍完整流程。只用了标准库，新建 `session_demo.py`：

```python
from datetime import datetime, timedelta, timezone

SESSIONS = {}
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def login(_cookie, user, password):
    if (user, password) != ("小林", "demo-password"):
        return 401, "用户名或密码不对", None
    sid = "demo-session-0001"  # 真实服务要用 secrets.token_urlsafe(32)
    SESSIONS[sid] = {"user": user, "expires_at": NOW + timedelta(hours=1)}
    return 200, "登录成功", f"session_id={sid}; HttpOnly; SameSite=Lax"


def profile(cookie):
    print("请求带的 Cookie:", cookie or "(无)")
    sid = cookie.removeprefix("session_id=") if cookie.startswith("session_id=") else ""
    data = SESSIONS.get(sid)
    if data is None or data["expires_at"] <= NOW:
        return 401, "请先登录", None
    return 200, f"你好，{data['user']}", None


def logout(cookie):
    sid = cookie.removeprefix("session_id=") if cookie.startswith("session_id=") else ""
    SESSIONS.pop(sid, None)
    return 200, "已退出", "session_id=; Max-Age=0; HttpOnly"


def send(cookie, action, **kwargs):
    status, body, set_cookie = action(cookie, **kwargs)
    if set_cookie:
        print("Set-Cookie:", set_cookie)
        cookie = "" if "Max-Age=0" in set_cookie else set_cookie.split(";")[0]
    print(status, body)
    return cookie


browser = ""
browser = send(browser, login, user="小林", password="demo-password")
browser = send(browser, profile)
browser = send(browser, logout)
browser = send(browser, profile)
send("", profile)
```

运行：

```bash
python session_demo.py
```

你应该看到：

```
Set-Cookie: session_id=demo-session-0001; HttpOnly; SameSite=Lax
200 登录成功
请求带的 Cookie: session_id=demo-session-0001
200 你好，小林
Set-Cookie: session_id=; Max-Age=0; HttpOnly
200 已退出
请求带的 Cookie: (无)
401 请先登录
请求带的 Cookie: (无)
401 请先登录
```

换成真实的 HTTP 报文，方向更清楚：

```http
HTTP/1.1 200 OK
Set-Cookie: session_id=demo-session-0001; HttpOnly; SameSite=Lax

GET /profile HTTP/1.1
Cookie: session_id=demo-session-0001
```

`Set-Cookie` 是服务器对浏览器说"存下这个"；`Cookie` 是浏览器后来对服务器说"这是我存的"。名字像，方向相反。

例子里的 `send` 函数扮演浏览器：它把上一条响应的 Cookie 存进 `browser` 变量，下一次请求再自动拼进头部。真实浏览器按域名、路径和过期时间管理这些键值，你不用在 JavaScript 里手动加。

例子把"现在"固定在 2026-01-01 12:00，所以每次运行结果一样；真实代码应该用 `datetime.now(timezone.utc)` 取当前时间。`send` 会把当前 Cookie 作为第一个参数传给每个动作，登录用不到它，所以 `login` 的参数名写成 `_cookie`。

## 服务端拿 session_id 查什么 {#server-lookup}

**登录时，服务器先验密码，再发编号。** 代码里的账号密码写死成 `("小林", "demo-password")`，只为了演示。真实系统存的是密码哈希，不会存明文。

登录成功后，服务器生成一个 `sid`，把用户和过期时间写进 `SESSIONS`。这个字典就是服务端的会话表。例子用固定的 `demo-session-0001`，是为了让每次运行的输出一致；真实服务必须用 `secrets.token_urlsafe(32)` 这类不可猜的随机值。

**编号不能从用户信息推导。** 如果你把 `session_id` 设成 `user-7` 或邮箱的哈希，攻击者拿到一个合法编号后，很容易猜出别人的。编号和用户之间只能靠服务端的表建立关系。

**浏览器只拿到编号。** 响应的 `Set-Cookie` 里只有 `session_id=demo-session-0001`，用户名和权限都没有下发。这正是会话和 JWT 的一个根本区别：状态留在服务器，客户端只拿指针。

**下一次请求，服务器拿编号查表。** `profile` 从 `Cookie` 头里切出 `session_id`，去 `SESSIONS` 取记录。取不到，或者 `expires_at` 已经过去，就返回 401。取到了，才把 `user` 填进响应。

**退出登录，删掉那一行。** `logout` 执行 `SESSIONS.pop(sid)`，同时让浏览器把 Cookie 过期掉。下一次请求再带同一个编号，表里已经没有了，所以立刻是 401。不是等令牌自然过期，也不是靠前端把页面藏起来。

这里还有一个容易漏的细节：登录成功后要换一个新编号。如果攻击者提前让受害者浏览器用一个他知道的编号登录，而服务器沿用这个编号，攻击者就能接着用。登录成功时丢弃旧会话、签发新编号，能挡住这种会话固定攻击。

## 三个 Cookie 属性各挡什么 {#cookie-flags}

`Set-Cookie` 后面可以跟一串属性。它们各管一段，不能互相替代。

| 属性 | 写上之后 | 挡不住 |
|---|---|---|
| `HttpOnly` | 页面脚本读不到这个 Cookie | XSS 仍能用你的身份发请求 |
| `Secure` | 只在 HTTPS 请求里发送 | XSS、CSRF |
| `SameSite=Lax` | 跨站的 POST 默认不带；顶层 GET 导航会带 | 同站请求、XSS |
| `SameSite=Strict` | 跨站请求一律不带 | 同站请求、XSS |

`HttpOnly` 防的是"脚本把编号读走"。它不防 XSS 本身：脚本虽然读不到 Cookie，仍可以让浏览器带着 Cookie 去调接口。

`SameSite` 防的是"另一个网站借你的 Cookie 发请求"，也就是 CSRF。`Lax` 是常用的折中：从别的站点点链接跳过来（顶层 GET）会带上，跨站表单 POST 不带。写操作最好再加 CSRF token 或校验 `Origin`，不要只靠一个属性。

`Secure` 只在 HTTPS 下有意义。开发环境如果用普通 HTTP，带 `Secure` 的 Cookie 可能根本存不下来，表现就是"登录了但下次还是游客"。部署时必须有 HTTPS。

Cookie 还有 `Domain` 和 `Path`。`Domain` 写宽了，子域都能收到；`Path` 写宽了，不相关接口也会带上。按最小范围设置。

## 会话会过期，也会续期 {#expiry-renewal}

服务端存的 `expires_at` 才是真正的过期时间。Cookie 上的 `Max-Age` 只是浏览器本地副本的寿命，客户端可以删、可以改、可以恢复，不能拿它当安全判断。

常见的是两层超时：

- 空闲超时：30 分钟没请求就失效，适合后台系统。
- 绝对超时：登录后最多 12 小时，到点必须重新登录，适合敏感系统。

空闲超时可以在每次请求时把 `expires_at` 往后推，这叫滑动续期。它让活跃用户不用反复登录，但也会让一个被盗的会话一直续下去。稳妥的做法是滑动续期加一个绝对上限：活跃就续，但登录满 12 小时一律失效。

过期记录要清理。内存字典不会自己删键，跑久了会一直涨；Redis 可以靠 TTL 自动删；数据库会话表需要定期删除过期行。清理是运维问题，但漏掉会变成内存或磁盘问题。

关掉标签页不等于退出登录。如果 Cookie 是"会话 Cookie"（没设 `Max-Age`），浏览器通常会在关闭时丢掉它，但浏览器恢复会话时也可能带回来。服务端的 `SESSIONS` 记录更不会因为标签页关闭而消失。共用电脑上，正确的动作是点退出，让服务端删记录。

用户有多台设备时，每台设备一个 `sid`，互不影响。要"退出所有设备"，就删掉该用户的所有会话记录；要封号，也是同一类操作。

## 五个关于登录态的错觉 {#session-misconceptions}

**"Session 就是 Cookie。"** Cookie 是运输工具，会话状态在服务端。JWT 也可以放在 Cookie 里；Cookie 里也可以只放一个会话编号。看到 Cookie 不等于看到会话，看到会话也不一定用 Cookie 传。

**"设了 HttpOnly 就安全了。"** 它只挡住脚本读取。XSS 仍然可以替用户发请求，CSRF 也不会因为 `HttpOnly` 消失。还要做输出转义、CSP、`SameSite` 和 CSRF 校验。

**"关掉标签页就退出了。"** 服务端记录还在，直到过期或被删。浏览器是否保留 Cookie 取决于它是不是会话 Cookie、有没有开启恢复会话。别把关闭页面当成安全操作。

**"把 user_id 当 session_id 更省事。"** 编号一旦可预测，攻击者就能枚举和冒用。会话编号必须随机、足够长、只存在服务端，登录后轮换。省下的那点查表成本，换来的是一整类越权漏洞。

**"代码里所有 session 都是登录态。"** 有些框架叫 session，实际把签名后的状态放在 Cookie 里，状态在客户端；有些则存在服务端表里。名字一样，机制和撤销方式完全不同。ORM 里的 session 是数据库工作单元，聊天里的 `conversation_id` 是业务分组，分析工具里的 session 是访问片段。它们可能和认证毫无关系，生命周期和权限检查也不该复用登录态那一套。读实现，别只看名字。

## 和 JWT 怎么选 {#session-vs-jwt}

| | 服务端会话 | JWT |
|---|---|---|
| 每次请求做什么 | 用编号查存储 | 验签、解载荷 |
| 状态放在哪 | 服务端 | 令牌里 |
| 立刻吊销 | 删除记录 | 要加黑名单或版本号 |
| 多服务共享 | 共享 Redis 或数据库 | 共享密钥或公钥 |
| 客户端体积 | Cookie 里只有一个编号 | 所有声明都在令牌里 |
| 泄露之后 | 服务端可以作废 | 到期前一直有效 |
| 适合 | 单体应用、后台、要即时踢人 | 跨服务、短时、外部 API |

查表和验签是两种代价。查表多一次 I/O，但你能随时改表；验签不查表，但改不了已经发出去的东西。

也可以混用：访问令牌用 JWT，活 5 分钟；刷新令牌存在服务端，退出时撤销。这样大多数请求不查表，撤销窗口最多 5 分钟。

判断标准不是"哪个更现代"，而是这几个问题：你能不能接受最长一个有效期的撤销延迟？要不要跨服务验证？会话存储撑不撑得住？如果答案偏向"要立刻踢人、只有一个服务"，会话更省事。

## 练习 {#self-check}

**第 1 题**：Cookie 里只有一个 `session_id`，服务器怎么知道当前用户是谁？

> **答案**
>
> 服务器拿这个编号去自己的会话表里查。例子中是 `SESSIONS[sid]`，查到的那条记录里有 `user` 和 `expires_at`。
>
> 编号本身不含用户信息，也不该能反推出用户。表和编号对不上，或者记录过期，就返回 401。

**第 2 题**：退出登录为什么能立刻生效？换成纯 JWT 为什么做不到？

> **答案**
>
> 因为服务端删掉了 `SESSIONS` 里对应的记录。下一次请求带同一个编号来，查不到，立刻 401。Cookie 过期只是顺手清理客户端副本，真正生效的是服务端状态被删。
>
> 纯 JWT 没有这条记录可删。令牌在 `exp` 之前一直能通过验签，除非额外维护黑名单或用户级版本号。

**第 3 题**：`HttpOnly` 能防 CSRF 吗？

> **答案**
>
> 不能。`HttpOnly` 只阻止页面脚本读取 Cookie，浏览器仍然会在符合条件的请求里自动带上它。别的网站诱导浏览器发一个跨站 POST，Cookie 照样会跟着走。
>
> 防 CSRF 要靠 `SameSite`、CSRF token、校验 `Origin` 或 `Referer`，以及把写操作设计成需要额外凭证。

## 继续阅读 {#related}

- [JWT：可验证的令牌](/learn/jwt)
- [HTTP 请求与响应](/learn/web-http)
- [URL、JSON 与 API 契约](/learn/web-api)
- [限流：保护服务不被请求打穿](/learn/rate-limit)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
- [FastAPI：依赖注入与安全](https://fastapi.tiangolo.com/tutorial/dependencies/)；作者：Sebastián Ramírez and contributors；MIT。版本：导入日网页快照; sha256:ae1f492784c1ccdc3f7f85f358c3f217f710fc4993ea3759561509601a131d04。
