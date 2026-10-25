# JavaScript 的变量与值

## const 锁的是名字，不是对象 {#const-binding}

读完这一篇，你能说清 const 究竟锁住了什么，也能亲手跑出 typeof null 和 0.1 + 0.2 这些结果。

你在给留言板写第一条留言：`{ id: 1, author: "小林", text: "还有货吗？", likes: 0 }`。用 `const` 声明它，然后想把点赞数加一。按"常量不能改"的直觉，这一行应该报错。

打开浏览器控制台（F12 → Console），输入：

```js
const message = { id: 1, author: "小林", text: "还有货吗？", likes: 0 };

message.likes = 1;
console.log(message.likes);
```

你应该看到 `1`，没有报错。再试着重写整个名字：

```js
message = { id: 2, author: "阿岚", text: "能便宜点吗？", likes: 0 };
```

控制台会给出 `TypeError: Assignment to constant variable.`。**`const` 锁住的是 `message` 这个名字指向哪个对象，不是对象里的内容。** 改属性不需要换对象，所以放行；重新赋值要换对象，所以拦下。

浏览器控制台的 `const` 声明会留在当前页面里。同一段 `const message = ...` 只能声明一次；要把整段重跑一遍，先刷新页面，否则会先撞上"名字已声明"的错误。

## 在 Node 里跑一遍 {#node-walkthrough}

零散地敲控制台容易漏掉输出。新建一个 `values.js`，把要对比的写法放进同一个文件：

```js
// values.js
const message = { id: 1, author: "小林", text: "还有货吗？", likes: 0 };

message.likes += 1;
console.log("改属性:", message.likes);

try {
  message = { id: 2, author: "阿岚", text: "能便宜点吗？", likes: 0 };
} catch (error) {
  console.log("重新赋值:", error.message);
}

let boardName = "留言板";
{
  let boardName = "另一个板";
  console.log("块内:", boardName);
}
console.log("块外:", boardName);

console.log("typeof null:", typeof null);
console.log("0.1 + 0.2:", 0.1 + 0.2);
console.log("等于 0.3 吗:", 0.1 + 0.2 === 0.3);
console.log("NaN 等于自己吗:", NaN === NaN);
console.log('"1" == 1:', "1" == 1);
console.log('"1" === 1:', "1" === 1);
console.log("null == undefined:", null == undefined);
console.log("null === undefined:", null === undefined);
```

在文件所在的目录运行：

```bash
node values.js
```

你应该看到：

```
改属性: 1
重新赋值: Assignment to constant variable.
块内: 另一个板
块外: 留言板
typeof null: object
0.1 + 0.2: 0.30000000000000004
等于 0.3 吗: false
NaN 等于自己吗: false
"1" == 1: true
"1" === 1: false
null == undefined: true
null === undefined: false
```

第一组只做了一件事：把 `message.likes` 从 0 加到 1。它读属性、加一、写回同一个对象，全程没有碰 `message` 这个名字。第二组用 `try` 包住重新赋值，是为了让报错只中断这一次赋值，后面的行还能继续跑。把 `try` 去掉，Node 会在这一行退出，后面的输出都不会出现。

第三组里有两个 `boardName`。花括号 `{ ... }` 创建了一个块，块里的 `let` 声明了一个新的 `boardName`，它暂时遮住外面的那个。块结束后，外面那个还是原来的值。这就是"块级作用域"：名字只在它所在的那对花括号里有效。

第四组是八个值的对照，下一节逐个解释。

## let、var 与循环里的同一个 i {#scope-loop}

`let` 和 `var` 都能重新赋值，差别在作用域。跑这个文件：

```js
// loop.js
console.log("用 var:");
for (var i = 0; i < 3; i++) {
  setTimeout(() => console.log("var:", i), 0);
}

console.log("用 let:");
for (let j = 0; j < 3; j++) {
  setTimeout(() => console.log("let:", j), 0);
}

console.log("循环结束");
```

```bash
node loop.js
```

你应该看到：

```
用 var:
用 let:
循环结束
var: 3
var: 3
var: 3
let: 0
let: 1
let: 2
```

