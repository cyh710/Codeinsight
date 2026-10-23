# Effect、依赖与清理

## 先建立直觉 {#overview}

Effect 用于让组件与外部系统保持同步，例如注册监听或根据项目 ID 读取数据。它不是所有业务逻辑的默认位置。能够从 props 或 state 直接计算的值，通常应在渲染时计算；用户点击导致的动作通常先放在对应事件处理里。

## 原理与执行过程 {#mechanism}

Effect 在适当的提交阶段之后执行，依赖变化时会重新同步。清理函数负责撤销旧同步，例如取消监听、结束订阅或阻止旧请求结果更新状态。开发模式的额外检查可以暴露清理不完整的问题，不能通过删依赖来掩盖。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

下面展示函数组件内部的 Effect 片段，不是可单独运行的模块。组件需要导入 useEffect，
并使用 useState 建立 setTopic、setError；loadTopic 应是模块中导入的稳定异步函数。
若 loadTopic 来自会变化的 props，应把它也列入依赖数组。教学例子只展示陈旧结果保护，
完整组件还需处理切换时清空旧内容、加载状态与错误显示。

```jsx
useEffect(() => {
  let stale = false;
  loadTopic(topicId).then(topic => {
    if (!stale) setTopic(topic);
  }).catch(error => {
    if (!stale) setError(String(error));
  });
  return () => { stale = true; };
}, [topicId]);
```

## 一步一步读懂 {#walkthrough}

每次 topicId 改变都建立本次同步。旧 Effect 清理后把 stale 置为 true，因此晚到结果不会覆盖新主题。这个例子忽略旧结果，不等于取消底层网络请求；需要时可再加入 AbortController。错误也检查 stale，避免旧失败消息覆盖新状态。

## 常见误解 {#pitfalls}

空依赖数组不是“让代码只运行一次”的万能开关。Effect 里使用了会变化的值却不列入依赖，可能读取陈旧数据。清理不应依赖一个已经变化的全局目标；应撤销该次 Effect 实际建立的资源。

## 工程中的取舍 {#tradeoffs}

Effect 使外部同步明确，但太多相互更新状态的 Effect 会形成复杂链条。可以将共同的资源逻辑提取成自定义 Hook。网络缓存和请求去重也可能更适合专门数据层，而不是每个组件独立实现。

## 接着探索 {#related}

- [State、重新渲染与状态快照](/learn/react-state)
- [Promise 与 async/await](/learn/js-async)
- [Hooks 的调用规则与组合](/learn/react-hooks)
- [网络请求、取消与失败处理](/learn/js-fetch)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
