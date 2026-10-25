# JWT：可验证的令牌

## 服务器怎么认出你 {#recognition}

读完这一篇，你能拆开一段 JWT，看清签名在验什么、载荷为什么是明文，以及令牌撤不回来时你要付什么代价。

HTTP 的每个请求都是单独的一封信。你登录过一次，下一次请求到达服务器时，服务器手上没有上一封信的记忆，只能重新问："你是谁？"

浏览器会顺手带上 IP、User-Agent 这些东西，但它们都不证明身份。IP 会变，User-Agent 谁都能改。

常见的解法有两种：服务器记住你（会话），或者你每次带一张服务器签过字的证明（JWT）。这篇讲后一种。

JWT 的全名是 JSON Web Token。它不是一串随机字符，而是三段用点号连起来的文本，每一段都有固定含义。

## 拆开一段令牌 {#token-anatomy}

先装 PyJWT：

```bash
pip install pyjwt
```

新建 `jwt_demo.py`：

```python
import base64
import json
from datetime import datetime, timezone

import jwt

DEMO_KEY = "demo-secret-do-not-use"

token = jwt.encode(
    {
        "sub": "user-7",
        "name": "小林",
        "iat": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        "exp": datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc),
    },
    DEMO_KEY,
    algorithm="HS256",
)

header_b64, payload_b64, signature_b64 = token.split(".")
print("头部段:", header_b64)
print("载荷段:", payload_b64)
print("签名段:", signature_b64[:16] + "...")


def decode_segment(segment):
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8")


print("头部解码:", decode_segment(header_b64))
claims = json.loads(decode_segment(payload_b64))
print("载荷解码:", json.dumps(claims, ensure_ascii=False, sort_keys=True))

checked = jwt.decode(token, DEMO_KEY, algorithms=["HS256"])
print("验签通过:", checked["sub"], checked["name"])

fake_claims = dict(claims, sub="user-8")
fake_payload = base64.urlsafe_b64encode(
    json.dumps(fake_claims, ensure_ascii=False).encode("utf-8")
).decode("ascii").rstrip("=")
fake_token = f"{header_b64}.{fake_payload}.{signature_b64}"
try:
    jwt.decode(fake_token, DEMO_KEY, algorithms=["HS256"])
except jwt.InvalidSignatureError:
    print("改过载荷:", "InvalidSignatureError")

expired = jwt.encode(
    {"sub": "user-7", "exp": datetime(2020, 1, 1, tzinfo=timezone.utc)},
    DEMO_KEY,
    algorithm="HS256",
)
try:
    jwt.decode(expired, DEMO_KEY, algorithms=["HS256"])
except jwt.ExpiredSignatureError:
    print("过期令牌:", "ExpiredSignatureError")
```

运行：

```bash
python jwt_demo.py
```

你应该看到：

```
头部段: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
载荷段: eyJzdWIiOiJ1c2VyLTciLCJuYW1lIjoiXHU1YzBmXHU2Nzk3IiwiaWF0IjoxNzY3MjY4ODAwLCJleHAiOjE4OTM0OTkyMDB9
签名段: Y9sRGAVfBEuskjjN...
头部解码: {"alg":"HS256","typ":"JWT"}
载荷解码: {"exp": 1893499200, "iat": 1767268800, "name": "小林", "sub": "user-7"}
验签通过: user-7 小林
改过载荷: InvalidSignatureError
过期令牌: ExpiredSignatureError
```

前三行是令牌的三个部分：`头部段.载荷段.签名段`。代码把签名段截短了，只打印前 16 个字符，因为这里要看的是结构，不是那串字符本身。

第四行是头部解码：`{"alg":"HS256","typ":"JWT"}`。`alg` 说签名算法，`typ` 说这是 JWT。

第五行是载荷解码。`sub` 是主体（这里是 user-7），`name` 是名字，`iat` 是签发时间，`exp` 是失效时间。PyJWT 生成载荷时默认把非 ASCII 字符写成 Unicode 转义（"小"的码位是 U+5C0F），所以令牌里的原始 JSON 不含汉字；解码打印时又还原了。

第六行说明验签通过，`jwt.decode` 把载荷交还了。末尾两行是故意做的两个失败实验，下一节拆开看。

