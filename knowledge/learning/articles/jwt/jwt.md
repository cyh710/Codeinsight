# JWT：可验证的令牌

## 先建立直觉 {#overview}

JWT 是一种承载声明的令牌格式，常用于让接收方验证某些信息来自可信签发者。常见的签名形式包含头部、载荷和签名。它不是密码保险箱，载荷通常只是编码而非加密，拿到令牌的人可能读出里面的信息。

## 原理与执行过程 {#mechanism}

签发方把用户标识、有效期等声明放进载荷，并使用约定算法签名。验证方检查签名、算法以及有效期、受众、签发者等约束后，才依据声明执行权限逻辑。签名验证只说明完整性和来源满足条件，不自动证明当前操作被授权。密钥轮换、撤销和泄露响应都需要额外设计。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
import jwt
token = jwt.encode({"sub": "user-7", "exp": 2000000000}, "教学密钥", algorithm="HS256")
claims = jwt.decode(token, "教学密钥", algorithms=["HS256"])
print(claims["sub"])
```

## 一步一步读懂 {#walkthrough}

encode 生成令牌，decode 在指定算法白名单下验证并解析。sub 表达主体，exp 表达失效时间。教学密钥不能用于真实服务；实际还应配置受众、签发者和安全的密钥管理。项目里出现 jwt 导入只证明它依赖相关库，还要追到实际签发与验证路径。

## 常见误解 {#pitfalls}

Base64URL 编码不是加密。不能相信未验证的载荷，也不能让令牌任意决定服务端接受的算法。JWT 不天然解决退出登录或即时撤销。日志记录完整令牌可能等于泄露凭证。

## 工程中的取舍 {#tradeoffs}

无状态验证便于多服务共享，但令牌失窃和即时撤销更难处理。短有效期减少暴露窗口，却需要刷新策略。小型本地应用可能更适合服务器会话，不能因为 JWT 常见就默认它最好。

## 接着探索 {#related}

- [Session：把多次请求关联为会话](/learn/session)
- [HTTP 请求与响应](/learn/web-http)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [PyJWT usage](https://pyjwt.readthedocs.io/en/stable/usage.html)；作者：José Padilla and contributors；MIT。版本：导入日网页快照; sha256:edebd01dea5f19fa1018568d872a3e8927feb72370d1d7909e29b2b8871bd5a8。
- [FastAPI：依赖注入与安全](https://fastapi.tiangolo.com/tutorial/dependencies/)；作者：Sebastián Ramírez and contributors；MIT。版本：导入日网页快照; sha256:ae1f492784c1ccdc3f7f85f358c3f217f710fc4993ea3759561509601a131d04。
