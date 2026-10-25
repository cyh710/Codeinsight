# State、重新渲染与状态快照

## 点击之后谁记住了数字 {#why-state}

学完这一篇，你能用 useState 保存输入框和留言列表，弄清 setX 之后为什么读不到新值，也躲开数组原地修改的坑。

上一篇的留言来自写死的 `seedMessages`。点删除只弹 alert；刷新页面，两条留言还在，新写的也进不来。界面需要一份会变的记忆。

props 是外面给的，state 是组件自己记的。输入框里的草稿、已经提交的留言，都随时间变化，正好归 state 管。

调用 `useState`，你拿到一对东西：当前值和更新函数。更新函数一调用，React 就安排一次重新渲染，用新值再执行一遍组件函数。

## 用 useState 搭出可增可删的留言板 {#board-with-state}

把 `src/App.jsx` 换成：

```jsx
import { useState } from "react";

function BoardSection({ title, children }) {
  return (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function MessageItem({ author, text, onDelete }) {
  return (
    <li>
      <strong>{author}</strong>
      <p>{text}</p>
      <button onClick={onDelete}>删除</button>
    </li>
  );
}

export default function App() {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([
    { id: "m1", author: "小林", text: "第一条留言" },
    { id: "m2", author: "阿岚", text: "列表已经能跑起来了" },
  ]);

  function handleAdd() {
    const text = draft.trim();
    if (!text) return;
    setMessages([...messages, { id: crypto.randomUUID(), author: "我", text }]);
    setDraft("");
  }

  function handleDelete(id) {
    setMessages(messages.filter((message) => message.id !== id));
  }

  return (
    <main>
      <h1>留言板</h1>
      <BoardSection title="写留言">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="写点什么"
        />
        <button onClick={handleAdd}>提交</button>
      </BoardSection>
      <BoardSection title="全部留言">
        <ul>
          {messages.map((message) => (
            <MessageItem
              key={message.id}
              author={message.author}
              text={message.text}
              onDelete={() => handleDelete(message.id)}
            />
          ))}
        </ul>
      </BoardSection>
    </main>
  );
}
```

输入框的 `value` 来自 `draft`，`onChange` 把每次输入写回 `draft`。这两个属性下一篇会拆开讲。

保存后你应该看到：“留言板”标题，一个空输入框和“提交”按钮，下面两条留言各带一个删除按钮。

在输入框里写“第三条留言”，点“提交”：新留言出现在列表底部，输入框清空。点某条的“删除”，那一条消失，其余不动。

`crypto.randomUUID()` 在 localhost 和 HTTPS 页面可用。换成 `Date.now().toString()` 也能跑，只是同一毫秒连点两次可能撞 id。

这些 state 只在当前页面有效，刷新会回到两条初始留言。要跨刷新保存，得写 `localStorage` 或发到后端，那是另一层的事。

## 每次渲染都是一张快照 {#render-snapshot}

`const [draft, setDraft] = useState("")` 做了两件事：从 React 拿当前值，再拿更新函数。

`setDraft` 不会改你手里的 `draft` 变量。它把更新排进队列，然后安排下一次渲染；下一次执行组件函数时，`useState` 才返回新值。

所以事件处理函数里读到的 `draft`、`messages`，都是这次渲染时的值，像一张不会变的照片。同一个处理函数里读十次，拿到的都是同一张照片。

这解释了一个常见现象：

```jsx
function handleAdd() {
  setDraft("新内容");
  console.log(draft);   // 还是点击时的旧内容
}
```

控制台打印旧值。更新已经排队了，但这段代码不会中途换照片。想看新值，就在下一次渲染里看。

界面什么时候变？React 处理完事件，把这一批更新合并，重新调用 `App`。这次 `useState` 返回新的 `draft` 和 `messages`，JSX 重新生成，React 把差异写进 DOM。

“更新是异步的”说的是这个排队过程，不是“过几毫秒一定执行”。React 可能在事件处理结束后马上渲染，也可能和同一批的其他更新合并。你的代码不该依赖“set 之后立刻读到新值”。

## 连写两次 setCount 只加一次 {#functional-update}

假设你想一次加 2：

```jsx
function handleClick() {
  setCount(count + 1);
  setCount(count + 1);
}
```

点击时 `count` 是 0。两行读的是同一张快照，都算出 1。React 把两次“设为 1”排队，界面只加一次。

改成函数式更新：

```jsx
function handleClick() {
  setCount((value) => value + 1);
  setCount((value) => value + 1);
}
```

传进去的是函数，React 按队列依次调用：第一次收到 0，返回 1；第二次收到 1，返回 2。点击后是 2。

规则：新值依赖旧值时，用函数式更新；新值由别处数据直接算出来时，普通写法够用。

批处理也是同一套机制。一个事件处理函数里改了三个 state，React 只安排一次重新渲染，不会每改一个字段就重画一遍。你写三次 `setMessages`，界面也只变一次。

## 数组要换一份新的 {#immutable-array}

下面这种写法不会可靠地更新界面：

```jsx
function handleAdd() {
  messages.push({ id: crypto.randomUUID(), author: "我", text: draft });
  setMessages(messages);
}
```

`push` 改的是同一个数组。React 用 `Object.is` 比较新旧 state，发现还是同一个引用，通常会直接跳过这次更新。更糟的是数据已经变了，界面却还停在旧样子。

如果你在输入框里再敲一个字，输入框的 state 触发重新渲染，刚才那条留言会突然出现。这个“先不动、后来突然出现”就是原地修改的典型症状。

正确做法是造一个新数组：

