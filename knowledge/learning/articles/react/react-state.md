# State、重新渲染与状态快照

## 先建立直觉 {#overview}

State 保存影响界面的记忆，例如当前选中的章节。调用状态更新函数会请求新的渲染；当前事件处理函数仍然读取本次渲染时的状态快照。理解这个时间关系，可以解释为什么 setState 后马上打印仍可能看到旧值。

## 原理与执行过程 {#mechanism}

组件每次渲染都会得到对应的 props 与 state，并创建本次使用的事件处理函数。React 可以批处理更新。新状态依赖旧状态时，函数式更新能表达按顺序计算，而不依赖闭包里固定的快照。对象状态应按约定创建新值，避免原地改动导致身份不变。

## 跟着例子理解 {#example}

```jsx
import { useState } from 'react';

export default function Counter() {
  const [count, setCount] = useState(0);
  function addTwo() {
    setCount(value => value + 1);
    setCount(value => value + 1);
  }
  return <button onClick={addTwo}>计数：{count}</button>;
}
```

## 一步一步读懂 {#walkthrough}

两次更新分别接收队列中的前一个结果，因此点击后增加 2。若两次都写 setCount(count+1)，它们可能都基于同一个 count 快照。状态更新不是普通变量赋值；真正显示还要等 React 处理渲染与提交。

## 常见误解 {#pitfalls}

不要直接给 state 对象添加属性来期待更新。异步请求返回时回调可能持有旧项目 ID，需要验证结果归属。可以从其他状态计算出的数据通常不必再存一份，否则容易出现两份数据不同步。

## 工程中的取舍 {#tradeoffs}

局部状态适合只影响一个区域的记忆；跨区域同步则需要提升或共享。频繁变化的大对象可能增加渲染成本，但先确保数据流正确，再根据测量优化。用户操作、请求状态和服务端事实应有清楚的对应关系。

## 接着探索 {#related}

- [Props：组件之间怎样传数据](/learn/react-props)
- [对象、数组与不可变更新](/learn/js-objects)
- [事件处理与受控输入](/learn/react-events)
- [状态提升与 Context](/learn/react-lifting)
- [事件循环、任务与微任务](/learn/js-events-loop)

## 来源与版本 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
