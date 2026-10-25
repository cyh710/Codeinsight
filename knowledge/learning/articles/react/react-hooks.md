# Hooks 的调用规则与组合

## 一个 Hook 到底记住了什么 {#hook-state}

学完这一篇，你能守住 Hook 的调用顺序，写出一个自定义 Hook，并说清两个组件各自调用它时为什么不会共享状态。

你在留言板里抽了一个 `useMessages`，周末计划和读书会各有一个 `MessageBoard`。在周末计划里提交一条留言，读书会的列表不会跟着变。

这不是状态没“连上”，而是两个组件实例各有一份。理解这一点，后面两条调用规则就不像死记硬背了。

Hook 是函数组件借用 React 能力的函数。`useState`、`useRef`、`useEffect` 是内置 Hook；自定义 Hook 调用它们，把一段相关逻辑组合起来。

规则只有两条：只在函数组件或自定义 Hook 的顶层调用；同一个组件每次渲染都按相同的顺序调用。第一条防止你把 Hook 放进条件、循环或事件处理里，让调用时有时无；第二条则要求这些调用从头到尾保持同样的次序。

## 用 useMessages 管住一份留言 {#custom-hook-example}

新建一个 Vite 项目：

```bash
npm create vite@latest message-board -- --template react
cd message-board
npm install
npm run dev
```

先建 `src/useMessages.js`：

```jsx
import { useRef, useState } from 'react';

export function useMessages(initialMessages) {
  const [messages, setMessages] = useState(initialMessages);
  const nextId = useRef(100);

  function addMessage(text) {
    const trimmed = text.trim();
    if (!trimmed) return;

    setMessages((current) => [
      { id: `m${nextId.current++}`, text: trimmed },
      ...current,
    ]);
  }

  return { messages, addMessage };
}
```

再把 `src/App.jsx` 换成：

```jsx
import { useState } from 'react';
import { useMessages } from './useMessages';

const projects = [
  { id: 'weekend', name: '周末计划' },
  { id: 'reading', name: '读书会' },
];

const initialMessages = {
  weekend: [
    { id: 'w1', text: '周六去爬山吗？' },
    { id: 'w2', text: '我带水和面包。' },
  ],
  reading: [{ id: 'r1', text: '这周读《小王子》。' }],
};

function MessageBoard({ project }) {
  const { messages, addMessage } = useMessages(
    initialMessages[project.id] ?? [],
  );
  const [draft, setDraft] = useState('');

  function handleSubmit(event) {
    event.preventDefault();
    addMessage(draft);
    setDraft('');
  }

  return (
    <section>
      <h2>{project.name}</h2>

      <form onSubmit={handleSubmit}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={`给「${project.name}」写留言`}
        />
        <button type="submit">提交</button>
      </form>

      {messages.length === 0 ? (
        <p>还没有留言。</p>
      ) : (
        <ul>
          {messages.map((message) => (
            <li key={message.id}>{message.text}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function App() {
  const [projectId, setProjectId] = useState(projects[0].id);

  return (
    <main>
      <h1>留言板</h1>

      <label>
        当前项目：
        <select
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>

      {projects.map((project) => (
        <div key={project.id} hidden={project.id !== projectId}>
          <MessageBoard project={project} />
        </div>
      ))}
    </main>
  );
}
```

你应该看到：

```text
「周末计划」下面有两条留言，切到「读书会」后只剩一条。
在周末计划的输入框输入「明天见」但不提交，切到读书会，再输入「下周换书」。
切回周末计划，第一段草稿还在；再切回读书会，第二段草稿也还在。
在周末计划里提交一条新消息，切到读书会，列表没有多出来；再切回来，新消息还在。
```

两个 `MessageBoard` 从页面打开时就都挂载着，`hidden` 只是把非当前项目藏起来。它们各自调用了一次 `useMessages`，各自有独立的 `messages`、`nextId` 和草稿。

## 两个组件调用同一个 Hook，状态为什么没共享 {#independent-state}

Hook 函数本身只是一段代码。每次 React 渲染一个 `MessageBoard`，都会执行一次 `useMessages`；这一次执行里的 `useState` 和 `useRef` 属于当前组件实例，不属于那个函数文件。

