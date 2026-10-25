# 条件渲染、列表与 key

## 条件渲染是在选一块界面 {#conditional-render}

学完这一篇，你能把加载、失败和空结果分开显示，也能用稳定的消息 id 做 key，不让输入框的内容跟着位置乱跑。

留言板刚打开时在等数据，请求可能失败，项目也可能一条留言都没有。这三种情况都显示“还没有留言”，用户就分不清是没数据还是没加载完。

条件渲染没有单独的 API，它只是在 JSX 里决定这里放哪个元素。

整个组件要根据状态换一整块界面时，用提前 `return`：

```jsx
function ProjectPage({ loading, error, project }) {
  if (loading) return <p>加载中…</p>;
  if (error) return <p>加载失败：{error}</p>;
  if (!project) return <p>项目不存在</p>;

  return <h1>{project.name}</h1>;
}
```

只在一个位置二选一时，用三元表达式：

```jsx
<p>{messages.length === 0 ? '还没有留言' : `共 ${messages.length} 条留言`}</p>
```

`&&` 适合左边一定是布尔值的情况，比如“有权限才显示删除按钮”：

```jsx
{isOwner && <button type="button">删除</button>}
```

左边换成数字就要小心：`0` 虽然是假值，但 `0 && <X />` 返回的是 `0` 本身，React 会把 `0` 画在页面上。

```jsx
const unread = 0;
return <p>{unread && <span>有未读留言</span>}</p>; // 页面出现一个 0
```

改成 `unread > 0 && ...`。空数组和空字符串也会让 `&&` 返回左边那个值；需要展示“没有内容”时，用三元把两种情况都写清楚。

## 先把留言板跑起来 {#message-board}

新建一个 Vite 项目：

```bash
npm create vite@latest message-board -- --template react
cd message-board
npm install
npm run dev
```

把 `src/App.jsx` 整个换成下面的代码。Vite 模板里的 `main.jsx` 已经会导入 `App`，不用改。

```jsx
import { useState } from 'react';

const projects = [
  { id: 'weekend', name: '周末计划' },
  { id: 'reading', name: '读书会' },
  { id: 'empty', name: '空项目' },
];

const initialMessages = {
  weekend: [
    { id: 'm1', text: '周六去爬山吗？' },
    { id: 'm2', text: '我带水和面包。' },
  ],
  reading: [{ id: 'm3', text: '这周读《小王子》。' }],
  empty: [],
};

let nextId = 4;

function MessageRow({ message }) {
  const [note, setNote] = useState('');

  return (
    <li>
      <p>{message.text}</p>
      <input
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="给这条留言写批注"
      />
    </li>
  );
}

export default function App() {
  const [projectId, setProjectId] = useState('weekend');
  const [messages, setMessages] = useState(initialMessages);
  const [draft, setDraft] = useState('');

  const project = projects.find((item) => item.id === projectId);
  const currentMessages = messages[projectId] ?? [];

  if (!project) {
    return <p>找不到这个项目。</p>;
  }

  function handleSubmit(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;

    const newMessage = { id: `m${nextId++}`, text };
    setMessages((current) => ({
      ...current,
      [projectId]: [newMessage, ...(current[projectId] ?? [])],
    }));
    setDraft('');
  }

  return (
    <main>
      <h1>留言板</h1>

      <label>
        当前项目：
        <select
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
        >
          {projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>

      <form onSubmit={handleSubmit}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="写一条留言"
        />
        <button type="submit">提交</button>
      </form>

      {currentMessages.length === 0 ? (
        <p>这个项目还没有留言。</p>
      ) : (
        <ul>
          {currentMessages.map((message) => (
            <MessageRow key={message.id} message={message} />
          ))}
        </ul>
      )}
    </main>
  );
}
```

你应该看到：

```text
页面上方是「留言板」、项目下拉框和留言输入框。
「周末计划」下面有两条留言，每条留言下面还有一个批注输入框。
切到「读书会」只剩一条留言；切到「空项目」显示「这个项目还没有留言。」。
在顶部输入「临时通知」并提交，它会成为当前列表的第一条，输入框被清空。
```

