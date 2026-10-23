# Session：把多次请求关联为会话

## 先建立直觉 {#overview}

HTTP 请求本身不会自动记住上一次是谁访问。会话机制通过一个标识，把多次请求关联到同一份登录或交互状态。常见做法是浏览器保存 Cookie，服务器根据其中的会话 ID 查找状态，也有把签名状态保存在客户端的方案。

## 原理与执行过程 {#mechanism}

登录后建立会话，后续请求携带标识，服务器读取并验证，再查找对应用户和权限。会话标识应难以猜测并能失效。Cookie 的 Secure、HttpOnly 与 SameSite 等属性分别控制传输、脚本读取和跨站携带行为，不能互相替代。不同框架的 session 可能存服务端，也可能使用签名 Cookie，需要读取实现而不是只看名称。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```http
HTTP/1.1 200 OK
Set-Cookie: session_id=example-random-id; HttpOnly; Secure; SameSite=Lax

GET /profile HTTP/1.1
Cookie: session_id=example-random-id
```

## 一步一步读懂 {#walkthrough}

第一段由服务器设置 Cookie，浏览器在符合条件的后续请求中携带它。session_id 只是演示值，不提供真实安全性。服务器还需要验证标识、检查过期并找到用户。对话的 conversation_id 则可能只是业务分组，不能见到“会话”二字就认定它承担认证。

## 常见误解 {#pitfalls}

HttpOnly 不阻止所有跨站请求问题。关闭标签页不一定使服务端会话失效。把用户 ID 直接当会话凭证容易被冒用。Session 在数据库 ORM 中还可能指另一类对象，检测时必须消歧。

## 工程中的取舍 {#tradeoffs}

服务端状态便于撤销与集中管理，却需要存储和清理。客户端签名状态减少查询，但载荷大小、泄露内容和撤销方式需要权衡。认证状态与聊天上下文应有不同的生命周期和权限检查。

## 接着探索 {#related}

- [JWT：可验证的令牌](/learn/jwt)
- [HTTP 请求与响应](/learn/web-http)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
- [FastAPI：依赖注入与安全](https://fastapi.tiangolo.com/tutorial/dependencies/)；作者：Sebastián Ramírez and contributors；MIT。版本：导入日网页快照; sha256:ae1f492784c1ccdc3f7f85f358c3f217f710fc4993ea3759561509601a131d04。
