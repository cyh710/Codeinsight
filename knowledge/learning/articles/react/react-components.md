# React 组件与 JSX

## 组件是返回界面的函数 {#component-as-function}

学完这一篇，你能用 Vite 建一个 React 项目，写出自己的组件，并看懂 JSX 被编译成了什么。

留言板的每一条留言都长得一样：作者一行、内容一行。你先写了一行，然后复制、粘贴、再复制。三条还能忍，等到要改配色，你发现三处都得改。

React 把这些重复的界面收进一个函数：你给它输入，它返回这段界面。这个函数叫组件。写一次 `<MessageItem />`，用三次，改一处就全改。

组件和普通函数只有两个约定：名字首字母大写，返回值是一段 JSX。其余的——参数、返回值、调用——和你写过的 JavaScript 函数一样。

这一篇先搭出留言列表；输入框、提交和状态在后面三篇逐步加上。

## 用 Vite 跑起第一块界面 {#vite-first-run}

先建项目。在终端里跑：

```bash
npm create vite@latest message-board -- --template react
cd message-board
npm install
npm run dev
```

第一次运行会问是否安装 `create-vite`，输入 `y`。脚手架如果问你要不要用实验版本，选默认的 React + JavaScript。终端会打印一个本地地址，通常是 `http://localhost:5173`，用浏览器打开。

把 `src/App.jsx` 的内容整个换掉：

```jsx
function Hello() {
  return <h1>留言板</h1>;
}

function MessageItem() {
  return (
    <li>
      <strong>小林</strong>
      <p>第一条留言</p>
    </li>
  );
}

export default function App() {
  return (
    <main>
      <Hello />
      <ul>
        <MessageItem />
        <MessageItem />
        <MessageItem />
      </ul>
    </main>
  );
}
```

保存。Vite 会在浏览器里直接替换掉旧界面，不用手动刷新。你应该看到：

```
留言板
小林
第一条留言
小林
第一条留言
小林
第一条留言
```

三行一模一样。这不是 bug，是同一段组件代码被用了三次。

## 把重复的留言行收成 MessageItem {#extract-message-item}

第一步，`Hello` 和 `MessageItem` 都是普通 JavaScript 函数。`function Hello() {...}` 只是定义，和 Python 的 `def` 一样，定义的时候不显示任何东西。

第二步，`<Hello />` 是调用。JSX 里写一个自定义组件，React 会调用这个函数，把它返回的元素放进那个位置。三个 `<MessageItem />` 就是三次调用。

第三步，返回值不是 HTML 字符串。`<li>` 会被转换成一个描述界面的 JavaScript 对象。React 拿这些对象算出最终的页面结构，再决定要不要动 DOM。

第四步，`App` 只负责组合。它自己返回 `<main>`，里面放 `Hello` 和三个 `MessageItem`。页面就是组件套组件，最外层的 `App` 由 `src/main.jsx` 挂到页面上。

`src/main.jsx` 里已经写好了 `import App from './App.jsx'` 和 `createRoot(...)`。你只改 `App.jsx` 就能看到效果。

把其中一个 `<MessageItem />` 改成 `<MessageItem></MessageItem>`，结果完全一样。自闭合只是没有子内容时的简写。

## JSX 编译后长什么样 {#jsx-compiled}

浏览器不认识 JSX。Vite 在开发时把它转成普通 JavaScript，再交给浏览器执行。

这一行：

```jsx
const title = <h1 className="title">留言板</h1>;
```

在旧的转换方式里会变成：

```js
const title = React.createElement("h1", { className: "title" }, "留言板");
```

三个参数是标签名、属性对象、子内容。换成组件，第一个参数就是函数本身：

```jsx
const item = <MessageItem author="小林" />;
```

```js
const item = React.createElement(MessageItem, { author: "小林" });
```

注意这里没有引号。`"h1"` 是字符串，浏览器按原生标签处理；`MessageItem` 是变量，React 会调用它。

React 17 之后，Vite 默认用新的 JSX 转换，生成的是从 `react/jsx-runtime` 导入的 `_jsx(...)`。函数名变了，“类型 + 属性 + 子内容”这个结构没变。

这三件事都和编译结果有关：

- `className` 而不是 `class`，因为 JSX 属性最终是对象的键，`class` 在 JavaScript 里是保留字。`<label>` 的 `for` 也要写 `htmlFor`。
- 花括号里放表达式：`<p>{1 + 1}</p>` 显示 2，不是显示 `{1 + 1}`。
- 所有标签必须闭合：`<input />`、`<br />`，不能像 HTML 那样只写 `<input>`。

还有一条容易误会：JSX 不是把字符串拼成 HTML。`{userInput}` 一定按文本插入，用户输入 `<script>` 也只会看到这几个字符。要真的插入 HTML，得显式用 `dangerouslySetInnerHTML`，名字里的 dangerously 不是装饰。

## 一个根节点与大写字母 {#root-and-capital}

组件必须返回一个根节点。下面这样写会直接编译失败：

```jsx
function Bad() {
  return (
    <h1>留言板</h1>
    <p>欢迎</p>
  );
}
```

