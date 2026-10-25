# 事件处理与受控输入

## 点击时执行的是哪一行 {#handler-vs-call}

学完这一篇，你能分清传函数和调用函数，做出受控输入框，用表单提交留言，并看懂定时器里读到旧 state 的原因。

留言板现在能加能删，但每次都得用鼠标点“提交”。用户在输入框里按回车，什么都不会发生。你还想让输入框在提交后自己清空。

事件处理就是：某个动作发生时，执行你指定的函数。React 的写法和 HTML 的 `onclick` 很像，但有一处关键差别：你传的是函数本身，不是函数调用结果。

这句话听起来像抠字眼。写错一次，页面可能直接白屏。下面把它拆开。

## 输入框跟着 state 走 {#controlled-input}

先看输入框。它的显示值完全由 state 决定：

```jsx
const [draft, setDraft] = useState("");

<input
  value={draft}
  onChange={(event) => setDraft(event.target.value)}
/>
```

两个 prop 缺一不可：

| 写法 | 作用 |
|---|---|
| `value={draft}` | 输入框显示 state 里的值 |
| `onChange={...}` | 用户每敲一个字符，把新值写回 state |

用户敲下“留”，浏览器先产生输入事件，`onChange` 把 `draft` 设成新字符串；React 重新渲染，`value` 变成新字符串；输入框显示它。看起来像输入框自己变了，实际路径是“事件 → state → 渲染 → 输入框”。

只写 `value` 不写 `onChange`，输入框会变成只读。控制台会警告你：传了 `value` 却没有 `onChange`，这个字段只能读。这不是 bug，是 React 在问：值由谁更新？

只写 `onChange` 不写 `value`，它是非受控输入：DOM 自己保存值，state 只是旁听。两种模式不要中途切换，否则控制台会警告，光标和值也可能跳。

受控输入的代价是每次敲键都要更新 state、重新渲染。留言板这种规模没问题；几万字的长文本编辑器要另做优化。收益是值只有一个来源：禁用按钮、显示字数、做校验，都读同一个 `draft`。

如果表单只有一两个字段、提交时读一次就够，也可以用非受控输入，少写几个 state。需要实时校验、联动或者边输入边改界面，受控更直接。

## 让回车和按钮走同一条路 {#form-submit}