## 签名挡住的是改动 {#signature-check}

签名不是对整串 token 做的，而是对 `base64(header) + "." + base64(payload)` 这段字节做 HMAC-SHA256，再把结果 Base64URL 编码，接到末尾一段。服务器收到令牌后，用同一把密钥重算一遍；算出来一样，才认为头部和载荷没被动过。

代码里的 `fake_token` 只换了载荷段，签名段原封不动。重算时输入变了，签名对不上，PyJWT 抛出 `InvalidSignatureError`。

这也说明签名保护的是"没被改"，不是"看不见"。改数据的人没有密钥，伪造不出新签名；但读数据的人不需要密钥。

`exp` 是 Unix 时间戳，`jwt.decode` 默认拿当前时间和它比较，超了就抛 `ExpiredSignatureError`。代码里那张过期令牌写的是 2020 年，所以一定会被拒。

`algorithms=["HS256"]` 是白名单。不要让令牌头里的 `alg` 决定服务端用什么算法验证：攻击者可以把头改成 `none` 或换成另一种算法，诱导服务端用错方式验签。验证时由服务端指定可接受的算法，这是必须做的事。

完整的验证顺序大致是：拆三段 → 确认算法在白名单里 → 用密钥重算签名 → 校验 `exp`（以及可选的 `nbf`、`aud`、`iss`）→ 才把载荷当数据用。

调试时可以用 `options={"verify_signature": False}` 看载荷，但那只配叫解码，不配叫认证。

## 载荷是明文，签名只管完整 {#jwt-misconceptions}

**"JWT 是加密的。"** 把第二段做 Base64URL 解码就能看到原文，上面的代码已经做了。Base64 是编码，谁都会解；加密需要密钥才解得开，JWT 默认不做这件事。密码、身份证号、内部密钥都不该进载荷。要保密得用 JWE，或者把敏感数据留在服务端，令牌里只放一个 id。

**"签名通过，就说明这个人有权限。"** 签名只证明这段载荷是持有密钥的人签的、且没被改过。它不证明 user-7 今天还能退款、能看别人的订单。权限要在服务端按 `sub` 查，或者校验载荷里的 `scope`、`role`，还要看资源归属。不校验 `aud`，别的服务签给同一批用户的令牌也可能被你的服务接受。

**"JWT 能像会话一样随时吊销。"** 纯 JWT 的验证不查任何表，所以没有一个地方能写下"这张令牌作废了"。用户点退出，只是浏览器删了本地副本；已经被复制走的那张，在 `exp` 之前照样能用。

**"把令牌打进日志没关系。"** 日志会被收集、转发、给人看。一张还没过期的令牌就是一把钥匙。打印时只留前后几位，不要把 `Authorization` 头和 URL 查询参数原样记下来。

## 令牌发出去，怎么收回 {#revocation}

无状态是 JWT 的优点，也是它的账单。多个服务不用共享会话表，拿到令牌验签就行；代价是每次请求都省掉了查表，也就省掉了"查表发现它被删了"的机会。

要立刻失效，通常有这几种做法：

1. 短有效期加刷新令牌。访问令牌只活 5 到 15 分钟；刷新令牌存在服务端，退出时撤销它。访问令牌靠自然过期，撤销窗口最多一个有效期。
2. 黑名单。把要作废的 `jti` 存进 Redis，过期时间设成令牌剩余寿命；每次请求查一下。这等于把查表又加回来了。
3. 用户级版本号。用户表里存 `token_version`，令牌里也带一份；退出或改密码时把版本加一，验证时比对。还是要查，但可以缓存。
4. 轮换签名密钥。所有旧令牌一起失效，只适合紧急情况，且会让全部用户重新登录。

如果产品要求"管理员封号后下一次请求就必须失败"，纯 JWT 不是最省事的选择，服务端会话更直接。

短有效期也不是免费的。用户要频繁刷新，刷新流程本身要安全；刷新令牌泄露，攻击者可以一直换新的访问令牌。所以刷新令牌要单独存储、可撤销，最好绑定设备或轮换使用。

## 令牌该放在浏览器的哪里 {#storage}

令牌最终要落到某个地方，下一次请求再取出来。浏览器里常见三个位置：

