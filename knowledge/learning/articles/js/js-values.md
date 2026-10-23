# JavaScript 的变量与值

## 先建立直觉 {#overview}

JavaScript 用变量保存对值的引用。let 允许重新赋值，const 限制名字重新绑定，但不会自动冻结它指向的对象。读前端状态时，要区分给变量换一个对象与修改原对象的属性，这会影响状态更新是否被观察到。

## 原理与执行过程 {#mechanism}

字符串、数字、布尔、null、undefined 等原始值与对象的行为不同。对象赋值会共享引用。严格相等 === 避免许多隐式类型转换；null 常表达明确的空值，undefined 常表达尚未提供的值。数字主要采用双精度浮点，金额等精确业务数据需要额外规则。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```javascript
const original = { count: 1 };
const alias = original;
alias.count = 2;
const copy = { ...original, count: 3 };
console.log(original.count); // 2
console.log(copy.count);     // 3
```

## 一步一步读懂 {#walkthrough}

alias 与 original 指向同一对象，修改 count 会互相可见。展开语法创建了新的外层对象，copy 的 count 是 3。const 并没有阻止 alias.count=2；它只是阻止把 alias 重新赋为另一个对象。嵌套对象仍可能共享，所以这里不是深复制。

## 常见误解 {#pitfalls}

不要因为 const 就假定对象不可变。使用 == 可能触发不直观的转换。空数组和空对象在条件判断中都是真值，与一些其他语言不同。JSON 序列化也不能保留所有 JavaScript 值。

## 工程中的取舍 {#tradeoffs}

优先使用 const 表达不重新绑定的意图，需要变化时再用 let。不可变更新更便于追踪状态，但频繁复制大结构有成本。把状态变更集中在明确入口，比随处共享修改对象更容易调试。

## 接着探索 {#related}

- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [对象、数组与不可变更新](/learn/js-objects)
- [State、重新渲染与状态快照](/learn/react-state)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