## map 和条件表达式各自在做什么 {#render-walkthrough}

**第一步，先拿到当前项目的留言。** `projects.find(...)` 按 `projectId` 找回项目对象；`messages[projectId] ?? []` 从按项目分组的对象里取出这一组留言。没有对应 key 时退回空数组，后面的 `map` 不会因为 `undefined` 崩掉。

**第二步，处理整个页面都不该显示的情况。** `if (!project)` 是提前 `return`。它写在所有 Hook 之后，因为 Hook 不能在条件分支里被跳过。

**第三步，渲染项目下拉框。** 这里的 `map` 把三个项目对象变成三个 `<option>`。每个 `<option>` 的 `key` 用项目 id，和下面留言列表同理。

**第四步，在空列表和有留言之间二选一。** 三元表达式只会选择 `p` 或 `ul` 中的一个。如果写成 `currentMessages.length && <ul>...</ul>`，空项目会多出一个 `0`。

**第五步，把留言数组变成元素数组。** `currentMessages.map(...)` 为每条消息创建一个 `<MessageRow>`，数组交给 JSX 后，React 会把这些元素依次放进 `<ul>`。`key` 写在 `map` 返回的最外层元素上，这里就是 `<MessageRow>` 那一行。

**第六步，提交时改数据。** 事件处理函数创建一个新消息对象，再用对象展开生成新的 `messages` 对象。React 看到新引用后重新渲染，新留言进入列表。`MessageRow` 里的 `note` 是它自己的局部状态，跟父级留言数据无关。

## key 是列表项的身份，不是消警告的数字 {#key-identity}

`key` 不是普通 prop。React 用它在相邻两次渲染之间回答一个问题：这个位置上的组件，还是上一条数据对应的那个组件吗？

先保持代码里的 `key={message.id}`，做一遍这个操作：

1. 在第一条留言「周六去爬山吗？」下面的批注框里输入“记得带伞”。
2. 在顶部输入“临时通知”并提交。
3. 新留言会插到第一条，原来的两条各往下挪一位。

你会看到“记得带伞”跟着「周六去爬山吗？」一起挪到了第二行，新留言的批注框是空的。因为 `m1` 还是 `m1`，React 把同一个 `MessageRow` 和它的输入状态挪到了新位置。

改完后刷新页面，现在把 `map` 换成用下标当 key：

```jsx
{currentMessages.map((message, index) => (
  <MessageRow key={index} message={message} />
))}
```

重复上面的操作。批注框里的“记得带伞”会留在第 1 行，可第 1 行现在显示的是“临时通知”；原来的「周六去爬山吗？」退到第 2 行，批注框却空了。输入内容没有跟着消息走，它被粘在了“第几个位置”上。

这不是输入框坏了。下标 key 告诉 React：第 0 个位置永远是同一个组件。React 就只更换传进去的 `message` prop，`MessageRow` 内部的 `note` 状态不重建。消息换了，输入框里的内容还留着，于是串到了新消息身上。

焦点也会受身份影响。假设你正在列表末行的批注框里打字，随后筛选列表，前面的行被去掉，列表变短。用下标 key 时，末尾那一格可能被整块卸载，焦点直接丢失；用消息 id 时，React 会把同一个输入框挪到新位置，焦点和内容都还能跟着那条消息。

改成 id 后，React 在新列表的 key 列表里仍然找得到 `m1`，知道它只是换了位置，于是移动原来的组件，而不是拿别的组件状态来复用。

`key` 只需要在同一个父元素的兄弟之间唯一，不需要全局唯一。它也不会出现在 `props` 里，子组件读不到 `props.key`。如果子组件真的需要消息 id，就再传一个普通 prop：

```jsx
<MessageRow key={message.id} messageId={message.id} message={message} />
```

## 四处最容易写错的地方 {#list-pitfalls}

**“`count && <List />` 在 count 为 0 时什么都不显示。”** 它会显示 `0`。`&&` 返回的是左操作数，不是布尔值。要隐藏就写 `count > 0 && <List />`，或者用三元明确写出空状态。

