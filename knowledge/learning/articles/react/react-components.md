# React 组件与 JSX

## 先建立直觉 {#overview}

React 用组件组织界面。组件可以小到一个按钮，也可以大到一个对话区；它接收输入，描述当前应该显示的内容。JSX 是一种便于在 JavaScript 中描述界面的语法，它看起来像 HTML，但会经过构建工具转换。

## 原理与执行过程 {#mechanism}

理解组件可以先把它看成“根据输入返回界面描述的函数”。React 调用组件计算树，再根据变化更新实际界面。组件名字以大写开头，浏览器原生标签使用小写。渲染过程应保持纯净：不要在函数主体中直接发网络请求、写存储或修改外部数据。那些副作用需要明确的事件或生命周期安排。

组件树与 DOM 树相关但不完全相同：一个组件可以返回多个元素，也可以组合其他组件。阅读工程时先看页面由哪些区域组成，再看区域接收什么数据和动作，通常比从每个标签的属性开始更容易建立整体理解。

## 跟着例子理解 {#example}

```jsx
function Greeting({ name }) {
  return <p>你好，{name}</p>;
}

export default function App() {
  return (
    <main>
      <h1>项目学习</h1>
      <Greeting name="小林" />
    </main>
  );
}
```

## 一步一步读懂 {#walkthrough}

第一步，App 描述主要区域以及标题。第二步，Greeting 是自定义组件，name 是传给它的输入。第三步，Greeting 读取 name 并返回段落。花括号中的内容是 JavaScript 表达式，所以可以把字符串数据放进界面。这里的 Greeting 只是渲染描述，不代表立即创建一个独立运行的进程。

如果把 name 改成另一个值，下一次渲染得到的段落内容也会改变。可以试着把问候语移入普通字符串，再比较 JSX 中引号和花括号的作用。更进一步，一个 KnowledgePanel 可以接收文章数据并组合目录、正文和相关入口，而不需要把所有内容都写在 App 里。

## 常见误解 {#pitfalls}

JSX 不是任意 HTML 字符串，插入普通字符串时 React 会按文本处理。自定义组件用小写名字可能被当作原生标签。组件函数不应在另一个组件每次渲染时临时定义并承担需要稳定身份的状态。开发模式下看到额外渲染，也不能直接认定用户发起了两次操作。

## 工程中的取舍 {#tradeoffs}

组件拆分应围绕职责和可复用边界。太大的组件难以追数据流，过细拆分又会让读者频繁跳文件。让展示组件接收明确 props，把网络请求与共享状态放在可追踪的位置，更容易测试。教材中的最小组件帮助理解机制；真实工作台还需要处理加载、空结果、失败和项目切换。

## 接着探索 {#related}

- [HTML：页面的结构与语义](/learn/web-html)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [Props：组件之间怎样传数据](/learn/react-props)
- [State、重新渲染与状态快照](/learn/react-state)
- [为 React props 与事件声明类型](/learn/ts-react)

## 来源与版本 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
