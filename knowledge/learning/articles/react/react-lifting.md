# 状态提升与 Context

## 先建立直觉 {#overview}

当多个区域需要同步变化，可以把状态放到它们共同的拥有者，再通过 props 或 Context 传递。单一事实来源表示同一业务事实有一个明确的权威状态，而不是每个组件各存一份并靠猜测互相同步。

## 原理与执行过程 {#mechanism}

状态提升把控制权移到共同父级。Context 让深层组件读取上层提供的值，减少逐层转传。Context 本身不是数据库，也不自动持久化、去重请求或解决所有性能问题。阅读位置、当前项目和服务端索引状态可能需要不同生命周期，不能随意揉成一个全局对象。

## 跟着例子理解 {#example}

下面是共同父组件内部的片段，需先从 React 导入 useState。TopicTree 和 Reader
表示已有的目录、阅读组件；这里专门展示二者怎样使用同一个选中状态，并非完整应用。

```jsx
const [selectedTopic, setSelectedTopic] = useState(null);
return <>
  <TopicTree selected={selectedTopic} onSelect={setSelectedTopic} />
  <Reader topicId={selectedTopic} />
</>;
```

## 一步一步读懂 {#walkthrough}

共同父级持有 selectedTopic。目录只发出选择动作，Reader 根据同一个值显示内容，因此二者不会各自维护互相矛盾的选择。若 AI 回答也能打开章节，应调用相同的导航动作，而不是再建立第二套选中状态。切回代码时还需要明确保存原阅读目标。

## 常见误解 {#pitfalls}

把所有字段放进一个 Context 可能让许多消费者不必要地更新。跨项目复用旧状态可能造成证据串项目。localStorage 保存的是客户端快照，不应被当成服务端权限或最新索引事实。

## 工程中的取舍 {#tradeoffs}

局部状态优先保持局部，共享范围越大，维护成本通常越高。Context 适合稳定的环境值或适量共享状态；复杂高频状态可使用有明确订阅机制的数据层。关键是状态所有权和更新入口清楚，而不是选择某个流行工具。

## 接着探索 {#related}

- [Props：组件之间怎样传数据](/learn/react-props)
- [State、重新渲染与状态快照](/learn/react-state)
- [URL、JSON 与 API 契约](/learn/web-api)

## 来源与版本 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
