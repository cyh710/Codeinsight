# Hooks 的调用规则与组合

## 先建立直觉 {#overview}

Hooks 让函数组件使用状态、Effect 等 React 能力，自定义 Hook 则把相关逻辑组合起来复用。复用 Hook 逻辑不等于所有调用者自动共享同一份状态；每个调用位置通常有自己的状态实例。

## 原理与执行过程 {#mechanism}

普通 Hooks 应在组件或自定义 Hook 的顶层调用，保持调用顺序稳定，不放进条件、循环或普通回调。自定义 Hook 以 use 开头，内部可以调用其他 Hooks。共享数据需要由共同状态所有者或 store 明确提供，不能只靠把函数提取到一个文件。

## 跟着例子理解 {#example}

```jsx
import { useState } from 'react';

function useQueryText() {
  const [query, setQuery] = useState('');
  return { query, setQuery, clear: () => setQuery('') };
}
export default function SearchBox() {
  const { query, setQuery } = useQueryText();
  return <input value={query} onChange={e => setQuery(e.target.value)} />;
}
```

## 一步一步读懂 {#walkthrough}

useQueryText 组合了输入状态和清空动作。SearchBox 在顶层调用它，之后渲染输入框。两个 SearchBox 分别调用时，不会因为 Hook 来自同一个文件就自动同步输入。若需要共享查询，应把状态提升到共同父组件或明确的共享数据层。

## 常见误解 {#pitfalls}

函数名字以 use 开头不自动获得 React 能力。不要在事件里临时调用 useState。Hook 返回对象每次可能有新身份，依赖比较需要考虑这一点。规则检查帮助发现顺序问题，但不能验证自定义 Hook 的业务语义。

## 工程中的取舍 {#tradeoffs}

提取 Hook 应围绕一个清楚的同步或交互职责，不应只是把杂乱代码藏起来。越通用的 Hook 越需要明确生命周期、取消和错误约定。小而具体的接口通常更容易理解和测试。

## 接着探索 {#related}

- [State、重新渲染与状态快照](/learn/react-state)
- [Effect、依赖与清理](/learn/react-effects)
- [状态提升与 Context](/learn/react-lifting)

## 来源与版本 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
