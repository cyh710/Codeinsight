# Props：组件之间怎样传数据

## 同一条留言，换个人写 {#props-overview}

学完这一篇，你能把作者、内容和删除动作从父组件传给子组件，也能判断什么时候该继续传、什么时候该换个结构。

上一篇的 `MessageItem` 把“小林”和“第一条留言”写死在组件里。现在第二条留言是阿岚写的，你不想再造一个 `MessageItemB`。结构一样，只有数据不同。

props 就是父组件传给子组件的参数。写 `<MessageItem author="阿岚" text="列表已经能跑起来了" />`，子组件会收到一个对象：`{ author: "阿岚", text: "列表已经能跑起来了" }`。

它和普通函数参数是一回事，只是写在 JSX 属性里。属性名就是参数名，值可以是字符串、数字、对象、数组，也可以是函数。

## 父组件把三样东西传下去 {#pass-author-text-delete}

把 `src/App.jsx` 换成：

```jsx
function MessageItem({ author, text, onDelete }) {
  return (
    <li>
      <strong>{author}</strong>
      <p>{text}</p>
      <button onClick={onDelete}>删除</button>
    </li>
  );
}

const seedMessages = [
  { id: "m1", author: "小林", text: "第一条留言" },
  { id: "m2", author: "阿岚", text: "列表已经能跑起来了" },
];

export default function App() {
  function handleDelete(id) {
    alert(`要删除第 ${id} 条留言`);
  }

  return (
    <main>
      <h1>留言板</h1>
      <section>
        <h2>全部留言</h2>
        <ul>
          {seedMessages.map((message) => (
            <MessageItem
              key={message.id}
              author={message.author}
              text={message.text}
              onDelete={() => handleDelete(message.id)}
            />
          ))}
        </ul>
      </section>
    </main>
  );
}
```

保存后你应该看到：

```
留言板
全部留言
小林
第一条留言
删除
阿岚
列表已经能跑起来了
删除
```

点第一个“删除”，浏览器弹出 `要删除第 m1 条留言`。现在还没有真的删除，只是验证回调确实带着 id 回到了父组件。

代码里出现了一个 `key`。它是给列表用的身份标记，React 不会把它放进 `props`。这里先照写，它的规则在 [条件渲染、列表与 key](/learn/react-lists) 里讲。

## 子组件只读这份输入 {#read-only-props}

`MessageItem({ author, text, onDelete })` 用的是参数解构。React 调用组件时传进来一个对象，这行写法从对象里取出三个字段。

props 是只读输入。子组件可以读，但不该改。试着在 `MessageItem` 里加一行：

```jsx
function MessageItem({ author, text, onDelete }) {
  author = "别人";
  return (
    <li>
      <strong>{author}</strong>
      <p>{text}</p>
      <button onClick={onDelete}>删除</button>
    </li>
  );
}
```

界面会显示“别人”，但父组件的 `seedMessages` 一点没变。你改的只是函数里的局部变量。父组件下次重新渲染，传进来的还是原来的作者。

改对象内部更隐蔽：

```jsx
function MessageItem({ message }) {
  message.text = "被改掉了";
  return <li>{message.text}</li>;
}
```

这真的改到了父组件持有的那个对象，但界面不会立刻更新——React 没收到任何“状态变了”的通知。等到别的原因触发重新渲染，你才会看到数据已经变了，界面还停在旧位置。

**要改数据，让拥有数据的一方改。** 子组件通过回调提出请求，父组件决定改不改、怎么改。

## 回调也是一份 props {#callback-props}

`onDelete` 不是特殊语法，就是名字里带 `on` 的普通 prop。父组件传函数，子组件在合适的时机调用。

看父组件这一行：

```jsx
onDelete={() => handleDelete(message.id)}
```

传进去的是一个新函数。点击时，`MessageItem` 调用 `onDelete()`；这个新函数再去调用 `handleDelete(message.id)`。

为什么要包一层箭头函数？如果写成 `onDelete={handleDelete(message.id)}`，它在渲染时就被调用了，点击还没发生。页面一加载，alert 就弹出来。

那 `onDelete={handleDelete}` 行不行？行，但 `MessageItem` 调用 `onDelete()` 时没有参数，父组件拿不到是哪条留言。箭头函数的作用就是把 `message.id` 固定进去。

回调让子组件不必知道删除怎么实现。它只负责画按钮、在点击时通知父组件。以后父组件改成发请求、改成先弹确认框，`MessageItem` 一行都不用动。

## children 和默认值 {#children-and-defaults}

`children` 是另一种 prop：写在标签中间的内容。

页面上很快会有“写留言”和“全部留言”两个区域，它们的容器结构一样：一个 `<section>`，一个 `<h2>`，下面是内容。把这个容器抽出来：

```jsx
function BoardSection({ title, children }) {
  return (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
```

使用时，标签中间的内容会作为 `children` 传进去：

```jsx
<BoardSection title="全部留言">
  <ul>{/* 留言列表 */}</ul>
</BoardSection>
```

`children` 就是普通 prop，名字固定。它适合做卡片、弹层、布局这类容器：容器负责外框，不需要知道里面具体放什么。下一篇的完整例子会用 `BoardSection` 包住输入区和列表区。

默认值也有用。作者没填时显示“匿名”：

