# 事件处理与受控输入

## 先建立直觉 {#overview}

事件处理把用户动作转换成状态变化。受控输入由 React state 保存当前值，输入框根据这个值显示；用户输入时通过 onChange 更新状态。它使校验和联动更明确，也要求状态更新不能遗漏。

## 原理与执行过程 {#mechanism}

处理函数在事件发生时执行，渲染阶段只传递函数。受控输入使用 value 或 checked 与状态对应。提交表单、键盘回车和点击按钮应汇聚到一致的业务入口。异步提交还要处理重复触发、失败提示和输入是否保留。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```jsx
import { useState } from 'react';

export default function SearchForm() {
  const [query, setQuery] = useState('');
  function submit(event) {
    event.preventDefault();
    console.log(query);
  }
  return <form onSubmit={submit}>
    <input value={query} onChange={event => setQuery(event.target.value)} />
    <button type="submit">查询</button>
  </form>;
}
```

## 一步一步读懂 {#walkthrough}

value 来自 query。每次输入触发 onChange，把新字符串保存进 state。提交时 preventDefault 避免默认页面导航，然后读取当前 query。按回车和点击提交按钮都经过 submit。真实发送请求后，应基于实际结果显示成功或失败，而不是立即清空所有内容。

## 常见误解 {#pitfalls}

有 value 却没有更新处理会让输入看似不能编辑。不要在受控和非受控模式之间无意切换。对中文输入法，需要注意组合输入和快捷键处理，不能每个 Enter 都当作提交。日志里看到回调触发，不代表后端已经保存。

## 工程中的取舍 {#tradeoffs}

受控输入便于一致校验，非受控输入适合某些简单原生表单。长文本编辑和高频交互需要权衡更新成本。尽量使用语义化表单和按钮，减少自己重做键盘行为。

## 接着探索 {#related}

- [State、重新渲染与状态快照](/learn/react-state)
- [DOM 与事件：点击怎样变成行为](/learn/js-dom)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [HTTP 请求与响应](/learn/web-http)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
