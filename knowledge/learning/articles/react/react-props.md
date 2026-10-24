# Props：组件之间怎样传数据

## 先建立直觉 {#overview}

Props 是父组件传给子组件的数据与回调。它让同一个组件可以展示不同内容，也把“显示什么”和“用户操作后做什么”连接起来。子组件应把 props 当作只读输入，不直接修改父组件传来的对象。

## 原理与执行过程 {#mechanism}

父组件渲染子组件时计算 props，子组件读取它们描述界面。数据通常向下传递，用户操作通过回调通知拥有状态的一方。children 可以表达嵌套内容。props 与内部 state 职责不同：一个由外部控制，一个由组件或共享状态持有。

## 跟着例子理解 {#example}

```jsx
function TopicLink({ title, onOpen }) {
  return <button onClick={onOpen}>{title}</button>;
}
function Reader() {
  return <TopicLink title="SQL 是什么" onOpen={() => console.log('open SQL')} />;
}
```

## 一步一步读懂 {#walkthrough}

Reader 决定标题与打开动作，TopicLink 只负责按钮表现和触发回调。箭头函数把参数或行为留到点击时执行。以后换成真正的站内导航，不需要让 TopicLink 自己猜项目 ID 或访问全局变量。这样更容易在测试中替换回调，确认用户操作是否发出。

## 常见误解 {#pitfalls}

不要给 props 赋新值来试图更新父界面。把 props 复制进 state 后，如果没有同步规则，外部更新可能不再显示。传入函数时要区分函数引用与调用表达式，避免渲染阶段意外触发操作。

## 工程中的取舍 {#tradeoffs}

明确 props 有助于追踪依赖；很深的逐层传递可以考虑 Context，但不应把所有状态都放进去。选择状态所有者时，应看哪些区域需要共同变化，而不是看哪个文件写起来最方便。

## 接着探索 {#related}

- [React 组件与 JSX](/learn/react-components)
- [状态提升与 Context](/learn/react-lifting)
- [为 React props 与事件声明类型](/learn/ts-react)

## 来源与版本 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