```jsx
function MessageItem({ author = "匿名", text = "（没有内容）", onDelete = () => {} }) {
  return (
    <li>
      <strong>{author}</strong>
      <p>{text}</p>
      <button onClick={onDelete}>删除</button>
    </li>
  );
}
```

规则和普通函数参数一样：只有 prop 是 `undefined` 时才用默认值。传 `null` 不会触发，`{text}` 会渲染成空白。

`MessageItem.defaultProps = { author: "匿名" }` 是老写法。React 19 已经移除了函数组件上的 `defaultProps`，新代码用解构默认值。类组件上的 `defaultProps` 仍然存在，但新项目基本不写类组件。

props 和 state 分工不同：`author`、`text` 由外面给，是 props；用户正在输入、还没提交的草稿，应该由输入框所在组件自己记，是 state。下一篇讲 state。

## 逐层转发到什么时候会烦 {#prop-drilling}

页面一大，中间层就会出现只负责转发的组件：

```jsx
function Board({ messages, onDelete }) {
  return <MessageList messages={messages} onDelete={onDelete} />;
}

function MessageList({ messages, onDelete }) {
  return (
    <ul>
      {messages.map((message) => (
        <MessageItem
          key={message.id}
          author={message.author}
          text={message.text}
          onDelete={() => onDelete(message.id)}
        />
      ))}
    </ul>
  );
}
```

`Board` 自己不用 `onDelete`，但必须接住再传下去。这种逐层转发叫 prop drilling。

什么时候开始难受？中间层超过两三层，或者每加一个 prop 都要改四五个函数的签名，而其中三个函数根本不使用它。这时有两个方向：

- 把列表和操作放进同一个父组件，减少层级。
- 用 Context 让深层组件直接读取，见 [状态提升与 Context](/learn/react-lifting)。

别急着上 Context。两三层、一个回调，显式传参更容易追：从 `MessageItem` 往上看，每一层的输入都写在签名里。Context 把连接藏起来，读代码时得先找 Provider。

判断标准很实际：你为了加一个 `onDelete` 改了四个文件，其中三个只是转发，那就该换结构；如果只改了两层，继续传更省事。

## 传错 props 的四种后果 {#props-pitfalls}

**“把 props 复制进 state，它就会跟着更新。”** 只在初始化时复制一次。父组件后来传了新值，state 不会自动同步。下面这段假设文件顶部已经导入了 `useState`：

```jsx
function MessageItem({ text }) {
  const [draft, setDraft] = useState(text);
  return <p>{draft}</p>;   // text 再变，draft 还是第一次的值
}
```

除非你明确要“只取初始值”，否则直接读 prop。

**“传函数和调用函数差不多。”** `onClick={onDelete}` 传的是函数本身，点击才执行；`onClick={onDelete()}` 在渲染时就执行。子组件再调用一次时，可能报 `onDelete is not a function`，因为执行结果不是函数。

**“`key` 也是 props，子组件能读到。”** 读不到。在子组件里打印 `props.key`，得到的是 `undefined`。`key` 被 React 拿去做列表身份。需要 id 就另传一个 `id={message.id}`。

**“默认值能接住 `null`。”** 不能。默认值只在 prop 为 `undefined` 时生效。传 `null` 就是 `null`，`{author}` 渲染为空。要同时兜住 `null` 和空字符串，按需要选 `author ?? "匿名"` 或 `author || "匿名"`：前者只换掉 `null` 和 `undefined`，后者连空字符串也换掉。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：父组件写 `<MessageItem author="阿岚" />`，子组件写 `function MessageItem({ author = "匿名" })`。显示什么？如果父组件写 `author={null}` 呢？

> **答案**
>
> 第一种显示“阿岚”。第二种显示空白：`null` 不是 `undefined`，不会触发默认值。
>
> 想同时兜住 `null`，写 `const name = author ?? "匿名"`，再用 `{name}`。

**第 2 题**：下面两行，哪一行会在渲染时就弹 alert？

```jsx
<button onClick={handleDelete}>删除</button>
<button onClick={handleDelete()}>删除</button>
```

> **答案**
>
> 第二行。`handleDelete()` 带括号，渲染到这一行就执行了。假设它长这样：
>
> ```jsx
> function handleDelete() {
>   alert("删除");
> }
> ```
>
> 页面一加载就弹。第一行传的是函数引用，点击时才执行。如果 `handleDelete` 需要 id，写成 `onClick={() => handleDelete(message.id)}`。

**第 3 题**：`Board -> MessageList -> MessageItem`，只有 `MessageItem` 用 `onDelete`，前两层都得转发。给出一种减少转发的做法，并说代价。

> **答案**
>
> 把 `messages` 和 `onDelete` 放进 `MessageList`，让 `Board` 只管布局；或者用 Context 提供 `onDelete`，`MessageItem` 直接消费。
>
> 前者的代价是状态位置变了，`Board` 以后要用这份数据就得再提升；后者让数据流不写在 props 签名里，读代码要先找 Provider，而且 Context 值一变，所有消费者都会重新渲染。层级不深时，继续显式传更清楚。

## 继续阅读 {#related}

- [React 组件与 JSX](/learn/react-components)
- [State、重新渲染与状态快照](/learn/react-state)
- [状态提升与 Context](/learn/react-lifting)
- [为 React props 与事件声明类型](/learn/ts-react)

## 参考资料 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
