# 对象、数组与不可变更新

## 留言按名字存，列表按顺序存 {#two-shapes}

学完这一篇，你能用 map、filter、find 把留言列表变成界面要的样子，并且改一条留言时不碰原数组。

留言板里的一条留言有编号、作者、内容、点赞数四个字段。用对象存它，因为取数据时你记得的是字段名：

```js
const message = {
  id: 1,
  author: "小林",
  text: "还有货吗？",
  likes: 2,
};

console.log(message.author);
```

输出 `小林`。对象靠名字取值，`message.text` 和 `message.likes` 谁写在前面都不影响结果。

整个留言列表用数组存，因为界面要按顺序显示，而且"第几条"有意义：

```js
const messages = [
  { id: 1, author: "小林", text: "还有货吗？", likes: 2 },
  { id: 2, author: "阿岚", text: "能便宜点吗？", likes: 5 },
  { id: 3, author: "小林", text: "几天发货？", likes: 0 },
];

console.log(messages[0].text);
```

输出 `还有货吗？`。这两段可以直接粘进浏览器控制台，也可以放进 `.js` 用 Node 跑。

**对象按名字找，数组按位置找。** 单条留言用对象，因为字段比位置可靠；列表用数组，因为渲染顺序就是数组顺序。界面上最常见的结构就是"对象数组"：一个数组装着若干条形状相同的对象。

## 用 map、filter、find 读留言 {#array-methods}

新建 `messages.js`，把三种最常用的读法放在一起：

```js
// messages.js
const messages = [
  { id: 1, author: "小林", text: "还有货吗？", likes: 2 },
  { id: 2, author: "阿岚", text: "能便宜点吗？", likes: 5 },
  { id: 3, author: "小林", text: "几天发货？", likes: 0 },
];

// map：每项换成一个新值，长度不变
const lines = messages.map((message) => `${message.author}：${message.text}`);
for (const line of lines) {
  console.log(line);
}

// filter：只留下满足条件的项
const hotIds = messages.filter((message) => message.likes >= 2).map((m) => m.id);
console.log("点赞不少于 2 的留言:", hotIds);

// find：拿第一个满足条件的项
const firstFromLin = messages.find((message) => message.author === "小林");
console.log("小林的第一条:", firstFromLin.text);

// find 找不到时返回 undefined
const missing = messages.find((message) => message.author === "阿岚的同事");
console.log("找不到的作者:", missing);
```

```bash
node messages.js
```

你应该看到：

```
小林：还有货吗？
阿岚：能便宜点吗？
小林：几天发货？
点赞不少于 2 的留言: [ 1, 2 ]
小林的第一条: 还有货吗？
找不到的作者: undefined
```

`map` 把每个元素交给回调，回调返回什么，新数组的对应位置就是什么。长度永远和原数组一样，即使回调返回 `undefined`，那个位置也会留一个 `undefined`。上面用它把对象转成一行行字符串。

`filter` 的回调返回真值或假值。真值对应的元素留下，假值对应的丢掉，所以结果可能更短。它留下的是**原元素**，不是回调的返回值。上面先筛出点赞不少于 2 的留言，再 `map` 取 `id`，得到 `[1, 2]`。

`find` 也是按条件找，但它只返回**第一个**匹配的元素。找不到时返回 `undefined`，不会返回空对象，也不会抛错。所以读它的属性前要先确认它不是 `undefined`；用 `missing?.text` 可以安全地得到 `undefined`，但"没有找到"这件事仍然需要你的代码处理。

三个方法都不会改动原数组。它们返回新数组或单个元素，原数组的引用和内容保持不变。

## 改一条留言：复制数组和对象 {#immutable-update}

真实界面要改数据。给第二条留言点个赞，有两种写法。新建 `update.js`：

