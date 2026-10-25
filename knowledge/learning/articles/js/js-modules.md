# JavaScript 模块与 import/export

## 一个文件装不下留言板了 {#why-split}

学完这一篇，你能把留言板拆成 store.js 和 main.js，用 export 和 import 拼回去，还能看懂导入拿到的为什么是绑定。

一开始，留言板的所有代码都在一个 `<script>` 里：存留言的数组、提交表单的处理、渲染列表的函数、点赞的逻辑。文件涨到几百行后，改渲染时很容易碰到数据那块，改数据时又怕影响提交逻辑。更麻烦的是，你没法只把"存留言"这段拿去另一个页面复用，因为它和整个文件绑在一起。

拆文件不是为了少写几个字，而是为了给每组代码一个明确的出口：哪些东西允许别人用，哪些是内部细节。`store.js` 只负责留言数据，`main.js` 只负责把数据变成输出。两个文件之间只通过事先说好的导出接口打交道。

## 建两个文件：store.js 与 main.js {#two-files}

新建一个文件夹 `board`，在里面放三个文件：

```
board/
  package.json
  store.js
  main.js
```

先写 `package.json`：

```json
{
  "type": "module"
}
```

这个文件里没有依赖，也不需要 `npm install`。`"type": "module"` 只告诉 Node：这个目录下的 `.js` 文件按 ES 模块解析，可以使用 `import` 和 `export`。

写 `store.js`：

```js
// store.js
const messages = [
  { id: 1, author: "小林", text: "还有货吗？" },
  { id: 2, author: "阿岚", text: "能便宜点吗？" },
];

export function getMessages() {
  return messages;
}

export function addMessage(author, text) {
  const message = { id: messages.length + 1, author, text };
  messages.push(message);
  return message;
}

export default function countMessages() {
  return messages.length;
}
```

写 `main.js`：

```js
// main.js
import countMessages, { getMessages, addMessage } from "./store.js";

console.log("一开始有", countMessages(), "条留言");

addMessage("小林", "几天发货？");

for (const message of getMessages()) {
  console.log(`${message.id}. ${message.author}：${message.text}`);
}

console.log("现在有", countMessages(), "条留言");
```

在 `board` 目录里运行：

```bash
node main.js
```

你应该看到：

```
一开始有 2 条留言
1. 小林：还有货吗？
2. 阿岚：能便宜点吗？
3. 小林：几天发货？
现在有 3 条留言
```

第一步，`store.js` 里的 `messages` **没有** `export`，所以它只在模块内部可见。外面的代码不能直接拿这个数组，只能通过 `getMessages` 和 `addMessage` 操作它。这是模块的基本用法：把内部状态藏起来，只暴露函数。

第二步，`addMessage` 往模块自己的数组里 `push` 一条，并返回新留言。`messages.length + 1` 在这里够用，因为示例只有追加、没有删除；真实项目应该用不会重复的 id 生成方式。

第三步，`main.js` 用一条 `import` 同时拿了默认导出和两个具名导出。然后它先打印条数，再添加留言，再遍历输出。`getMessages()` 每次返回的都是同一个数组，所以第三次循环能看到刚添加的那条。

路径 `"./store.js"` 是从 `main.js` 所在目录算的，不是从你敲命令的目录算的。所以在上一级目录运行 `node board/main.js` 也能找到 `store.js`。Node 的 ES 模块要求写全扩展名：`"./store.js"` 不能省成 `"./store"`。

没有 `"type": "module"` 时，旧一点的 Node 会把 `.js` 当 CommonJS，`import` 会报 `SyntaxError: Cannot use import statement outside a module`。Node 22.7 以后能自动识别一部分模块语法，但显式写 `type` 不用赌版本。另一个办法是把文件后缀改成 `.mjs`，Node 会直接按模块处理，这时可以不要 `package.json`。

## default 导出和具名导出的区别 {#default-vs-named}

`store.js` 同时用了两种导出：

- `export function getMessages` 和 `export function addMessage` 是**具名导出**，名字由导出方定。
- `export default function countMessages` 是**默认导出**，一个模块只能有一个。

导入方的写法必须对应：

| 写法 | 拿到什么 | 名字由谁定 |
|---|---|---|
| `import countMessages from "./store.js"` | 默认导出 | 导入方随便起名 |
| `import { getMessages } from "./store.js"` | 具名导出 `getMessages` | 必须和导出名一致 |
| `import { getMessages as list } from "./store.js"` | 同上，但本地改叫 `list` | 导出名一致，本地可改 |
| `import * as store from "./store.js"` | 所有导出，包括 `default` | 挂在 `store` 对象上 |

新建 `imports.js` 验证一下：

```js
// imports.js
import countMessages, { getMessages as list } from "./store.js";
import * as store from "./store.js";

console.log("默认导出是函数吗:", typeof countMessages);
console.log("具名导出是函数吗:", typeof store.getMessages);
console.log("别名拿到的也是同一个函数:", list === store.getMessages);
console.log("default 就是那个默认导出:", store.default === countMessages);
console.log("现在有几条:", countMessages());
```

在 `board` 目录里运行 `node imports.js`：