- `localStorage` 或 `sessionStorage`：页面脚本能读能写。任何一处 XSS 执行了 `localStorage.getItem`，令牌就被拿走了。关闭标签页后 `sessionStorage` 会清空，`localStorage` 不会。
- `httpOnly` Cookie：脚本读不到，浏览器会自动带。方便，但自动带也意味着别的网站可以借你的 Cookie 发请求（CSRF），所以还要配 `SameSite` 和写操作的 CSRF 校验。
- JavaScript 内存变量：刷新页面就丢，只适合很短的访问令牌；XSS 仍然能读到。

没有零风险的位置，只有不同的攻击面。服务端渲染的 Web 应用常把令牌放 `HttpOnly; Secure; SameSite=Lax` 的 Cookie 里。纯前后端分离、跨域调 API 时，常用 `Authorization` 请求头携带 `Bearer` 令牌，这时你得接受页面脚本能读到令牌。

不要把令牌放进 URL 查询参数。它会进浏览器历史、代理日志和 `Referer` 头，泄露面比放在头里大得多。

Cookie 的 `Domain` 不要写太宽，`Path` 收紧到需要的接口。生产环境必须用 HTTPS，否则 `Secure` 属性不会生效。

## 什么时候该用会话 {#tradeoffs}

JWT 适合这些场景：多个服务要独立验证令牌、不想共享会话存储；令牌生命周期短；对外提供 API，调用方拿令牌访问；服务要无状态横向扩容。

服务端会话适合另一类场景：要立刻踢人、改权限马上生效；应用不大、只有一个服务；载荷经常变；不想处理密钥分发和撤销。

别因为 JWT 流行就默认它更好。一个小型后台，用服务端会话往往代码更少，出事也更好查。

读项目时，别停在 `import jwt`。追这几处：谁调用 `encode`、密钥从哪来（有没有写死）、`decode` 时算法白名单是什么、`exp` 多长、令牌存在哪、有没有撤销机制。少一项，安全模型就少一块。

## 练习 {#self-check}

**第 1 题**：把载荷里的 `sub` 从 `user-7` 改成 `user-8`，重新做 Base64URL 编码，签名段不动。这段令牌能通过验证吗？

> **答案**
>
> 不能。签名覆盖的是 `头部段.载荷段`，载荷变一个字节，重算出的签名就不同，`jwt.decode` 会抛 `InvalidSignatureError`。
>
> 除非攻击者拿到签名密钥。拿到密钥就等于能签发任意令牌，这也是密钥不能写进前端代码的原因。

**第 2 题**：为什么不能把用户的密码放进 JWT 的载荷？

> **答案**
>
> 因为载荷只是 Base64URL 编码，不是加密。任何拿到令牌的人都能解出第二段，看到密码。
>
> 载荷里应该放 `sub` 这类标识，真正的敏感数据留在服务端，用 `sub` 去查。

**第 3 题**：用户点了"退出登录"，服务端什么都没做，只让浏览器删掉令牌。这张令牌立刻失效了吗？

> **答案**
>
> 没有。纯 JWT 没有服务端状态，删掉浏览器里的副本只是让这台设备不再发送它。已经被复制走的令牌在 `exp` 之前仍然有效。
>
> 要立刻失效，就得加撤销机制：短有效期加可撤销的刷新令牌、`jti` 黑名单，或者用户级版本号。每一种都意味着服务端要多查一次。

## 继续阅读 {#related}

- [Session：把多次请求关联为会话](/learn/session)
- [HTTP 请求与响应](/learn/web-http)
- [URL、JSON 与 API 契约](/learn/web-api)
- [配置与环境变量](/learn/config-env)

## 参考资料 {#sources}

- [PyJWT usage](https://pyjwt.readthedocs.io/en/stable/usage.html)；作者：José Padilla and contributors；MIT。版本：导入日网页快照; sha256:edebd01dea5f19fa1018568d872a3e8927feb72370d1d7909e29b2b8871bd5a8。
- [FastAPI：依赖注入与安全](https://fastapi.tiangolo.com/tutorial/dependencies/)；作者：Sebastián Ramírez and contributors；MIT。版本：导入日网页快照; sha256:ae1f492784c1ccdc3f7f85f358c3f217f710fc4993ea3759561509601a131d04。
