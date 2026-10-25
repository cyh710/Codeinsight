# 为 React props 与事件声明类型

## 一块留言卡片要接收什么 {#overview}

读完这一篇，你能给 Button 和 MessageItem 写出准确的 props、children 与事件类型，并看懂 tsc 报的 JSX 错误。

留言板页面上有两块 UI：一个提交按钮，一个消息列表项。按钮需要文字和一个点击动作；列表项需要一条 `Message` 和一个删除动作。

先决定每个组件收什么，再写类型。收得越准，调用方漏传、传错时越早暴露。

## Button 的 children 与回调 {#button-props}

新建 `board.tsx`：

```tsx
import type { ReactNode } from "react";

type ButtonProps = {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
};

function Button({ children, onClick, disabled = false }: ButtonProps) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export { Button };
```

先编译一次：

```bash
npx tsc board.tsx --noEmit --strict --jsx react-jsx --target es2022 --module esnext --moduleResolution bundler --lib dom,es2022
```

你应该看到：没有任何输出。tsc 通过时保持沉默。

`ButtonProps` 就是这个组件的使用说明书。`children` 和 `onClick` 必填，`disabled` 可选且有默认值。

- `children: ReactNode` 表示"React 能渲染的内容"：字符串、JSX 元素、数组、`null` 都行。写成 `children: string` 就只能传纯文本，传 `<strong>发布</strong>` 会报错。
- `onClick: () => void` 表示调用方给一个"没有参数、不返回东西"的函数。按钮只负责在点击时调用它，不关心它内部做什么。
- `disabled?: boolean` 的问号表示可以不传；解构时 `disabled = false` 给它默认值。
- `type="button"` 防止按钮在表单里默认触发提交。

调用方这样用：

```tsx
<Button onClick={() => console.log("发布")}>发布</Button>
```

如果漏了回调，或者把字符串传给 `onClick`，tsc 会直接拦：

```tsx
const missing = <Button>发布</Button>;
// TS2741: Property 'onClick' is missing in type '{ children: string; }' but required in type 'ButtonProps'.

const wrong = <Button onClick="发布">发布</Button>;
// TS2322: Type 'string' is not assignable to type '() => void'.
```

把这两行临时接在 `board.tsx` 末尾，再编译一次：

```bash
npx tsc board.tsx --noEmit --strict --jsx react-jsx --target es2022 --module esnext --moduleResolution bundler --lib dom,es2022
```

你应该看到：

```
board.tsx(19,18): error TS2741: Property 'onClick' is missing in type '{ children: string; }' but required in type 'ButtonProps'.
board.tsx(22,23): error TS2322: Type 'string' is not assignable to type '() => void'.
```

错误发生在调用处，不需要等到浏览器里点一下才发现按钮没反应。这就是 props 类型的价值。

## MessageItem 的数据与删除动作 {#message-item}

接着在同一个文件里写列表项：

```tsx
type Message = {
  id: string;
  author: string;
  content: string;
  editedAt: string | null;
};

type MessageItemProps = {
  message: Message;
  onDelete: (id: string) => void;
};

function MessageItem({ message, onDelete }: MessageItemProps) {
  return (
    <li>
      <strong>{message.author}</strong>
      <p>{message.content}</p>
      {message.editedAt !== null && <small>编辑于 {message.editedAt}</small>}
      <Button onClick={() => onDelete(message.id)}>删除</Button>
    </li>
  );
}
```

`MessageItemProps` 把输入分成两类：`message` 是要显示的数据，`onDelete` 是用户可以触发的动作。回调的参数写明是 `string`，意思是"子组件会把要删的 id 交出去，具体删哪条、怎么删由父组件决定"。

列表这样渲染：

```tsx
function MessageList({ messages }: { messages: Message[] }) {
  return (
    <ul>
      {messages.map((message) => (
        <MessageItem
          key={message.id}
          message={message}
          onDelete={(id) => console.log(`删除 ${id}`)}
        />
      ))}
    </ul>
  );
}
```

`key` 由 React 使用，不属于 `MessageItemProps`。不要把它加进 props 类型，也不要在组件里读它。

`onClick={() => onDelete(message.id)}` 是包了一层函数。点击时才调用 `onDelete`，并把这条留言的 id 传出去。如果写成 `onClick={onDelete(message.id)}`，渲染阶段就会执行，删除动作会提前发生。

`editedAt !== null` 是显式判断。这里不用 `message.editedAt && ...`，因为空字符串也是假值；显式写 `null` 比较，读代码的人能直接看出这个字段的约定是"字符串或 null"。空字符串应该在接口边界被校验掉，不要让组件同时猜两种空值。

## 输入框和表单事件该标什么类型 {#event-types}

把文件顶部的导入补成：

```tsx
import { useState } from "react";
import type { ChangeEvent, FormEvent, MouseEvent, ReactNode } from "react";
```