**“key 会自动传进子组件，子组件直接读就行。”** 读不到。`key` 被 React 用于协调，不会成为 `props` 的字段。子组件需要 id 时，额外传 `id={message.id}`。

**“随机数也是唯一的，用随机数当 key 一样。”** 唯一不等于稳定。每次渲染都换随机数，React 会认为所有列表项都是新组件，于是全部卸载重建。批注框里的字、输入焦点、展开状态都会没。key 要跟数据身份一样稳定，不是每次都新。

**“列表为空和请求还没回来是一回事。”** 不是。请求未完成时应该显示加载中，请求成功但结果为零时才显示空列表。只看 `messages.length === 0` 会把这两个时刻混成一个界面。项目切换时更要注意：不要先显示上一个项目的留言，再等新数据回来。

## 什么时候该换 key、什么时候不该铺满列表 {#list-tradeoffs}

默认用稳定 id。只有当你要**故意清空**某一项的内部状态时，才主动换 key。

比如一个子组件 `Composer` 自己保存草稿，你希望在切换项目时把草稿清掉，可以给它换一个和项目绑定的 key：

```jsx
<Composer key={projectId} projectId={projectId} />
```

key 一变，React 卸载旧组件、挂载新组件，草稿自然归零。这个办法只在状态确实放在 `Composer` 内部时有效。当前示例的 `draft` 放在 `App` 里，改 `<form>` 的 key 不会清掉它，得在切换事件里调用 `setDraft('')`，或者按项目分别保存草稿。

用下标 key 只在一种情况下勉强说得过去：列表从创建到销毁都不排序、不插入、不删除、不筛选，而且每一项都没有内部状态。项目里一旦出现这些操作中的任何一个，下标就不再代表身份。别把它当默认选项。

列表很长时，优先分页，减少一次渲染的条目；只有确实卡顿时再考虑虚拟化。虚拟化会改变 DOM 里实际存在的条目，滚动定位、键盘操作、浏览器查找和无障碍读屏都要重新验证。先确认每项的真实身份，再谈渲染优化。

## 练习 {#self-check}

**第 1 题**：下面这段代码在 `messages` 为空时会显示什么？

```jsx
{messages.length && <MessageList messages={messages} />}
```

> **答案**
>
> 显示一个 `0`。空数组的 `length` 是 `0`，`0 && ...` 返回 `0`，React 会把它渲染成文本。
>
> 改成：
>
> ```jsx
> {messages.length > 0 && <MessageList messages={messages} />}
> ```
>
> 或者用三元同时处理有数据和空状态。

**第 2 题**：列表里每条留言都有一个批注输入框。现在用 `key={index}`，用户给第一条写完批注，又提交了一条新留言置顶。批注内容会出现在哪一条消息下面？为什么？

> **答案**
>
> 仍留在第 1 个位置，也就是新提交的那条消息下面。
>
> 因为下标 key 表示“位置不变”，React 复用第 0 个位置的 `MessageRow` 和它的 `note` 状态，只替换 `message` prop。旧消息往下移动时，它的输入状态没有跟着移动。
>
> 把 key 改成 `message.id`，React 就能按消息身份移动组件，批注会跟着原消息走。

**第 3 题**：草稿 `draft` 原本在子组件 `Composer` 内部。你希望在切换项目时清空草稿，最少改哪里？

> **答案**
>
> 给 `Composer` 加项目相关的 key：
>
> ```jsx
> <Composer key={projectId} projectId={projectId} />
> ```
>
> 项目一变，旧的 `Composer` 被卸载，内部 `useState` 的草稿也一起消失，新的组件拿到空草稿。
>
> 如果草稿放在父组件的 state 里，换 key 不起作用，得在项目切换的事件处理里显式清空，或者按项目分开存。

## 继续阅读 {#related}

- [State、重新渲染与状态快照](/learn/react-state)
- [对象、数组与不可变更新](/learn/js-objects)
- [React 组件与 JSX](/learn/react-components)
- [Hooks 的调用规则与组合](/learn/react-hooks)

## 参考资料 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
