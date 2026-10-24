# 条件渲染、列表与 key

## 先建立直觉 {#overview}

条件渲染决定当前显示哪个状态，列表渲染把一组数据转换为多个元素。key 帮助 React 在相邻渲染之间识别同一项，不是单纯为消除警告而填写的数字。身份选错，可能让输入状态或展开状态跟着错误条目移动。

## 原理与执行过程 {#mechanism}

React 根据元素类型、位置和 key 等信息匹配树。稳定的业务 ID 通常比数组索引更适合作为可重排列表的 key。条件分支需要覆盖加载中、失败、空结果与正常结果；空列表与请求未完成不是同一种状态。

## 跟着例子理解 {#example}

```jsx
export default function TopicList({ loading, error, topics }) {
  if (loading) return <p>加载中</p>;
  if (error) return <p>{error}</p>;
  if (!topics.length) return <p>没有匹配章节</p>;
  return <ul>{topics.map(topic => <li key={topic.id}>{topic.title}</li>)}</ul>;
}
```

## 一步一步读懂 {#walkthrough}

首先处理尚未完成的状态，再处理失败与空结果。map 为每个主题建立列表项。topic.id 在重排后仍跟随同一主题，因此 React 可以保持正确身份。若每次渲染都使用随机 key，条目可能被不断重建，阅读位置或输入状态也容易丢失。

## 常见误解 {#pitfalls}

key 不会作为普通 prop 自动传给子组件。用 0 && JSX 可能直接显示数字 0。仅靠 items.length 判断状态，无法区分初次加载与真正没有结果。项目切换时也要避免短暂显示上一个项目的列表。

## 工程中的取舍 {#tradeoffs}

稳定身份有助于状态保留，主动改变 key 则可用于明确重置。列表很大时可考虑分页或虚拟化，但应保留可访问性与跳转定位。先定义每项的真实身份，再决定渲染优化。

## 接着探索 {#related}

- [State、重新渲染与状态快照](/learn/react-state)
- [对象、数组与不可变更新](/learn/js-objects)
- [React 组件与 JSX](/learn/react-components)

## 来源与版本 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