```js
// update.js
const messages = [
  { id: 1, text: "还有货吗？", likes: 2 },
  { id: 2, text: "能便宜点吗？", likes: 5 },
];

// 直接改原对象
messages[1].likes += 1;
console.log("原对象被改成:", messages[1].likes);

// 复制数组，只替换发生变化的那一条
const nextMessages = messages.map((message) =>
  message.id === 2 ? { ...message, likes: message.likes + 1 } : message
);

console.log("旧数组里的值:", messages[1].likes);
console.log("新数组里的值:", nextMessages[1].likes);
console.log("两个数组是同一个吗:", messages === nextMessages);
console.log("改过的那条是同一个吗:", messages[1] === nextMessages[1]);
console.log("没改的那条是同一个吗:", messages[0] === nextMessages[0]);
```

```bash
node update.js
```

输出：

```
原对象被改成: 6
旧数组里的值: 6
新数组里的值: 7
两个数组是同一个吗: false
改过的那条是同一个吗: false
没改的那条是同一个吗: true
```

第一段是原地修改。`messages[1]` 拿到第二个对象的引用，改它的 `likes`，原数组里那条留言就变了。所有拿着旧数组的地方，看到的也是被改过的对象。

第二段是复制更新。`map` 建了一个新数组。遇到 `id === 2` 时，`{ ...message, likes: message.likes + 1 }` 先复制原对象的字段，再用新的 `likes` 覆盖；其他留言原样返回。于是：

- 数组是新的，`messages !== nextMessages`。
- 改过的那条是新的，`messages[1] !== nextMessages[1]`。
- 没改的那条还是原对象，`messages[0] === nextMessages[0]`，没有多余复制。

这种"新数组 + 只复制变化的部分"叫结构共享。复制数组只遍历一遍，未变化的对象不重复创建；它会不会成为瓶颈需要测量，不能凭感觉下结论。

React 判断状态有没有变化，靠的正是对象身份。新建 `identity.js`：

```js
// identity.js
const state = [{ id: 1, likes: 2 }];

state[0].likes += 1;
const nextState = state;

console.log("是同一个值吗:", Object.is(state, nextState));

const copied = state.map((m) => ({ ...m, likes: m.likes + 1 }));
console.log("复制之后还是同一个值吗:", Object.is(state, copied));
```

```bash
node identity.js
```

输出：

```
是同一个值吗: true
复制之后还是同一个值吗: false
```

React 的 `useState` 在更新时用 `Object.is` 比较新旧 state。你原地改了对象，再把它交回去，新旧是同一个引用，`Object.is` 判定没有变化，这次更新会被跳过，界面不重新渲染。即使你交的是 `[...state]`，数组变新了，里面的对象还是旧的；总体会渲染，但接收那个对象作为 prop 的 `memo` 子组件仍可能认为 prop 没变，继续用旧结果。

**让"变了的东西"换一个新身份，让"没变的东西"保持原身份。** 这是不可变更新的核心操作，也是 React 能准确判断哪里需要更新的前提。这里不需要安装 React，`Object.is` 这一行就是它做的判断。

## 展开语法只复制一层 {#shallow-copy}

`{ ...message }` 复制的是对象的第一层属性。如果某个属性的值本身是对象，复制到的是同一个内部对象的引用。新建 `shallow.js`：

```js
// shallow.js
const first = { id: 1, author: { name: "小林" } };
const shallow = { ...first };
shallow.author.name = "阿岚";

console.log("浅拷贝后，原对象:", first.author.name);
console.log("浅拷贝后，副本:", shallow.author.name);

const second = { id: 2, author: { name: "小林" } };
const deep = { ...second, author: { ...second.author, name: "阿岚" } };

console.log("逐层复制后，原对象:", second.author.name);
console.log("逐层复制后，副本:", deep.author.name);
console.log("第二组的 author 还共享吗:", second.author === deep.author);

const cloned = structuredClone(second);
console.log("structuredClone 后的 author 还共享吗:", cloned.author === second.author);
```

```bash
node shallow.js
```

输出：

