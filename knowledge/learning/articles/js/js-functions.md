# JavaScript 函数、作用域与闭包

## 函数是能传来传去的值 {#function-values}

学完这一篇，你能写出一个计数器闭包，分清普通函数和箭头函数的 this，也能看懂回调为什么拿到旧值。

留言板的提交按钮要做一串事：读输入框、拼出留言、塞进列表、清空输入框。"按回车提交"也要复用同一串动作。与其复制两遍，不如把它包成一个函数，再把函数交给两个入口。

JavaScript 里函数本身就是值，可以赋给变量、作为参数传出去、从函数里返回。先看赋值：

```js
function createMessage(text) {
  return { id: 1, text, likes: 0 };
}

const onSubmit = createMessage;

console.log(typeof onSubmit);
console.log(onSubmit("还有货吗？").text);
```

在浏览器控制台或存成 `.js` 用 Node 运行，你都会看到：

```
function
还有货吗？
```

`const onSubmit = createMessage` 让两个名字指向同一个函数，拿到的不是调用结果。后面那对括号才表示"现在调用"。少了括号，拿到的永远是函数；加上括号，拿到的才是返回值。`setTimeout`、按钮监听、数组的 `map`，接收的都是这种"可以稍后调用的函数"，也就是回调。

## 写一个计数器 {#counter-closure}

把留言板的未读数做成一个计数器。新建 `counter.js`：

```js
// counter.js
function makeCounter() {
  let count = 0;

  return function next() {
    count += 1;
    return count;
  };
}

const next = makeCounter();
console.log(next());
console.log(next());

const other = makeCounter();
console.log(other());
```

```bash
node counter.js
```

你应该看到：

```
1
2
1
```

调用 `makeCounter()` 时，函数里创建了局部变量 `count`，然后返回内部函数 `next`。按普通的局部变量规则，`makeCounter` 一返回，`count` 就该消失了。但 `next` 还引用着它，所以这个环境被保留了下来。后面每次调用 `next()`，改的都是同一份 `count`：第一次加一得 1，第二次得 2。

又一次调用 `makeCounter()` 会创建一份全新的环境。`other` 有自己的 `count`，从 0 开始，所以第一次调用返回 1。两个计数器互不影响。

**函数加上它能访问的那份环境，就是闭包。** 闭包不是某种特殊语法，只要内部函数引用了外部函数的变量并被带出来，它就形成了。

## 闭包抓住的是变量，不是值 {#closure-mechanism}

先把"查找名字"这件事跑出来看。新建 `scope.js`：

```js
// scope.js
const boardName = "留言板";

function outer() {
  const greeting = "你好";

  function inner() {
    const name = "小林";
    console.log(`${greeting}，${name}，这里是${boardName}`);
  }

  inner();
}

outer();
```

```bash
node scope.js
```

输出：

```
你好，小林，这里是留言板
```

`inner` 里用到了三个名字。`name` 在它自己的函数里；`greeting` 在包着它的 `outer` 里；`boardName` 在最外层。查找顺序就是由内向外：先用自己作用域里的，找不到就去外层，再找不到就去模块或全局作用域。整条路径叫作用域链。

查找按**函数被写在哪里**决定，不按它被谁调用决定。新建 `lexical.js`：

```js
// lexical.js
const title = "外层";

function showTitle() {
  console.log(title);
}

function runInOtherScope() {
  const title = "内层";
  showTitle();
}

runInOtherScope();
```

用 `node lexical.js` 跑，输出是 `外层`。`showTitle` 在模块最外层定义，它的作用域链里只有那个 `title`。`runInOtherScope` 里另有一个 `title`，但它在调用 `showTitle` 时不会被临时塞进去。这种按书写位置确定的作用域叫词法作用域。

现在看闭包到底抓住了什么。新建 `binding.js`：

```js
// binding.js
function makeGreeting() {
  let name = "小林";
  const greet = () => console.log(`你好，${name}`);
  name = "阿岚";
  return greet;
}

const greet = makeGreeting();
greet();
```

用 `node binding.js` 跑，输出：

```
你好，阿岚
```

`greet` 定义时 `name` 是"小林"，执行时却打印"阿岚"。因为它抓住的是 `name` 这个**变量**，不是定义那一刻的值。变量改成什么，闭包读到的就是什么。

