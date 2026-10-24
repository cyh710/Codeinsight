# HTTP 请求与响应

## 先建立直觉 {#overview}

HTTP 是客户端与服务器交换消息的一套规则。请求描述想做什么，响应说明处理结果并携带数据。方法、地址、状态码、头部和正文各有职责；它们共同构成接口约定，不能只看一个 JSON 字段就认定调用成功。

## 原理与执行过程 {#mechanism}

GET 通常用于读取资源，POST 常用于提交处理。成功与否先看约定的状态码，再解析匹配内容类型的正文。网络传输成功不代表业务一定成功，HTTP 200 也不能弥补返回体违反契约。流式响应分批到达，客户端需要区分完整消息、暂时没有新数据和连接结束。

## 跟着例子理解 {#example}

```http
GET /messages?limit=2 HTTP/1.1
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{"items": [{"text": "你好"}], "total": 1}
```

## 一步一步读懂 {#walkthrough}

请求路径指定资源，查询参数 limit 指定数量。Accept 表明期望格式；响应 Content-Type 声明实际格式。total 是接口定义的总数，不一定等于当前页条目数。这个文本把请求和响应放在一起展示，真实网络中它们来自不同方向。

## 常见误解 {#pitfalls}

超时不一定表示服务器没有完成操作，因此重试写请求需要考虑幂等。401 与 403 含义不同；404 也可能是前缀或路由错误。浏览器 fetch 遇到 404 通常仍会得到响应对象，不会因为状态码自动抛网络异常。

## 工程中的取舍 {#tradeoffs}

稳定的错误结构让前端可以给出明确下一步。缓存可减少重复读取，但需要确定过期与权限边界。接口设计应区分同步完成和异步受理；返回任务 ID 后，后续状态必须有可查询或可订阅的来源。

## 接着探索 {#related}

- [浏览器、前端与后端](/learn/web-client-server)
- [URL、JSON 与 API 契约](/learn/web-api)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 来源与版本 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