```
默认导出是函数吗: function
具名导出是函数吗: function
别名拿到的也是同一个函数: true
default 就是那个默认导出: true
现在有几条: 2
```

`import * as store` 把模块的所有导出装进一个命名空间对象。默认导出也在里面，键名是 `"default"`。所以 `store.default` 和直接默认导入的 `countMessages` 是同一个函数。

默认导出不是特殊的东西，它只是名字叫 `"default"` 的导出。`import countMessages from` 是"取 default 并起个本地名字"的简写。

两种写法不能混着套。`store.js` 只提供了默认导出 `countMessages`，没有同名的具名导出。如果你写：

```js
import { countMessages } from "./store.js";
```

模块链接阶段就会失败，报错里会出现 `The requested module './store.js' does not provide an export named 'countMessages'`。这段代码一行都不会执行，因为错误发生在开始运行之前。

默认导出的名字由导入方决定，所以同一个东西在两个文件里可能叫不同名字，全局搜索时不好找。具名导出必须对得上名字，重构工具和编辑器更容易追踪。只有"这个模块主要就提供一个东西"时，默认导出才比较顺手；其余情况用具名导出更清楚。

## 导入拿到的是绑定，不是拷贝 {#live-bindings}

新建 `board-state.js`：

```js
// board-state.js
export let messageCount = 2;

export function addMessage() {
  messageCount += 1;
}
```

再新建 `watch-count.js`：

```js
// watch-count.js
import { messageCount, addMessage } from "./board-state.js";

console.log("加之前:", messageCount);
addMessage();
console.log("加之后:", messageCount);
```

运行 `node watch-count.js`：

```
加之前: 2
加之后: 3
```

如果导入的是拷贝，第二行应该还是 2。它变成 3，因为 `watch-count.js` 里的 `messageCount` 不是数字 2 的副本，而是指向 `board-state.js` 里那个变量的**实时绑定**。导出方把变量加一，导入方再读，读到的就是新值。

从导入方看，这个绑定是只读的。你可以把 `messageCount` 读出来，但不能给它赋值：

```js
import { messageCount } from "./board-state.js";
messageCount = 10;
```

把这两行存成 `bad-assign.js`，运行会抛 `TypeError: Assignment to constant variable.`。导出方用的是 `let`，可那是对导出方而言的；对导入方来说，这个绑定不能换。要改值，必须调用导出方提供的函数，比如 `addMessage()`。这也是一种保护：状态的修改入口留在拥有它的模块里。

同样的规则适用于对象。假如一个模块 `export const messages = [...]`，导入方拿到的不是数组副本，而是同一个数组的引用。直接 `push` 会改到模块内部状态，所有导入这个模块的地方都看得见。想让调用方改不到，导出时就要复制，或者只导出查询函数。

## 循环依赖：读到一半的模块 {#circular-imports}

两个模块互相导入并不罕见：`a.js` 需要 `b.js` 的函数，`b.js` 又需要 `a.js` 的数据。新建一对文件试试。

`a.js`：

```js
// a.js
import { reply } from "./b.js";

export function boardName() {
  return "留言板";
}

console.log(reply());
```

`b.js`：

```js
// b.js
import { boardName } from "./a.js";

export function reply() {
  return `欢迎来到${boardName()}`;
}
```

运行 `node a.js`，输出：

```
欢迎来到留言板
```

没有死循环，因为模块系统不会重新执行已经在加载中的模块。过程是这样：`a.js` 开始执行前，先加载 `b.js`；`b.js` 又需要 `a.js`，但发现它已经在加载，于是只把 `a.js` 的导出绑定交给 `b.js`，不再执行一遍。`b.js` 定义好 `reply` 就结束，回到 `a.js` 继续执行，这时 `boardName` 已经可用，调用 `reply()` 成功。

这个例子能跑，有两个前提：`boardName` 是函数声明，而且 `b.js` 没有在顶层立刻调用它。

函数声明在模块体开始执行前就初始化好了，所以在循环里也能被对方引用。`const` 和 `let` 不一样，它们要等声明那一行执行到才有值。如果 `a.js` 导出的是 `export const boardName = "留言板"`，而 `b.js` 在顶层直接读 `boardName`，运行会报：

```
ReferenceError: Cannot access 'boardName' before initialization
```

因为 `b.js` 比 `a.js` 先执行，读的时候 `a.js` 的那个声明还没轮到。`var` 会得到 `undefined`，不报错，但同样不是你想要的值。

循环依赖不是语法错误，但它把"模块什么时候初始化好"变成了需要推理的问题。能避开就避开：把两边都要用的部分抽到第三个模块，让依赖保持单向。确实避不开时，只在函数体里使用对方的值，不要在模块顶层立刻读取；把实际调用推迟到两个模块都加载完之后。

## 模块边界不是进程边界 {#boundary}

模块把代码分开了，但它们**没有**被分到不同的进程或线程里。同一个 Node 进程里的所有模块，共享同一个全局对象、同一个事件循环、同一份内存；同一个网页里的所有模块，共享同一个 `window` 和 DOM。

先看模块只执行一次这件事。新建 `double-import.js`：