```jsx
setMessages([...messages, newMessage]);                                    // 加
setMessages(messages.filter((message) => message.id !== id));              // 删
setMessages(messages.map((message) =>
  message.id === id ? { ...message, text: "改过" } : message
));                                                                        // 改
```

三行分别对应加、删、改。共同点是返回新数组，不碰原来的。改对象字段也一样：`{ ...message, text: "改过" }` 先复制，再覆盖一个字段。

React 靠引用比较判断“变没变”。原地改之后，旧引用和新引用是同一个，它看不出来。不可变更新的代价是每次复制；收益是数据流向可预测，谁都没有偷偷改老数据。

如果同一次事件里要连续改两次列表，用函数式写法：

```jsx
setMessages((prev) => [...prev, first]);
setMessages((prev) => [...prev, second]);
```

道理和 `setCount` 一样：第二个更新拿到的是第一个更新算出的结果，不是渲染时的旧数组。

## 能算出来的不要再存 {#derived-state}

留言条数需要单独存一个 state 吗？

```jsx
const [messages, setMessages] = useState([]);
const [count, setCount] = useState(0);   // 多余
```

不需要。渲染时算：

```jsx
<p>共 {messages.length} 条留言</p>
```

多存一份，就得在每次增删时记得同步。漏一次，两处数字就对不上。这是同一类 bug 的常见来源：同一件事有两个版本。

判断方法：这个值能不能从现有的 props 和 state 直接算出来？能，就别存。

- `messages.length`：算。
- 输入框是不是空的：`draft.trim() === ""`，算。
- 用户正在输入的字：不能算，存 state。
- 已经提交的留言：不能从别处算，存 state。
- 筛选后的列表：`messages.filter(...)` 在渲染时算，不要再存一份筛选结果。

有些值看起来该存，其实能算，比如新留言的 id。用 `crypto.randomUUID()` 就不需要维护计数器。反过来，如果 id 必须递增，计数器就得单独存，因为它依赖历史，不是当前数据能推出来的。

state 也不是越多越好。只影响一个区域的记忆放在组件内部；两个区域要同步，就提升到共同父级，见 [状态提升与 Context](/learn/react-lifting)。把什么都塞进全局 state，改一个输入框会让一片组件重渲染。先保证数据流对，再谈优化。

## 快照留下的三个怪现象 {#state-pitfalls}

**“setState 之后马上 console.log，能看到新值。”** 看到的是本次渲染的快照。更新已经排队，界面也会变，但当前这行代码里的变量不会变。验证方法就是上面的 `handleAdd`，打印出来是旧草稿。

**“`messages.push` 之后调用 `setMessages(messages)`，界面会刷新。”** 同一个引用，React 通常跳过更新。它也可能先渲染一次再丢弃结果，让你看到新条目，那同样不是可靠行为。用展开复制，或者函数式更新 `setMessages((prev) => [...prev, newMessage])`。

**“异步回调里展开的 `messages` 是最新的。”** 不是。回调捕获的是它被创建那次渲染的数组。用户在这期间又加了留言，回调里的旧数组会把新内容覆盖掉。假设页面上有个“加载更多”按钮调用下面这个函数：

```jsx
function loadMore() {
  setTimeout(() => {
    const remote = [{ id: "m9", author: "阿岚", text: "晚到的留言" }];
    setMessages([...messages, ...remote]);   // messages 是发起时的旧数组
  }, 2000);
}
```

点“加载更多”后，在两秒内提交一条新留言。两秒后，新留言会消失，因为回调拿旧数组整个替换了 state。改成函数式更新，让 React 把当前值交给你：

```jsx
setMessages((prev) => [...prev, ...remote]);
```

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：`count` 初值是 0，点击后执行下面两行。界面显示几？改成函数式呢？

```jsx
setCount(count + 1);
setCount(count + 1);
```

> **答案**
>
> 普通写法显示 1：两行都基于 0，排队后都是“设为 1”。
>
> 函数式写法显示 2：
>
> ```jsx
> setCount((value) => value + 1);
> setCount((value) => value + 1);
> ```
>
> 第二个更新接收到第一个的结果 1，再加 1。

**第 2 题**：下面代码点击后，列表为什么没有稳定地增加？怎么改？

```jsx
function handleAdd() {
  messages.push({ id: "m3", author: "我", text: draft });
  setMessages(messages);
}
```

> **答案**
>
> `push` 改了原数组，传给 `setMessages` 的还是同一个引用。React 用 `Object.is` 比较，通常直接跳过更新。数据已经变了，界面却没跟着走。
>
> 改成：
>
> ```jsx
> const newMessage = { id: crypto.randomUUID(), author: "我", text: draft };
> setMessages([...messages, newMessage]);
> setDraft("");
> ```
>
> 想要更稳，用 `setMessages((prev) => [...prev, newMessage])`。

**第 3 题**：下面哪些需要 state？(a) 留言数组 (b) 留言条数 (c) 输入框草稿 (d) 提交按钮是否禁用 (e) 渲染时的筛选结果。

> **答案**
>
> 需要：(a)、(c)。
>
> 不需要：(b) 用 `messages.length`；(d) 用 `draft.trim() === ""`；(e) 在渲染时 `filter`。这三样都能从现有 state 算出来，存了就要同步，容易不同步。

## 继续阅读 {#related}

- [Props：组件之间怎样传数据](/learn/react-props)
- [对象、数组与不可变更新](/learn/js-objects)
- [事件处理与受控输入](/learn/react-events)
- [状态提升与 Context](/learn/react-lifting)

## 参考资料 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
