# 事件循环、任务与微任务

## 先建立直觉 {#overview}

浏览器通过事件循环协调脚本、事件与渲染。主线程一次执行一段 JavaScript 工作，异步操作完成后再安排后续处理。异步写法可以避免等待时阻塞，但长时间同步计算仍会让页面卡住。

## 原理与执行过程 {#mechanism}

当前任务执行完毕后，运行时会处理微任务队列，之后才有机会继续其他任务和渲染。Promise 回调通常进入微任务，定时器回调进入后续任务。setTimeout 的时间是最早可安排时机，不是精确执行承诺。不同宿主环境的细节也不同，不能把浏览器顺序直接套给所有运行时。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```javascript
console.log('A');
setTimeout(() => console.log('B'), 0);
Promise.resolve().then(() => console.log('C'));
console.log('D');
// 常见浏览器顺序：A D C B
```

## 一步一步读懂 {#walkthrough}

同步代码先输出 A，注册定时器与 Promise 回调后继续输出 D。当前任务结束时处理 Promise 微任务，输出 C，之后定时器任务才输出 B。0 毫秒不意味着立刻中断当前函数。可以把队列画出来逐步推演，而不是记住一个没有条件的顺序口诀。

## 常见误解 {#pitfalls}

大量递归微任务可能一直推迟页面渲染。把计算包进 Promise 并不自动把它移到后台线程。定时器延迟会受到后台标签页和调度影响。性能问题需要观察具体阻塞工作，不能仅凭使用 async 就判断界面流畅。

## 工程中的取舍 {#tradeoffs}

长计算可分片让出执行机会，或考虑 Web Worker；两者都有状态和通信成本。界面更新还要兼顾输入响应、渲染与网络结果。理解事件循环有助于判断“代码已经执行”和“用户已经看到更新”为什么不是同一个时间点。

## 接着探索 {#related}

- [Promise 与 async/await](/learn/js-async)
- [State、重新渲染与状态快照](/learn/react-state)
- [线程池：受控执行阻塞工作](/learn/thread-pool)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