同步代码先跑完，三行日志先出现。定时器的回调排在后面，等循环结束后才执行。

`var i` 是函数作用域，这里整个模块只有一份 `i`。三次循环往里塞了三个回调，它们闭包住的是**同一个 `i`**。等回调真正执行时，循环已经结束，`i` 停在 3，所以三次都打印 3。

`let j` 是块级作用域。每一轮循环都会创建一个新的 `j`，三个回调各自记住自己那一轮的绑定。回调稍后执行，读到的仍是 0、1、2。

还有一处差别：`var` 的声明会提升，并且在开始时就初始化为 `undefined`；`let` 也提升，但在声明那一行执行前不能访问。新建 `tdz.js`：

```js
// tdz.js
console.log(a);
var a = 1;

try {
  console.log(b);
} catch (error) {
  console.log(error.message);
}
let b = 1;
```

```bash
node tdz.js
```

输出：

```
undefined
Cannot access 'b' before initialization
```

这个"声明了但还没初始化"的区间叫暂时性死区。它拦住的是先读后声明这类错误，而不是不让你在任何位置使用变量。

`var` 还能在同一个作用域里重复声明，`let` 和 `const` 不行。新代码里没有理由再用 `var`：需要重新赋值就用 `let`，不需要就用 `const`。旧项目里看到 `var`，先按"函数作用域、会提升"来读。

## 原始值和对象：复制与共享 {#value-vs-reference}

```js
// refs.js
let likes = 3;
let moreLikes = likes;
moreLikes += 1;
console.log(likes, moreLikes);

const first = { text: "你好" };
const second = first;
second.text = "改过了";
console.log(first.text);

const twin = { text: "你好" };
console.log(first === twin);
console.log(first === second);
```

```bash
node refs.js
```

输出：

```
3 4
改过了
false
true
```

`likes` 是数字，属于原始值。`let moreLikes = likes` 复制的是 3 这个值本身，之后改 `moreLikes` 不影响 `likes`。字符串、布尔、`null`、`undefined`、`symbol`、`bigint` 都是原始值。

对象、数组、函数是引用值。`const second = first` 复制的是"指向哪个对象"，不是对象内容。所以 `second.text = "改过了"` 改的是同一个对象，`first.text` 跟着变。

`===` 比较两个对象时，比的也是它们是不是同一个对象，而不是长得像不像。`first` 和 `twin` 内容相同，但它们是分别创建的两个对象，所以 `false`。这条规则后面会反复用到：React 判断状态有没有变化，靠的正是这个"身份"。

## 四个反直觉的值 {#weird-values}

回到 `values.js` 的输出，逐条看。

**"`typeof null` 返回 `"object"`，所以 `null` 是对象。"** 不是。这是 JavaScript 最早实现留下的错误：当年用值的低位标记来区分类型，`null` 的标记和对象撞在了一起。修掉它会让大量旧代码的行为改变，所以一直保留。判断空值要用 `value === null`，不要用 `typeof`。

**"`NaN` 不等于自己，那就没法判断了。"** 能判断。`NaN` 表示"这次运算没有得到合法数字"，它不等于任何值，包括自己。用 `Number.isNaN(value)`，下面三行可以粘进浏览器控制台：

```js
console.log(Number.isNaN(NaN));
console.log(Number.isNaN("abc"));
console.log(typeof NaN);
```

输出：

```
true
false
number
```

`Number.isNaN` 只对真正的 `NaN` 返回 `true`，不会把字符串转换后再判断。全局的 `isNaN("abc")` 会先做类型转换，得到 `true`，很容易误判，别用它。`typeof NaN` 是 `"number"`，因为 `NaN` 在类型上确实属于数字。

**"`0.1 + 0.2` 就是 `0.3`。"** 在 JavaScript 里不是。数字用双精度浮点存储，`0.1` 和 `0.2` 都无法用二进制精确表示，相加得到 `0.30000000000000004`。要比较两个浮点结果，留一点误差。在控制台里试：