```
浅拷贝后，原对象: 阿岚
浅拷贝后，副本: 阿岚
逐层复制后，原对象: 小林
逐层复制后，副本: 阿岚
第二组的 author 还共享吗: false
structuredClone 后的 author 还共享吗: false
```

第一组里，`shallow` 是新的外层对象，但 `shallow.author` 和 `first.author` 指向同一个内层对象。改 `shallow.author.name`，原对象当然看得见。

第二组逐层复制：外层展开一次，`author` 再展开一次并覆盖 `name`。这样内层也换了新对象，原对象不受影响。

要深拷贝整棵结构，可以用 `structuredClone(second)`。Node 17 及以后、现代浏览器都提供它。它复制不了函数和 DOM 节点，遇到这类值会抛错。数据里只有普通对象、数组、字符串、数字时，它最省事。

数组也一样：`[...messages]` 只复制数组这一层，里面的对象仍然共享。这也是 `update.js` 里为什么必须同时复制数组和那一条对象。

## 哪些方法会动原数组，以及四个误区 {#array-pitfalls}

不是所有数组方法都像 `map` 那样返回新数组。先看对照：

| 方法 | 返回什么 | 会不会改原数组 |
|---|---|---|
| `map` | 等长的新数组 | 不会 |
| `filter` | 可能更短的新数组 | 不会 |
| `find` | 第一个匹配的元素，找不到是 `undefined` | 不会 |
| `forEach` | `undefined` | 不建新数组，除非回调自己改元素 |
| `push`、`pop` | 新长度、被移除的元素 | 会 |
| `sort`、`reverse` | 原数组本身（已经变了） | 会 |
| `slice`、`concat` | 新数组 | 不会 |
| `toSorted`、`toReversed` | 新数组（Node 20 及以后、现代浏览器） | 不会 |

跑一段验证 `sort` 和 `forEach`：

```js
// methods.js
const ids = ["3", "1", "2"];

const sorted = ids.sort();
console.log("sort 之后:", ids);
console.log("返回的是原数组吗:", sorted === ids);

const copy = ids.slice().sort();
copy.push("4");
console.log("slice 之后原数组:", ids);
console.log("副本:", copy);

const result = ids.forEach((id) => id);
console.log("forEach 返回:", result);
```

```bash
node methods.js
```

输出：

```
sort 之后: [ '1', '2', '3' ]
返回的是原数组吗: true
slice 之后原数组: [ '1', '2', '3' ]
副本: [ '1', '2', '3', '4' ]
forEach 返回: undefined
```

`sort` 原地排序并返回原数组本身。要保留原顺序，先 `slice()` 复制，再排副本。`forEach` 只是逐个执行回调，回调的返回值被丢掉，所以它不能拿来生成新数组；要转换就用 `map`。

再看四个常被写错的判断。

**"`map` 会返回新数组，所以回调里怎么改都安全。"** `map` 换掉的是外层数组，回调拿到的元素仍是原对象。在回调里写 `m.likes += 1`，改的就是原数据。新建 `pitfalls.js`：

```js
// pitfalls.js
const messages = [{ id: 1, likes: 2 }];

messages.map((m) => {
  m.likes += 1;
});
console.log("map 之后原对象:", messages[0].likes);

const missing = messages.find((m) => m.id === 99);
console.log("find 找不到:", missing);
console.log("读不存在的属性:", missing?.text);

console.log("空数组是真值吗:", Boolean([]));
console.log("空对象是真值吗:", Boolean({}));
console.log("两个内容相同的数组相等吗:", [1, 2] === [1, 2]);
```

用 `node pitfalls.js` 跑，输出：

```
map 之后原对象: 3
find 找不到: undefined
读不存在的属性: undefined
空数组是真值吗: true
空对象是真值吗: true
两个内容相同的数组相等吗: false
```

**"`find` 找不到时会返回空对象，可以直接读属性。"** 它返回 `undefined`。`missing.text` 会抛 `TypeError: Cannot read properties of undefined`，程序可能就此中断。用 `missing?.text` 只能让读取变安全，不能替你做"没找到"的分支逻辑。