然后写表单：

```tsx
function MessageForm() {
  const [draft, setDraft] = useState("");

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    setDraft(event.target.value);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDraft("");
  }

  function handleClear(event: MouseEvent<HTMLButtonElement>) {
    console.log(event.currentTarget.tagName);
    setDraft("");
  }

  return (
    <form onSubmit={handleSubmit}>
      <input value={draft} onChange={handleChange} />
      <Button onClick={() => console.log(draft)}>发布</Button>
      <button type="button" onClick={handleClear}>
        清空
      </button>
    </form>
  );
}
```

事件类型不是随便挑的：

| 事件 | 类型 | 你能安全读什么 |
|---|---|---|
| 输入框内容变化 | `ChangeEvent<HTMLInputElement>` | `event.target.value`，类型是 `string` |
| 表单提交 | `FormEvent<HTMLFormElement>` | `event.preventDefault()` |
| 按钮点击 | `MouseEvent<HTMLButtonElement>` | `event.currentTarget`，类型是按钮元素 |

这些类型来自 React 的合成事件，不是浏览器原生的 `Event`。把参数标成原生 `Event`，`target.value` 和 `currentTarget` 的元素类型都会丢掉。

写成独立函数的处理器需要显式标注参数类型。写成内联的 `onChange={(event) => setDraft(event.target.value)}` 时，tsc 会根据 `onChange` 这个 prop 自动推断 `event` 的类型，不用手写。

`useState("")` 会把状态推断成 `string`，所以 `setDraft(42)` 会报 `TS2345: Argument of type 'number' is not assignable to parameter of type 'SetStateAction<string>'.`。初始值写 `useState<string | null>(null)` 时，状态就是 `string | null`，存空值也不用绕。

不要为了省事把事件参数写成 `any`。写成 `any` 后，`event.target.value`、`event.preventDefault()` 都不再有提示和检查，拼错属性也要到运行时才发现。

## 返回类型写不写 JSX.Element {#return-type}

组件的返回类型通常不用写。tsc 会从 JSX 推断出来，编辑器悬停时能看到推断出的 JSX 元素类型：

```tsx
function MessageItem({ message, onDelete }: MessageItemProps) {
  return (
    <li>
      <strong>{message.author}</strong>
      <Button onClick={() => onDelete(message.id)}>删除</Button>
    </li>
  );
}
```

不写返回类型，组件以后多返回一个 `null` 或在分支里换结构，都不用改签名。

真要写，得注意 React 19 的类型里 `JSX` 不再是随手可用的全局名字：

```tsx
function MaybeEmpty({ message }: { message: Message }): JSX.Element {
  return <p>{message.content}</p>;
}
// TS2503: Cannot find namespace 'JSX'.
```

补上类型导入后，另一个问题会冒出来：

```tsx
import type { JSX } from "react";

function MaybeEmpty({ message }: { message: Message }): JSX.Element {
  if (message.content === "") return null;
  return <p>{message.content}</p>;
}
// TS2322: Type 'null' is not assignable to type 'Element'.
```

正确写法是让注解反映真实返回值：

```tsx
import type { JSX } from "react";

function MaybeEmpty({ message }: { message: Message }): JSX.Element | null {
  if (message.content === "") return null;
  return <p>{message.content}</p>;
}
```

大多数组件不需要这一行。只有组件确实会返回 `null`、或者你想强制它只能返回某一种结构时，显式注解才有用。不同 React 版本的 `@types/react` 对 `JSX` 命名空间的处理不一样，跟项目里实际装的版本走，别照抄旧教程。

## 调用时机、事件目标与 any 的三个坑 {#pitfalls}

**"`onClick={handleClick()}` 只是写法不同，点了都会调用 `handleClick`。"** 不一样。前者在渲染时就调用了函数，把返回值当成事件处理器：

```tsx
function handleClick() {
  console.log("点了");
}

<Button onClick={handleClick()}>发布</Button>
// TS2322: Type 'void' is not assignable to type '() => void'.
```

渲染一次就打印一次"点了"，点击按钮反而不触发。正确写法是传函数本身：

```tsx
const buttons = (
  <>
    <Button onClick={handleClick}>发布</Button>
    <Button onClick={() => onDelete(message.id)}>删除</Button>
  </>
);
```

需要传参数时，用箭头函数包一层。tsc 能抓住返回 `void` 的写法；如果 `handleClick` 恰好返回一个函数，类型检查可能通过，但调用时机仍然是错的。

**"`event.target` 和 `event.currentTarget` 是一回事。"** 在按钮点击里不是。`target` 是实际被点到的节点，可能是按钮里的图标或文字节点；`currentTarget` 是挂载处理器的那个按钮：