```js
console.log(Math.abs(0.1 + 0.2 - 0.3) < 1e-9);
```

输出 `true`。金额不要用"元"的浮点数存，改用整数"分"：12.30 元存成 1230，显示时再除 100。留言板的点赞数是整数，碰不到这个问题；一旦加上打赏金额就会碰到。

**"`==` 只是 `===` 的简写，用哪个都行。"** 不是。`==` 会先做类型转换再比较，`===` 不转换。几个结果：

| 表达式 | 结果 | 原因 |
|---|---|---|
| `"1" == 1` | `true` | 字符串先转成数字 |
| `"1" === 1` | `false` | 类型不同，直接不等 |
| `null == undefined` | `true` | 规范特别规定这两者相等 |
| `null === undefined` | `false` | 类型不同 |
| `null == 0` | `false` | `null` 不会转成 0 |
| `"" == 0` | `true` | 空字符串转成 0 |
| `[] == false` | `true` | 数组先转成空字符串，再转成 0 |

默认写 `===`。代码里偶尔会看到 `value == null`，它的意思是"`null` 或 `undefined` 都算空"，这是 `==` 少数有明确用途的写法；如果不确定，就写成两个显式判断。

## 什么时候用 let，什么时候用 const {#choose-declaration}

先给结论：**默认写 `const`，需要重新赋值时再改成 `let`，`var` 留给旧代码。**

| 声明 | 能否重新赋值 | 作用域 | 新代码里的用法 |
|---|---|---|---|
| `const` | 不能 | 块级 | 默认选择 |
| `let` | 能 | 块级 | 循环计数、累加器、要换值的变量 |
| `var` | 能 | 函数级 | 只用来读旧代码 |

`const` 用得多的好处不是性能，而是读代码时少一种可能：这个名字不会中途换对象。把 `const` 改成 `let` 的那一刻，你会意识到"这里确实需要变"，这比到处用 `let` 更容易发现问题。

`const` 不代表对象不可变。要防止改属性，`Object.freeze` 只能冻住第一层，嵌套对象照样能改；而且在非严格模式下，写入会静默失败，不报错，更难查。真正可靠的做法是改数据时复制出新对象，下一篇会讲。

不可变更新的代价是复制。留言板只有几十条数据时，复制一次的开销可以忽略；数据很大、更新很频繁时，先测量再决定，不要凭感觉把代码写复杂。把多次修改合并成一次复制，通常比每条字段改一次就复制一次更划算。

声明的位置也影响可读性。变量离第一次使用越近、作用域越小，读代码时要同时在脑子里记住的东西越少。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这段会报错吗？

```js
const list = [];
list.push("第一条");
console.log(list);
```

> **答案**
>
> 不会报错。`const` 只阻止 `list` 重新指向另一个数组，`push` 是在原数组上追加元素，没有换对象。
>
> 输出是 `[ '第一条' ]`（Node 的格式）。如果写成 `list = ["第二条"]`，那才会抛 `TypeError: Assignment to constant variable.`。

**第 2 题**：为什么 `NaN === NaN` 是 `false`？应该怎么判断一个值是不是 `NaN`？

> **答案**
>
> `NaN` 表示"不是合法数字"，两个无效结果不能互相证明相等，所以规范规定它不等于任何值，包括自己。
>
> 用 `Number.isNaN(value)`。不要用 `value === NaN`，那个表达式永远是 `false`。

**第 3 题**：下面这段打印什么？想让它打印 0、1、2，最少改哪里？

```js
for (var i = 0; i < 3; i++) {
  setTimeout(() => console.log(i), 0);
}
```

> **答案**
>
> 打印三次 `3`。三个回调闭包住的是同一个函数级变量 `i`，定时器执行时循环已经结束，`i` 是 3。
>
> 把 `var` 改成 `let` 就行。`let` 每轮迭代创建一个新绑定，三个回调分别拿到 0、1、2。

## 继续阅读 {#related}

- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [对象、数组与不可变更新](/learn/js-objects)
- [State、重新渲染与状态快照](/learn/react-state)
- [Python 的变量与值](/learn/python-values)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
