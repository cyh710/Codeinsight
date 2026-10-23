# 对象、数组与不可变更新

## 先建立直觉 {#overview}

对象适合按名字组织属性，数组适合有顺序的一组元素。界面常把消息、项目和章节保存成对象数组，再转换成视图。读这类代码时，先看每项的数据形状，以及转换是否修改了原数据。

## 原理与执行过程 {#mechanism}

map 把每项映射到新值，filter 按条件保留元素，find 返回第一个满足条件的项。展开语法创建浅层副本。sort、push 等方法会修改原数组，而有些其他方法返回新数组。状态管理往往依赖对象身份变化，因此原地改动可能绕过预期通知。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```javascript
const messages = [{ id: 1, read: false }, { id: 2, read: false }];
const updated = messages.map(message =>
  message.id === 1 ? { ...message, read: true } : message
);
console.log(messages[0].read); // false
console.log(updated[0].read);  // true
```

## 一步一步读懂 {#walkthrough}

map 创建新数组。遇到 id=1 的消息时创建新对象，其他消息继续复用原对象。这样没有修改 messages 中原来的第一项。这个例子既保留了未变部分的引用，也让发生变化的部分具有新身份，适合许多状态更新机制。

## 常见误解 {#pitfalls}

展开对象只复制一层，内部嵌套引用仍可能共享。find 可能返回 undefined，不能马上假设存在属性。forEach 的结果不是变换后的数组。不要把一个不存在的字段默默当作空值继续渲染，否则契约错误可能很晚才暴露。

## 工程中的取舍 {#tradeoffs}

不可变更新使状态变化更清楚，但深层嵌套会让代码繁琐；可以先改善数据结构。对大列表，需在可读性、复制成本与局部更新之间权衡。选择 map 或循环应看是否在表达转换，而不是追求代码行数少。

## 接着探索 {#related}

- [JavaScript 的变量与值](/learn/js-values)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [State、重新渲染与状态快照](/learn/react-state)
- [interface、type 与结构契约](/learn/ts-interfaces)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