把输入区和按钮包进 `<form>`，提交逻辑放到 `onSubmit`。下面是可以直接替换 `src/App.jsx` 的完整代码：

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

  function handleSubmit(event) {
    event.preventDefault();
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
        <form onSubmit={handleSubmit}>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="写点什么"
          />
          <button type="submit">提交</button>
        </form>
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

和上一篇相比，主要差别是：添加动作从按钮的 `onClick` 换成了表单的 `onSubmit`，输入框和按钮被 `<form>` 包住。删除逻辑没变。

`handleSubmit` 做四件事：

```jsx
function handleSubmit(event) {
  event.preventDefault();
  const text = draft.trim();
  if (!text) return;
  setMessages([...messages, { id: crypto.randomUUID(), author: "我", text }]);
  setDraft("");
}
```

第一步，`preventDefault()`。表单的默认行为是把数据提交到当前地址并刷新页面。不阻止的话，刚加进 state 的留言会随着刷新消失。你会看到页面闪一下，然后一切回到初始状态。

第二步，`trim()` 后再判断。只输入空格不该产生一条空留言。

第三步，`if (!text) return;` 提前结束。不用写 `else`，后面的代码自然不执行。

第四步，先追加留言，再清空草稿。两个 state 在同一次事件里更新，React 合并成一次重新渲染。

为什么按回车也能提交？输入框在 `<form>` 里，回车会触发表单的 submit 事件；点击 `type="submit"` 的按钮触发同一个事件。两条路汇到 `handleSubmit`，不用分别监听键盘。

保存后你应该看到：

- 页面初始仍是两条留言。
- 在输入框写“回车提交的留言”，按回车：列表底部多一条，输入框清空。
- 写“按钮提交的留言”，点“提交”：结果一样。
- 只输入空格再提交：列表不变。
- 点任意一条的“删除”：那一条消失，其余保留。

你可以做个对照实验：把 `event.preventDefault()` 注释掉，再提交一次。页面会刷新，新留言不见了。这就是默认行为。

## 提交之后输入框为什么清空 {#clear-after-submit}

输入框是受控的，它显示 `draft`。`setDraft("")` 之后，下一次渲染的 `value` 是空字符串，所以输入框空了。你清的是 state，界面跟着变。

反过来，直接清 DOM 不会清 state。比如在 `handleSubmit` 里写：

```jsx
event.target.reset();   // 只重置 DOM
```

你看到输入框空了一下，但紧接着 `setMessages` 触发重新渲染，`value={draft}` 又把旧草稿写回去。除非同时 `setDraft("")`，否则 state 和界面会打架。

同样的坑还有手写 `document.querySelector("input").value = ""`。下一次任何 state 更新，旧内容都会回来。受控输入只有一个源头，清它就得清 state。

提交成功后清空，提交失败时通常不清空——用户不用重打一遍。真实项目里等请求成功再清空；这里的例子为了讲同步，直接清空。

## 定时器里读到的是旧 state {#stale-closure}

事件处理函数捕获的是本次渲染的快照。这个规则在异步回调里最容易咬人。看一个独立的小组件：

```jsx
function DelayedCounter() {
  const [count, setCount] = useState(0);

  function handleClick() {
    setTimeout(() => {
      setCount(count + 1);
    }, 3000);
  }

  return <button onClick={handleClick}>点我：{count}</button>;
}
```

三秒内点两次，界面最终只加 1。两次点击都没有立刻改 state，所以中间没有重新渲染，两个定时器回调都来自 `count` 为 0 的那次渲染。三秒后它们各自执行 `setCount(0 + 1)`，两次都设成 1。

改成函数式更新：

```jsx
setTimeout(() => {
  setCount((value) => value + 1);
}, 3000);
```

两次回调排队执行：第一次拿到 0 返回 1，第二次拿到 1 返回 2。界面加 2。

`setInterval` 也会这样。下面这个 Effect 只在挂载时建立定时器，回调里的 `count` 永远是 0：

```jsx
useEffect(() => {
  const id = setInterval(() => {
    console.log(count);   // 0
  }, 1000);
  return () => clearInterval(id);
}, []);
```

要读最新值，用函数式更新；或者把 `count` 放进依赖，每次变化重建定时器——多数情况下那不是你想要的，见 [Effect、依赖与清理](/learn/react-effects)。

记一句话：**函数记住的是它被创建时的那张快照，不是变量的最新值。**

## 输入框上的四个麻烦 {#events-pitfalls}

**“`onClick={handleSubmit()}` 和 `onClick={handleSubmit}` 一样，只是少写括号。”** 完全不一样。带括号在渲染时就执行，`handleSubmit` 收到的是 `undefined` 而不是事件对象，第一行 `event.preventDefault()` 就会报 `Cannot read properties of undefined (reading 'preventDefault')`。就算不报错，`onClick` 拿到的也是返回值，通常不是函数。要传参数就包箭头函数：`onClick={() => handleDelete(message.id)}`。

**“受控输入框显示不对，直接改 DOM 的 value 就行。”** 下一次渲染，`value={draft}` 会把 DOM 改回 state 的值。手改 DOM 只是暂时骗过眼睛，state 一更新就露馅。

**“按回车一定会提交，中文输入法也一样。”** 组合输入时，回车常用于确认候选词。浏览器通常不会在组合期间提交表单，但不同输入法和浏览器的细节不完全一致。要自己监听回车（`onKeyDown`），先看 `event.nativeEvent.isComposing`；更稳的做法是用表单的 `onSubmit`，把判断交给浏览器。

**“提交后清空输入框，用 `event.target.reset()` 最省事。”** 对非受控表单也许行，对受控输入不行。`reset()` 只改 DOM，不改 state；下一次渲染旧值又回来。清 `draft`，不要清 DOM。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面两行有什么区别？哪一行会在渲染阶段就执行？

```jsx
<button onClick={handleSubmit}>提交</button>
<button onClick={handleSubmit()}>提交</button>
```

> **答案**
>
> 第一行传函数引用，点击时 React 才调用它，并把事件对象传进去。
>
> 第二行在渲染时就调用 `handleSubmit()`，没有事件参数。如果函数第一行是 `event.preventDefault()`，会抛 `Cannot read properties of undefined (reading 'preventDefault')`。同时 `onClick` 得到的是返回值，通常不是函数。

**第 2 题**：`<input value={draft} />` 没有 `onChange` 时，为什么敲字敲不进去？怎么改？

> **答案**
>
> 输入框显示的是 `draft`。敲字时浏览器改了 DOM 的值，但 React 没有更新 state；重新渲染后 `value={draft}` 又把显示改回原值，所以看起来输入被吞了。控制台还会提示只有 `value`、没有 `onChange`，字段是只读的。
>
> 加上 `onChange={(event) => setDraft(event.target.value)}`。

**第 3 题**：写一个按钮，点击三秒后把 `count` 加 1。连续点三次，最终加 3。

> **答案**
>
> ```jsx
> function handleClick() {
>   setTimeout(() => {
>     setCount((value) => value + 1);
>   }, 3000);
> }
> ```
>
> 三个回调都从队列里取“前一个结果”再加 1，最终是 3。如果写 `setCount(count + 1)`，三个回调读到的是同一张快照，点三次也只加 1。

## 继续阅读 {#related}

- [State、重新渲染与状态快照](/learn/react-state)
- [DOM 与事件：点击怎样变成行为](/learn/js-dom)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [HTTP 请求与响应](/learn/web-http)

## 参考资料 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