**"空数组是假值，`if (messages)` 就能判断有没有留言。"** `[]` 和 `{}` 都是对象，对象在条件判断里一律是真值。空列表要用 `messages.length === 0` 判断。这也是新手用 `if (!messages)` 判断"没有数据"却一直进不去的原因。

**"两个内容一样的数组用 `===` 比较会得到 `true`。"** 不会。`===` 比较的是引用，两个分别创建的数组永远是两个对象，哪怕内容完全一样。要比较内容，得逐项比较，或者比较序列化后的字符串（但属性顺序会影响结果，通常不推荐）。

## 什么时候该复制，什么时候不必 {#copy-tradeoffs}

不可变更新的规则不是"每次碰数据都深拷贝一遍"。**只复制变了的路径。** 改一条留言，就是新数组加一个新对象，其他对象原样复用；`update.js` 里已经这么做了。

同时改多条留言时，一趟 `map` 解决，不要每条都复制一次整个数组。复制本身是 O(n)，连续几次就是几倍的浪费。

嵌套太深会让复制代码变得难读。一条留言嵌作者对象，作者又嵌地址，改个名字要展开三层。遇到这种情况，先想想数据结构能不能摊平：列表里只存 `authorId`，作者信息单独放一张表，按 id 查。结构变简单，更新也跟着简单。

列表很大、更新很频繁时，复制才有明显成本。先用浏览器的性能面板测量，再决定要不要引入更复杂的状态库或局部更新。留言板这个规模，按可读性优先写就好。

还有一条边界：从父组件传进来的 props、从模块里拿到的共享数组，都当作只读。需要排序展示时用 `[...messages].sort(...)` 或 `toSorted`，不要直接在共享数组上 `sort`，否则调用方手里的顺序也会被悄悄改掉。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：用 `messages` 取出点赞不少于 2 的留言文本，写成一行链式调用。

```js
const messages = [
  { id: 1, author: "小林", text: "还有货吗？", likes: 2 },
  { id: 2, author: "阿岚", text: "能便宜点吗？", likes: 5 },
  { id: 3, author: "小林", text: "几天发货？", likes: 0 },
];
```

> **答案**
>
> ```js
> const texts = messages
>   .filter((message) => message.likes >= 2)
>   .map((message) => message.text);
>
> console.log(texts); // [ '还有货吗？', '能便宜点吗？' ]
> ```
>
> `filter` 先留下点赞不少于 2 的两条，`map` 再把它们转成文本。两个方法都返回新数组，原 `messages` 没变。

**第 2 题**：你把 `messages[0].likes` 加了一，然后把同一个数组传给 React 的 `setMessages`。界面为什么没更新？怎么改？

> **答案**
>
> 因为传给 `setMessages` 的数组还是原来那个引用。React 用 `Object.is` 比较新旧 state，判断"没有变化"，跳过这次更新。
>
> 要创建新数组，并且给发生变化的那条留言创建新对象：
>
> ```js
> const next = messages.map((message) =>
>   message.id === 1 ? { ...message, likes: message.likes + 1 } : message
> );
> setMessages(next);
> ```
>
> 新数组让整体更新被接受，新对象让依赖这条留言的子组件也能看出变化。

**第 3 题**：`const copy = { ...message }` 之后，改 `copy.author.name`，原 `message.author.name` 会变吗？为什么？

> **答案**
>
> 会变。展开语法只复制第一层，`copy.author` 和 `message.author` 指向同一个内层对象。
>
> 要连内层一起换，得逐层复制：
>
> ```js
> const copy = {
>   ...message,
>   author: { ...message.author, name: "阿岚" },
> };
> ```
>
> 这样 `copy.author` 是新对象，原 `message.author` 不受影响。

## 继续阅读 {#related}

- [JavaScript 的变量与值](/learn/js-values)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [State、重新渲染与状态快照](/learn/react-state)
- [interface、type 与结构契约](/learn/ts-interfaces)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
