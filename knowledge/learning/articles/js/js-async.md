# Promise 与 async/await

## 先建立直觉 {#overview}

异步让程序在等待网络或其他操作时可以继续处理别的工作。Promise 表示一个未来可能成功或失败的结果，async/await 提供更接近顺序代码的写法。等待并不等于开一个新线程，也不保证多个请求会自动同时完成。

## 原理与执行过程 {#mechanism}

Promise 有待定、兑现和拒绝等状态。async 函数返回 Promise；await 暂停当前 async 函数后续部分，等结果可用时再恢复。异常可以通过 try/catch 处理。两个 await 顺序写通常形成串行依赖；独立任务可先启动再等待，但要明确失败和取消策略。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```javascript
async function loadTitle() {
  const response = await fetch('/api/title');
  if (!response.ok) throw new Error('读取失败');
  const data = await response.json();
  return data.title;
}
loadTitle().then(title => console.log(title)).catch(console.error);
```

## 一步一步读懂 {#walkthrough}

调用 loadTitle 立即得到一个 Promise。函数在网络请求处等待，响应到达后再检查状态并解析 JSON。return data.title 让外层 Promise 兑现为标题。最后 then 使用结果，catch 处理拒绝。没有等待或处理这个 Promise，调用方可能提前继续执行。

## 常见误解 {#pitfalls}

await 不会自动检查 HTTP 状态。Promise.all 的一个失败会使整体拒绝，但其他任务不一定已经停止。超时包装也不一定取消底层请求。异步结果返回时界面可能已切换项目，更新状态前必须检查它是否仍属于当前请求。

## 工程中的取舍 {#tradeoffs}

并行能缩短独立任务的总等待时间，却可能增加服务器压力。串行更容易表达依赖和事务边界。重要交互需要加载、失败、取消和陈旧结果处理，而不只是给函数加 async。

## 接着探索 {#related}

- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [HTTP 请求与响应](/learn/web-http)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [事件循环、任务与微任务](/learn/js-events-loop)
- [异步编程：等待期间让出执行机会](/learn/async)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
