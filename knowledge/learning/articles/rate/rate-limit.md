# 限流：保护有限处理能力

## 先建立直觉 {#overview}

限流控制一段时间内允许多少请求或工作进入系统，避免资源耗尽。它与并发上限有关但不同：每秒十次请求和同时十个任务约束的是不同维度。合理限流还需要明确按用户、接口、项目还是全局计数。

## 原理与执行过程 {#mechanism}

固定窗口实现简单，但窗口边界可能集中放行；滑动窗口更平滑，令牌桶允许受控突发。分布式服务需要共享计数或接受局部误差。拒绝请求时应有稳定状态与重试建议，但不能保证客户端都会遵守。

## 跟着例子理解 {#example}

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
Content-Type: application/json

{"error": {"code": "rate_limited", "title": "请稍后重试"}}
```

## 一步一步读懂 {#walkthrough}

429 表示服务器基于限流规则拒绝本次请求。Retry-After 提供示例等待建议。客户端可以提示并延后可重试操作，但不能立即无限重试。服务端还需要明确这个规则覆盖哪类主体，防止不同用户互相挤占或绕过。

## 常见误解 {#pitfalls}

限流不是权限验证，也不自动防止所有拒绝服务攻击。只在单个进程计数，多个进程可能合起来超过全局限制。把队列无限延长只是推迟过载，仍可能耗尽内存和用户等待时间。

## 工程中的取舍 {#tradeoffs}

更严格限制保护容量，却可能拒绝正常突发。排队、降级与拒绝适合不同工作。应监测拒绝比例、等待时间和下游容量；具体数值需要依据实际负载，不应由概念检测器凭代码名字判断合理性。

## 接着探索 {#related}

- [线程池：受控执行阻塞工作](/learn/thread-pool)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 来源与版本 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