报错是 `Adjacent JSX elements must be wrapped in an enclosing tag. Did you want a JSX fragment <>...</>?`。两个并列元素没有共同的父级。

加一个真容器可以：

```jsx
return (
  <div>
    <h1>留言板</h1>
    <p>欢迎</p>
  </div>
);
```

用 Fragment 也行，它不会在 DOM 里留下多余节点：

```jsx
return (
  <>
    <h1>留言板</h1>
    <p>欢迎</p>
  </>
);
```

`<>...</>` 是 `<Fragment>` 的简写。列表和表格里尤其需要它：`<ul>` 的直接子元素只能是 `<li>`，多包一层 `<div>` 会把结构弄坏。

另一个硬规则是首字母大写。`<MessageItem />` 编译成 `createElement(MessageItem, ...)`；`<messageItem />` 编译成 `createElement("messageItem", ...)`。

小写那个会被当成原生标签。浏览器造一个叫 `messageItem` 的未知 DOM 元素，你的函数一次都不会执行。界面上什么都没有，控制台也不一定报错，很容易盯半天。

## 什么时候该拆组件 {#when-to-split}

出现下面任一情况，就值得拆：

- 同一段结构写了第二遍。复制第二遍时拆，比复制到第五遍再拆便宜。
- 这块界面有名字，你能用一句话说清它显示什么，比如“一条留言”。
- 一个函数里塞了互不相关的几块区域，改一处要读完整段才能确认没影响别处。

反方向也有成本。给每个 `<div>` 都包一层组件，读代码要跳五六个文件，还没看到一条留言长什么样。拆分的边界是职责，不是行数。

还有一条容易忽略：不要把组件定义在另一个组件里面。

```jsx
function App() {
  function MessageItem() {
    return <li>一条留言</li>;
  }
  return <MessageItem />;
}
```

`App` 每渲染一次，都会创建一个新的 `MessageItem` 函数。React 比较类型时发现不是同一个函数，会把整棵子树卸载再重建。子组件里如果有输入框或 state，内容会跟着丢。把组件定义移到模块顶层。

组件函数只该做一件事：根据输入返回界面。不要在函数体里发请求、写 `localStorage`、改全局变量。开发模式下，StrictMode 会故意多执行一次组件函数来暴露这类问题，你会看到请求发了两遍。请求和订阅放到事件处理或 Effect 里，见 [Effect、依赖与清理](/learn/react-effects)。

## 四种写错法的现场表现 {#components-pitfalls}

**“JSX 就是 HTML，直接粘过来就行。”** 属性名、闭合规则、注释都不一样。`class` 写 `className`，`for` 写 `htmlFor`，`style` 传对象 `{ color: "red" }` 而不是字符串，注释写 `{/* ... */}`。粘一段 HTML 进 JSX，最先撞上的通常是未闭合的 `<input>`。

```jsx
<p className="tip" style={{ color: "red" }}>提示</p>
```

**“组件名小写只是风格。”** 不是风格，是类型判断。把 `MessageItem` 改成 `messageItem` 跑一次，列表会变成空的未知标签，函数不执行。

**“必须用 `<div>` 包住所有东西。”** 不必。Fragment 不产生 DOM 节点。只有需要给这块区域加样式或参与布局时，才值得用 `<div>`。

**“在组件函数里发请求没关系，反正只渲染一次。”** 开发模式的 StrictMode 会让组件函数执行两次。把 `fetch` 写在函数体里，网络面板里就是两条请求。渲染只算界面，副作用另找地方。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面三个组件，哪个编译不过？为什么？

```jsx
function A() { return <h1>hi</h1>; }
function B() { return (<h1>hi</h1><p>there</p>); }
function C() { return (<><h1>hi</h1><p>there</p></>); }
```

> **答案**
>
> B。两个并列元素没有共同父级，Babel 会报 `Adjacent JSX elements must be wrapped in an enclosing tag`。
>
> A 只有一个根节点，合法；C 用 Fragment 包住了两个元素，也合法。B 改成 `return (<><h1>hi</h1><p>there</p></>);` 就能过。

**第 2 题**：`<messageItem />` 和 `<MessageItem />` 有什么区别？

> **答案**
>
> 首字母决定它是原生标签还是组件。`<MessageItem />` 编译成 `createElement(MessageItem, ...)`，React 调用这个函数；`<messageItem />` 编译成 `createElement("messageItem", ...)`，React 造一个同名 DOM 元素，函数不会执行。

**第 3 题**：把 `Hello` 改成接收 `name`，显示“你好，小林”，父组件传入 `name="小林"`。写出两段代码。

> **答案**
>
> ```jsx
> function Hello({ name }) {
>   return <h1>你好，{name}</h1>;
> }
>
> export default function App() {
>   return <Hello name="小林" />;
> }
> ```
>
> 屏幕上显示 `你好，小林`。`{ name }` 是参数解构，父组件写的属性会变成一个对象传进来。这就是下一篇要讲的 props。

## 继续阅读 {#related}

- [HTML：页面的结构与语义](/learn/web-html)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [Props：组件之间怎样传数据](/learn/react-props)
- [State、重新渲染与状态快照](/learn/react-state)

## 参考资料 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