```tsx
function handleDelete(event: MouseEvent<HTMLButtonElement>) {
  console.log(event.target.value);
  // TS2339: Property 'value' does not exist on type 'EventTarget'.
  console.log(event.currentTarget.disabled); // boolean
}
```

React 的 `MouseEvent<HTMLButtonElement>` 里，`currentTarget` 的类型是 `EventTarget & HTMLButtonElement`，能读按钮属性；`target` 只保证是 `EventTarget`，因为点击可能落在子元素上。要拿按钮自己的 `dataset`、`disabled`，用 `currentTarget`。

输入框的 `ChangeEvent<HTMLInputElement>` 是特例：React 把它的 `target` 也收窄成了输入框，所以 `event.target.value` 能通过。不要把这一条推广到所有事件。

**"props 写成 any 最省事。"** 省掉的是检查，不是复杂度：

```tsx
function BadButton(props: any) {
  return <button onClick={props.onClik}>{props.childrn}</button>;
}
// tsc 通过：onClik 和 childrn 都不检查
```

这段能通过 tsc，但 `onClik` 和 `childrn` 都拼错了。运行时 `props.onClik` 是 `undefined`，点击没有任何反应。换成 `ButtonProps`，两处拼写会在编译时被指出。

## props 越窄，组件越好复用 {#tradeoffs}

窄不是少传字段，而是只传组件用得到的字段和动作。

`MessageItem` 接收一条完整的 `Message`，因为它要显示作者、正文和编辑时间。如果只显示作者，传 `author: string` 就够了，不必把整个对象塞进去。传得越宽，组件和数据结构绑得越死，测试时也要造更多无关字段。把整个 store 传给每个子组件，问题更大。

回调的签名决定子组件能告诉父组件什么：

- `onDelete: () => void` 适合父组件已经知道要删哪条，子组件只负责报告"点了删除"。
- `onDelete: (id: string) => void` 把 id 交给父组件，同一个子组件可以用在多个列表里。

两种都能用，但签名要写清。不要在父组件里靠闭包猜子组件内部状态。

可选 prop 只给真的可选的东西。`disabled?: boolean` 合理；`message?: Message` 会让组件每个地方都要处理缺失，通常说明数据还没准备好，应该在父组件或接口边界解决。外部 API 返回的数据要在这里校验，props 类型只在编译期管用。

组件泛型只有在 props 之间确实存在类型关系时才值得写，比如 `items: T[]` 配 `renderItem: (item: T) => ReactNode`。给 Button 加类型参数不会让它更通用，只会让调用方多读一层签名。

不必为了"规范"去写 `React.FC<Props>`。普通函数加上 props 类型，推断出来的结果一样，还少一层包装。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：给 `Button` 加一个可选 prop `variant`，只允许 `"primary"` 或 `"danger"`，默认 `"primary"`。props 类型和组件签名怎么写？

> **答案**
>
> ```tsx
> type ButtonProps = {
>   children: ReactNode;
>   onClick: () => void;
>   disabled?: boolean;
>   variant?: "primary" | "danger";
> };
>
> function Button({
>   children,
>   onClick,
>   disabled = false,
>   variant = "primary",
> }: ButtonProps) {
>   return (
>     <button
>       type="button"
>       className={variant}
>       onClick={onClick}
>       disabled={disabled}
>     >
>       {children}
>     </button>
>   );
> }
> ```
>
> 联合类型把可选值写死，调用方传 `"warning"` 会报 `TS2322`；默认值让不传时也有确定结果。

**第 2 题**：为什么 `onClick={handleClick()}` 是错的？如果 `handleClick` 返回 `void`，tsc 报什么？

> **答案**
>
> 因为它立即调用了 `handleClick`，把返回值传给了 `onClick`，而不是把函数本身传过去。渲染时就会执行一次，点击时反而不执行。
>
> 返回 `void` 时，tsc 报 `TS2322: Type 'void' is not assignable to type '() => void'.`。改成 `onClick={handleClick}` 或 `onClick={() => handleClick()}`。

**第 3 题**：一个按钮里包着 `<span>删除</span>`，点击 `span` 时，想读按钮上的 `data-id`，应该用 `event.target` 还是 `event.currentTarget`？

> **答案**
>
> 用 `event.currentTarget`。它指向挂载点击处理器的按钮，类型是 `HTMLButtonElement`，能读 `dataset.id`。
>
> `event.target` 是实际被点的 `span`，类型只保证是 `EventTarget`，没有 `dataset` 这种按钮属性。需要区分"点到了哪个子元素"时才用 `target`。

## 继续阅读 {#related}

- [TypeScript 的类型注解与推断](/learn/ts-types)
- [interface、type 与结构契约](/learn/ts-interfaces)
- [Props：组件之间怎样传数据](/learn/react-props)
- [事件处理与受控输入](/learn/react-events)

## 参考资料 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
