# DOM 与事件：点击怎样变成行为

## 先建立直觉 {#overview}

DOM 是浏览器中的页面对象树，JavaScript 可以读取或修改它。事件把用户动作和程序行为连接起来，例如点击、输入和键盘操作。理解一个按钮，既要看它对应的元素，也要看事件被谁监听以及触发后改变了什么。

## 原理与执行过程 {#mechanism}

事件通常经历捕获、目标和冒泡阶段。event.target 是实际触发节点，currentTarget 是当前处理函数所绑定的节点。默认行为如提交表单，与事件传播是两个不同机制；preventDefault 和 stopPropagation 作用不同。事件监听也需要和组件生命周期一起清理。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```javascript
const button = document.querySelector('#learn');
function openLesson(event) {
  console.log(event.currentTarget.id);
}
button?.addEventListener('click', openLesson);
// 不再使用时：button?.removeEventListener('click', openLesson);
```

## 一步一步读懂 {#walkthrough}

先寻找元素，可能找不到所以用了可选链。addEventListener 注册的是函数引用，而不是立即调用函数。点击后浏览器才传入事件对象。移除监听时需要相同的函数引用；重新写一个外观相同的匿名函数并不等于同一个对象。

## 常见误解 {#pitfalls}

事件处理函数执行不代表异步保存已经完成。清理监听遗漏会导致重复处理或持有旧对象。点击链接导航与切换站内面板应有明确约定，不能让用户同时看到两种跳转结果。键盘和鼠标入口也应表达相同操作。

## 工程中的取舍 {#tradeoffs}

直接操作 DOM 适合小范围原生交互，在 React 中通常应通过状态驱动界面，避免两套机制争夺同一节点。事件委托减少监听数量，但需要正确识别目标和作用范围。先追用户动作，再追状态变化，能更快定位交互问题。

## 接着探索 {#related}

- [HTML：页面的结构与语义](/learn/web-html)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [事件处理与受控输入](/learn/react-events)
- [URL、JSON 与 API 契约](/learn/web-api)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