这点很关键：闭包不自动做快照。想固定住某个值，得把它复制到一个新变量，或者作为参数传进一个新函数。

## 箭头函数没有自己的 this {#this-arrow}

普通函数的 `this` 由**调用方式**决定；箭头函数没有自己的 `this`，用的是外层作用域的 `this`。在留言板的方法里放一个定时器，两种写法结果不同。新建 `this.js`：

```js
// this.js
const message = {
  author: "小林",

  replyLater() {
    setTimeout(function () {
      console.log("普通函数:", this.author);
    }, 0);

    setTimeout(() => {
      console.log("箭头函数:", this.author);
    }, 0);
  },
};

message.replyLater();
```

```bash
node this.js
```

你应该看到：

```
普通函数: undefined
箭头函数: 小林
```

调用 `message.replyLater()` 时，方法里的 `this` 是 `message`。第一个定时器的回调是普通函数，定时器调用它时没有以 `message.xxx()` 的形式调用，所以它的 `this` 不是 `message`，读 `this.author` 得到 `undefined`。第二个回调是箭头函数，它没有自己的 `this`，直接沿用 `replyLater` 里的那个 `this`，也就是 `message`，所以能读到 `小林`。

在浏览器里，普通回调里的 `this` 通常是 `window`；在 Node 的定时器里，它是定时器对象。两种情况下都不是 `message`，所以输出一样。换了运行环境，普通函数的 `this` 可能变，箭头函数不会。

箭头函数还有几条限制：不能用 `new` 调用，没有自己的 `arguments`，也不能用 `call`、`apply`、`bind` 改它的 `this`。把它当回调传出去很方便，但**不要用箭头函数写需要 `this` 的对象方法**：

```js
const broken = {
  author: "小林",
  show: () => console.log(this.author),
};
```

对象字面量不会给箭头函数提供一个 `this`，它会一直找到外层作用域；外层没有 `author`，所以 `show()` 读不到。需要方法的 `this` 指向对象时，用 `show() { ... }` 这种简写。

## 回调稍后执行，捕获的是创建时的绑定 {#stale-callback}

留言板给每条留言生成一个"回复"按钮。新建 `handlers.js`：

```js
// handlers.js
const messages = ["还有货吗？", "能便宜点吗？", "几天发货？"];

function handlersWithVar() {
  const handlers = [];
  for (var i = 0; i < messages.length; i++) {
    handlers.push(() => `第 ${i + 1} 条：${messages[i]}`);
  }
  return handlers;
}

function handlersWithLet() {
  const handlers = [];
  for (let i = 0; i < messages.length; i++) {
    handlers.push(() => `第 ${i + 1} 条：${messages[i]}`);
  }
  return handlers;
}

for (const handler of handlersWithVar()) {
  console.log(handler());
}

console.log("---");

for (const handler of handlersWithLet()) {
  console.log(handler());
}
```

```bash
node handlers.js
```

输出：

```
第 4 条：undefined
第 4 条：undefined
第 4 条：undefined
---
第 1 条：还有货吗？
第 2 条：能便宜点吗？
第 3 条：几天发货？
```

第一组是真实的 bug 形状：三个按钮都指向第 4 条，而第 4 条不存在，所以内容是 `undefined`。原因是 `var i` 只有一份绑定，循环结束后 `i` 是 3；回调此时才执行，读到的全是 3。闭包抓住的是那个一直在变的变量，不是每一轮当时的数字。

`let` 为每一轮创建一个新绑定，三个回调分别记住自己的 `i`，所以输出 1、2、3。

把回调放进定时器，"稍后"会更明显。新建 `timers.js`：

```js
// timers.js
const messages = ["还有货吗？", "能便宜点吗？", "几天发货？"];

console.log("用 var:");
for (var i = 0; i < messages.length; i++) {
  setTimeout(() => console.log(`第 ${i + 1} 条：${messages[i]}`), 0);
}

console.log("用 let:");
for (let j = 0; j < messages.length; j++) {
  setTimeout(() => console.log(`第 ${j + 1} 条：${messages[j]}`), 0);
}
```

```bash
node timers.js
```

输出：