```js
// double-import.js
import countA, { addMessage } from "./store.js";
import countB from "./store.js";

console.log("两个名字是同一个函数吗:", countA === countB);

addMessage("阿岚", "再问一句");
console.log("加一条之后:", countA(), countB());
```

运行 `node double-import.js`：

```
两个名字是同一个函数吗: true
加一条之后: 3 3
```

`store.js` 被写了两条 `import`，但模块只求值一次，结果被缓存。两个名字拿到的是同一个默认导出函数，背后也是同一个 `messages` 数组。`addMessage` 加的这条，两个名字都看得见。

这带来几个实际后果：

- 被导入模块的**顶层代码会执行**，即使你只用它的一个函数。如果 `store.js` 顶层写了 `console.log`、开了定时器、连了数据库，导入就会触发它们。
- 一个模块的顶层代码抛异常，整个导入链都会失败。一个模块里写了死循环，整个进程或页面都会停住。
- 模块之间共享状态，一个模块改了导出的对象，其他导入方看到的是改过的版本。
- 每次重新运行 `node main.js` 都是一个新进程，模块状态从初始值重新开始。模块变量不是数据库，不能拿来跨进程保存数据。

浏览器里用 `<script type="module" src="main.js"></script>` 加载模块。它和普通 `<script>` 的区别是默认延迟执行、有独立的作用域、支持 `import`。直接用 `file://` 打开页面时，多数浏览器会拦截模块请求，起一个本地静态服务器更稳。

## 小接口比大文件重要 {#module-tradeoffs}

模块拆得好不好，看的是导出接口，不是文件数量。`store.js` 暴露了 `getMessages`、`addMessage` 和 `countMessages`，`main.js` 只依赖这三个名字。内部数组怎么改、以后换不换存储方式，只要这三个函数的行为不变，`main.js` 就不用动。

示例里的 `getMessages` 直接返回了内部数组。调用方可以绕过 `addMessage` 自己 `push`，甚至把它清空。方便，但接口没有被真正守住。如果这个数组的不变量很重要，就返回一份副本，或者只暴露按条件查询的函数。复制有成本，所以这是一个需要明确选择的边界，不是"永远返回副本"或"永远返回原数组"。

导出接口要小，也要稳定。把所有东西塞进一个 `index.js` 再统一转发，调用方写起来短，但很容易把不相关的模块拖进来，还可能制造循环依赖。分组按业务边界来，不按"方便一次导入"来。

动态导入适合按需加载：`await import("./store.js")` 返回一个 Promise，拿到模块命名空间。它能把首屏不需要的代码推迟到用时再加载，代价是你得自己处理加载中和失败状态。默认还是用顶层的静态 `import`，它更简单，也更容易被工具分析。

不同运行环境解析路径的规则不完全一样。Node 的 ES 模块要求写扩展名，浏览器按 URL 解析，构建工具可能允许省略扩展名，还可能配置了 `@/` 这样的别名。编辑器能跳转，不代表 `node` 或最终构建也能找到。遇到"编辑器正常、运行报错"，先看实际运行命令的解析规则和构建配置，不要只看编辑器的提示。

ES 模块和 CommonJS 也不是同一套语法换皮。`import`/`export` 属于 ESM，`require`/`module.exports` 属于 CommonJS。Node 根据最近的 `package.json` 里的 `type` 和文件扩展名决定用哪套。混用时需要互操作规则，导出的形状也可能和你以为的不一样；在同一个项目里，先确定用哪一套。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：`store.js` 里默认导出 `countMessages`，还具名导出了 `getMessages`。写一条 `import`，同时拿到这两个。

> **答案**
>
> ```js
> import countMessages, { getMessages } from "./store.js";
> ```
>
> 默认导入写在花括号外，具名导入写在花括号里。顺序不能反过来：花括号里的 `getMessages` 必须和导出名一致，前面的 `countMessages` 可以随便起名。

**第 2 题**：`board-state.js` 里写了 `export let messageCount = 2;`。另一个文件导入后执行 `messageCount = 10;`，会发生什么？为什么？

> **答案**
>
> 抛 `TypeError: Assignment to constant variable.`。
>
> 导入拿到的是导出方变量的实时绑定，但从导入方看是只读的。导出方自己可以用 `let` 重新赋值，导入方不能替它赋值。要改值，得调用模块导出的函数，让修改发生在拥有这个变量的模块里。

**第 3 题**：`main.js` 和 `other.js` 都导入 `store.js` 并各添加一条留言，然后各自打印条数。同一个 Node 进程里，它们看到的是同一份数据还是各自一份？换成两次 `node` 命令运行呢？

> **答案**
>
> 同一个进程里是同一份。模块只求值一次，之后被缓存，两个文件拿到的是同一个模块实例和同一个 `messages` 数组。
>
> 两次 `node` 命令是两个进程，各自从初始数据开始，互不共享内存。模块状态不会自动持久化。

## 继续阅读 {#related}

- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [模块、包与导入](/learn/python-modules)
- [React 组件与 JSX](/learn/react-components)
- [JavaScript 异步与 Promise](/learn/js-async)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
