# 网络请求、取消与失败处理

## 先建立直觉 {#overview}

fetch 是浏览器发起 HTTP 请求的接口。一次可靠的请求处理需要分别处理网络失败、HTTP 错误、正文解析失败和业务错误。用户切换项目后，旧请求可能晚到；让旧结果覆盖新界面，是异步应用常见的状态问题。

## 原理与执行过程 {#mechanism}

fetch 先返回响应对象，读取正文又是一个异步过程。AbortController 可请求取消支持它的操作。取消、网络异常和 4xx/5xx 响应不是同一种情况，应提供不同处理。即使客户端取消等待，服务器也可能已经完成写入，因此取消不等于撤销。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```javascript
const controller = new AbortController();
const response = await fetch('/api/projects', { signal: controller.signal });
if (!response.ok) throw new Error(`HTTP ${response.status}`);
const projects = await response.json();
// 切换页面时可以调用 controller.abort()；这里不代表撤销服务器写入。
```

## 一步一步读懂 {#walkthrough}

controller 创建取消信号，fetch 接收它。拿到响应后先判断状态，再解析数据。实际组件卸载时应执行清理；若取消发生在请求完成之后，它不会倒转已经发生的处理。对项目切换，还应使用请求标识或项目 ID 防止旧数据串入新项目。

## 常见误解 {#pitfalls}

并不是所有 fetch 抛错都表示服务器没有收到请求。不要无条件重试创建、付款或保存等操作。展示错误时不应直接把完整响应和密钥写进日志。流式响应需要增量解析，不能只在结束时一次读取来冒充流式显示。

## 工程中的取舍 {#tradeoffs}

清楚的客户端错误类型有助于统一提示。首字节超时与流中静默超时解决不同问题。对于可以安全重试的读取，退避与取消可以改善体验；对写操作，先明确幂等性和服务器状态查询。

## 接着探索 {#related}

- [Promise 与 async/await](/learn/js-async)
- [HTTP 请求与响应](/learn/web-http)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)
- [Effect、依赖与清理](/learn/react-effects)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