```
用 var:
用 let:
第 4 条：undefined
第 4 条：undefined
第 4 条：undefined
第 1 条：还有货吗？
第 2 条：能便宜点吗？
第 3 条：几天发货？
```

同步的两行日志先出现。定时器要等当前代码全部跑完才轮到，那时 `var i` 已经是 3，三次读到的都是 `messages[3]`；`let j` 在每一轮有自己的一份，所以三个回调分别读到三条真实的留言。

不想用 `let` 也能修：把当前下标作为参数传给一个工厂函数，参数会为每次调用创建新绑定。

```js
function makeHandler(index) {
  return () => `第 ${index + 1} 条：${messages[index]}`;
}
```

React 里遇到的"回调拿到旧 state"是同一个问题换了外壳。函数组件每次渲染都会重新执行，`count` 是那一次渲染里的绑定。第一次渲染时创建、几秒后才执行的定时器，闭包住的是第一次渲染的 `count`，它根本没见过后面的值。正确的修法是写对 effect 的依赖并清理定时器；如果更新要基于旧值，用函数式更新 `setCount((c) => c + 1)`。给回调加延迟不会让它看见新值。

## 闭包什么时候会拖后腿 {#closure-tradeoffs}

闭包让环境活着，这既是能力也是成本。只要那个内部函数还被引用，它引用的变量和对象就不会被回收。事件监听器、定时器、缓存数组都是常见的"忘了放手"的地方；页面切换时该移除的监听要移除，该清空的定时器要清空。

闭包也容易把状态藏得太深。一个未读计数放在闭包里没问题；如果这个值需要被序列化、需要跨模块共享、或者调试时想在控制台里看一眼，它就不该只存在于某个函数内部。**判断标准很简单：这个值要不要被外部观察或接管。要，就用对象或模块状态；不要，闭包很好。**

函数作为参数传入，比在函数内部直接依赖全局变量更容易测试。比如把"发送请求"的函数作为参数交给提交逻辑，测试时就能传一个假函数，不用真的联网。

嵌套过多匿名函数会让调用关系难读，出错时的调用栈也全是 `<anonymous>`。给重要的回调起个名字，问题会好查很多。React 里每次渲染都会创建新的函数身份，这会影响依赖比较和 `memo`；需要稳定身份时再用 `useCallback`，并且先确认它真的带来了改善。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这段输出什么？

```js
function makeCounter() {
  let count = 0;
  return () => {
    count += 1;
    return count;
  };
}

const a = makeCounter();
const b = makeCounter();
console.log(a(), a(), b());
```

> **答案**
>
> 输出 `1 2 1`。
>
> `a` 和 `b` 来自两次独立的 `makeCounter()` 调用，各自有一份 `count`。`a()` 第一次返回 1，第二次返回 2；`b()` 是另一个计数器，从 0 开始，返回 1。

**第 2 题**：为什么下面这个普通函数读不到 `message.author`？怎么改？

```js
const message = {
  author: "小林",
  replyLater() {
    setTimeout(function () {
      console.log(this.author);
    }, 0);
  },
};
message.replyLater();
```

> **答案**
>
> 定时器调用回调时，不是以 `message.replyLater()` 这种带接收者的方式调用的，所以普通函数里的 `this` 不是 `message`。它可能是 `window`，也可能是 Node 的定时器对象，两种都没有 `author`。
>
> 两种改法：把回调换成箭头函数，让它沿用 `replyLater` 的 `this`；或者在进入定时器前先保存 `const self = this;`，回调里读 `self.author`。
>
> ```js
> setTimeout(() => {
>   console.log(this.author);
> }, 0);
> ```

**第 3 题**：下面这段打印什么？想打印 0、1、2，最少改哪里？

```js
for (var i = 0; i < 3; i++) {
  setTimeout(() => console.log(i), 0);
}
```

> **答案**
>
> 打印三次 `3`。三个回调闭包住同一个 `i`，定时器执行时循环早已结束，`i` 停在 3。
>
> 把 `var` 改成 `let`。每轮迭代创建一个新绑定，三个回调分别拿到 0、1、2。

## 继续阅读 {#related}

- [JavaScript 的变量与值](/learn/js-values)
- [函数、参数与返回值](/learn/python-functions)
- [Effect、依赖与清理](/learn/react-effects)
- [事件循环、任务与微任务](/learn/js-events-loop)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
