# 为 React props 与事件声明类型

## 先建立直觉 {#overview}

TypeScript 可以描述 React 组件接收的 props、事件和状态，让组件使用方式更清楚。一个按钮需要的标题与回调可以直接写在接口中，调用方漏传或传错类型时就能在构建阶段发现。

## 原理与执行过程 {#mechanism}

TSX 支持带类型的 JSX。组件函数接收 props，回调类型说明谁负责触发动作。状态可以由初始值推断，也可以显式声明联合类型。React 事件类型与浏览器原生事件不完全相同，应依据实际 API 使用，不靠 any 统一绕过。

## 跟着例子理解 {#example}

```tsx
type LearnButtonProps = {
  title: string;
  onOpen: () => void;
};
function LearnButton({ title, onOpen }: LearnButtonProps) {
  return <button type="button" onClick={onOpen}>{title}</button>;
}
```

## 一步一步读懂 {#walkthrough}

props 明确要求字符串标题和无参数回调。组件把回调交给 onClick，点击时才触发。若写 onClick={onOpen()}，就会在渲染时调用并传入返回值，行为不同。类型检查有助于发现这类错误，但仍需确认回调触发的是正确业务目标。

## 常见误解 {#pitfalls}

组件类型正确不能证明返回的链接有效。外部 API 数据仍需校验。为了省事把事件或 ref 都写成 any，会失去访问属性时的帮助。类型与 React 版本应匹配，旧教程可能使用不同的类型习惯。

## 工程中的取舍 {#tradeoffs}

组件接口应尽量小而明确。把完整 store 或巨大对象传给所有子组件，容易扩大耦合；只传需要的字段和动作更容易复用与测试。通用组件可以使用泛型，但不要让类型设计比组件职责更难理解。

## 接着探索 {#related}

- [interface、type 与结构契约](/learn/ts-interfaces)
- [Props：组件之间怎样传数据](/learn/react-props)
- [事件处理与受控输入](/learn/react-events)

## 来源与版本 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
