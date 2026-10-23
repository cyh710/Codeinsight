# HTML：页面的结构与语义

## 先建立直觉 {#overview}

HTML 描述网页中有哪些内容以及它们的结构，例如标题、段落、按钮和表单。标签不是单纯的外观标记：button 表达可操作按钮，h1 表达主要标题。清楚的语义让浏览器、键盘用户和辅助技术都更容易理解页面。

## 原理与执行过程 {#mechanism}

浏览器解析 HTML 后建立 DOM 树。元素可以包含属性和子节点，嵌套关系决定内容结构。CSS 负责样式，JavaScript 负责行为，但两者都建立在元素结构之上。可交互元素应有可访问名称，输入框通常需要对应 label。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```html
<main>
  <h1>消息查询</h1>
  <form>
    <label for="query">关键词</label>
    <input id="query" name="query" />
    <button type="submit">查询</button>
  </form>
</main>
```

## 一步一步读懂 {#walkthrough}

main 标记主要内容。h1 说明页面主题。label 的 for 与 input 的 id 对应，点击标签也能定位输入框。button 明确声明提交行为；如果它只是展开知识面板，应选择 type=button 并添加对应事件逻辑。这个例子只提供结构，不代表已经实现查询。

## 常见误解 {#pitfalls}

用 div 模拟按钮会失去默认键盘与语义行为，除非补上相应支持。HTML 属性并不总与 JSX 属性同名。页面里的 id 应避免重复。把不可信字符串当作 HTML 插入，可能把原本的数据变成可执行内容，正常文本应采用转义后的渲染方式。

## 工程中的取舍 {#tradeoffs}

优先使用原生语义元素，可以减少自制交互需要维护的行为。过多包装层会增加 DOM 和样式复杂度。阅读前端组件时，应先看结构和可操作元素，再追事件处理函数，这比从所有 CSS 类名开始更容易理解用户流程。

## 接着探索 {#related}

- [浏览器、前端与后端](/learn/web-client-server)
- [CSS 选择器、层叠与盒模型](/learn/web-css)
- [DOM 与事件：点击怎样变成行为](/learn/js-dom)
- [React 组件与 JSX](/learn/react-components)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