周末计划里的 `useMessages` 拿到一组状态槽，读书会里的调用拿到另一组。`addMessage` 每次在各自的闭包里调用 `setMessages`，改的也是各自那组数据。

如果把项目区域改成条件渲染，只在当前项目时挂载：

```jsx
{projects
  .filter((project) => project.id === projectId)
  .map((project) => (
    <MessageBoard key={project.id} project={project} />
  ))}
```

切换项目会卸载旧的 `MessageBoard`，它的 Hook 状态随之消失，草稿和新增留言都留不住。这个示例用 `hidden` 让两个组件一直活着，所以能做到“切过去再切回来，内容还在”。Hook 状态跟着组件实例的生命周期走，不跟着 Hook 所在的文件走。

要共享数据，必须让两个组件读到同一份状态。可以让共同父级调用一次 Hook，再把值和回调通过 props 传下去；也可以把状态放进 Context 或带订阅的数据层。两边各调一次 `useMessages`，无论函数名多像，都不可能自动共享。

## 条件分支里调用会当场报错 {#call-order}

看一个会出错的写法：

```jsx
import { useState } from 'react';

function MessageBoard({ loading }) {
  if (loading) {
    return <p>加载中…</p>;
  }

  const [draft, setDraft] = useState('');
  return (
    <input
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
    />
  );
}
```

第一次 `loading` 是 `true` 时，组件提前返回，一个 Hook 都没调用。数据加载完，`loading` 变成 `false`，这次调用了一个 `useState`。React 会在控制台报：

```text
Rendered more hooks than during the previous render.
```

反过来，如果先渲染有 Hook 的版本，再切到提前返回的版本，就会报“渲染的 Hook 比上一次少”。React 计数不是为了刁难你，它在用数量判断状态槽是否对得上。

React 在每个组件实例里维护一组 Hook 状态槽，还有一个渲染时从头开始的游标。第一次 `useState` 占第 0 个槽，第二次占第 1 个槽。下一次渲染时，它按调用顺序把状态发回去。变量名在运行时并不参与这个对应关系。

所以顺序一变，麻烦不只是数量不对。假设两个 Hook 换了位置：

```jsx
const [name, setName] = useState('小林');
const [count, setCount] = useState(0);
```

如果某次渲染先调用了原本第二行，React 会把原来存在第 0 个槽的字符串交给 `count`，把数字交给 `name`。类型可能看起来不对，更新函数也可能改错值。规则之所以严格，是因为状态靠位置认领。

修法是先无条件调用 Hook，再做条件返回：

```jsx
function MessageBoard({ loading }) {
  const [draft, setDraft] = useState('');

  if (loading) {
    return <p>加载中…</p>;
  }

  return (
    <input
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
    />
  );
}
```

如果只有某个子组件需要这组状态，把子组件拆出去，再在父级条件渲染它：

```jsx
{loading ? <p>加载中…</p> : <Composer projectId={projectId} />}
```

`Composer` 挂载时才调用自己的 Hook，卸载时状态一起销毁，顺序问题就不存在了。

## use 开头的名字是在告诉工具什么 {#naming-rules}

自定义 Hook 用 `use` 开头，比如 `useMessages`、`useLocalStorage`。这不是语法强制，React 运行时也不会检查前三个字母。

它是在告诉 ESLint 和 React DevTools：“这个函数里可能调用 Hook，请按 Hook 的规则检查。” `eslint-plugin-react-hooks` 靠这个前缀识别自定义 Hook，再检查它有没有在组件或另一个 Hook 的顶层被调用。名字叫 `getMessages`、内部却调用 `useState` 的函数不会因此变成合法 Hook，它仍然是一个在普通函数里调用 Hook 的违规写法。

名字不会给函数增加能力。`useMessages()` 放进按钮的 `onClick`，仍然会报 Invalid hook call，因为点击时没有正在进行的组件渲染。Hook 只能出现在函数组件或另一个自定义 Hook 的顶层。

`use` 开头也不代表它自动变成一个共享单例。它仍然是在调用位置创建属于那个组件的一份逻辑和状态。

## 五条容易踩坏的规则 {#hook-pitfalls}

**“名字以 use 开头，就自动有了 Hook 能力。”** 没有。能力来自 React 正在渲染，名字只是给检查工具的路标。放到事件处理里调用，照样报错。

**“条件分支里不能写，我用一个普通函数包一层再调用就行。”** 不行。包一层的函数如果内部调用 Hook，它自己也得是自定义 Hook，而且调用它的地方仍然要在顶层。条件调用只是换了个文件位置，顺序照样会变。

**“两个组件都调用同一个 Hook，所以它们的数据会同步。”** 不会。每次调用分配各自的状态槽。需要共享就把状态交给共同父级、Context 或数据层，不能靠共用函数名。

**“Hook 返回的对象能直接放进依赖数组，反正内容一样。”** 对象字面量每次渲染都是新引用，`Object.is` 会认为它变了。需要依赖具体字段时，先解构：

```jsx
const { messages, addMessage } = useMessages(initialMessages);
```

如果 `addMessage` 本身每次渲染都换引用，又确实要放进 Effect 依赖，就用 `useCallback` 稳定它，或者把调用逻辑收进 Hook 内部。别用空依赖掩盖变化。

**“规则检查通过，说明这个 Hook 的逻辑就是对的。”** lint 只检查调用位置、数量和一些依赖，它不知道请求有没有竞态、清理是否完整、错误是否被吞掉。Hook 的行为仍然要靠测试和实际运行验证。

## 抽 Hook 的边界 {#hook-tradeoffs}

抽 Hook 应该围绕一个清楚的责任：管理一组留言的增删、保存输入草稿、处理某个请求的生命周期。接口小而具体，读的人一眼能知道它负责什么、不负责什么。

把请求、筛选、弹窗、提示消息全塞进一个 `useEverything`，只是把复杂藏进了另一个文件。调用处变短了，排查问题时却要跳进一个几十个状态互相影响的函数。

越通用的 Hook，越要把生命周期、取消、错误和返回值的身份约定写清楚。比如 `useMessages` 目前只管本地数组；如果以后加上服务端同步，就要处理加载状态、失败、重复请求和卸载后不再写状态。

自定义 Hook 也不能解决“共享数据”的问题。它复用的是调用逻辑，不是状态。共享范围一大，应该让状态归属明确，而不是继续加参数和 `useEffect`。

## 练习 {#self-check}

**第 1 题**：为什么下面的写法第一次能渲染，加载结束后会报错？

```jsx
function Board({ loading }) {
  if (loading) return <p>加载中…</p>;
  const [draft, setDraft] = useState('');
  // ...
}
```

> **答案**
>
> 第一次渲染提前返回，Hook 数量是 0；加载结束后这次渲染调用了 `useState`，Hook 数量变成 1。React 按调用顺序对应状态槽，数量对不上就报 “Rendered more hooks than during the previous render.”
>
> 把 `useState` 移到条件返回之前：
>
> ```jsx
> const [draft, setDraft] = useState('');
> if (loading) return <p>加载中…</p>;
> ```
>
> 或者把带 Hook 的部分拆成子组件，在父级条件渲染这个子组件。

**第 2 题**：两个 `MessageBoard` 都调用 `useMessages`，在其中一个里提交留言，另一个会变吗？如果要让它们同步，应该把状态放到哪里？

> **答案**
>
> 不会。两个调用分别属于两个组件实例，各自有独立的 `useState` 和 `useRef`。
>
> 要同步，把 `useMessages` 提到共同父级只调用一次，把 `messages` 和 `addMessage` 通过 props 传下去；层级很深时用 Context 提供，或者交给一个明确的数据层。不要在两边各调一次再想办法“通知”对方。

**第 3 题**：给 `useMessages` 增加一个“清空留言”的函数，怎么写？

> **答案**
>
> 在 Hook 内增加一个函数，用同一个 `setMessages` 清空，并一起返回：
>
> ```jsx
> function clearMessages() {
>   setMessages([]);
> }
>
> return { messages, addMessage, clearMessages };
> ```
>
> 调用方只能在组件顶层拿到 `clearMessages`，再在事件处理里调用它。不要直接把 `setMessages` 暴露出去，Hook 可以保留自己决定怎么改数据。

## 继续阅读 {#related}

- [State、重新渲染与状态快照](/learn/react-state)
- [Effect、依赖与清理](/learn/react-effects)
- [状态提升与 Context](/learn/react-lifting)
- [Props：组件之间怎样传数据](/learn/react-props)

## 参考资料 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
