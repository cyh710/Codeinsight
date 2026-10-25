# TypeScript 的类型注解与推断

## 参数传错了，为什么半夜才发现 {#why-check}

读完这一篇，你能给留言板的数据和函数写上类型，也能分清 any 和 unknown 该用哪个。

凌晨一点，你在查留言板页面为什么显示「undefined：undefined」。请求确实回来了，`createdAt` 也有值；问题在另一个调用点：那里把 `Date.now()` 塞进了本该放日期字符串的字段。JavaScript 没有拦，格式化函数也没有拦，错误一路走到页面上。

TypeScript 把这类检查提前。它读你的代码，算出每个值的形状，再看这个值被放进了什么位置。放不进去，编辑器标红，`tsc` 拒绝编译。下面从一个最小的项目开始。

建目录，装编译器：

```bash
mkdir message-board
cd message-board
npm init -y
npm i -D typescript
```

`npm init -y` 生成 `package.json`，`npm i -D typescript` 把编译器装进这个项目的 `node_modules`。之后在这个目录里运行 `npx tsc`，用的就是刚装好的版本，不依赖全局安装。

新建 `board.ts`：

```ts
type Message = {
  id: number;
  author: string;
  text: string;
  createdAt: string;
};

const messages: Message[] = [
  {
    id: 1,
    author: "小林",
    text: "今晚一起吃饭吗？",
    createdAt: "2026-10-24T19:02:00+08:00",
  },
  {
    id: 2,
    author: "阿岚",
    text: "好，七点见。",
    createdAt: "2026-10-24T19:03:00+08:00",
  },
];

function formatMessage(message: Message): string {
  return `${message.author}：${message.text}`;
}

console.log(formatMessage(messages[0]));
```

先做类型检查：

```bash
npx tsc --noEmit --strict board.ts
```

没有输出就是通过。再编译成 JavaScript 并运行：

```bash
npx tsc board.ts --strict --target es2020
node board.js
```

你应该看到：

```
小林：今晚一起吃饭吗？
```

现在新建 `broken.ts`，把 `createdAt` 换成毫秒数：

```ts
type Message = {
  id: number;
  author: string;
  text: string;
  createdAt: string;
};

function formatMessage(message: Message): string {
  return `${message.author}：${message.text}`;
}

formatMessage({
  id: 2,
  author: "阿岚",
  text: "好，七点见。",
  createdAt: Date.now(), // TS2322: Type 'number' is not assignable to type 'string'.
});
```

```bash
npx tsc --noEmit --strict broken.ts
```

输出：

```
broken.ts(16,3): error TS2322: Type 'number' is not assignable to type 'string'.
```

错误落在 `createdAt` 那一行。`Date.now()` 返回 `number`，这个字段要求 `string`。TypeScript 不会把数字转成字符串，也不会在运行时补一次转换；它只告诉你两个形状对不上。改成 `new Date().toISOString()` 才能通过。

这就是最基本的用法：写清楚形状，让 `tsc` 在运行前检查。后面几节讲什么该写、什么可以不写，以及哪些地方别指望它。

## 哪些地方要写类型，哪些交给推断 {#annotation-inference}

`board.ts` 里有两处明显的手写类型：`messages: Message[]` 和函数签名。别的地方没写：

```ts
const first = messages[0];          // first 被推断为 Message
const snippet = first.text.slice(0, 4); // snippet 被推断为 string
```

TypeScript 从 `messages` 的元素类型推出 `first` 是 `Message`，再从 `Message.text` 推出 `snippet` 是 `string`。这叫推断；推断出来的类型和手写的一样参与检查。在 VS Code 里把鼠标停在 `first` 上，提示会显示 `const first: Message`。

想确认它不是 `any`，故意赋错一次：

```ts
const first = messages[0];
const wrong: number = first.text; // TS2322: Type 'string' is not assignable to type 'number'.
```

把 `first.text` 换成 `first.nickname`，也会报这样的错：

```ts
console.log(first.nickname); // TS2339: Property 'nickname' does not exist on type 'Message'.
```

```
error TS2339: Property 'nickname' does not exist on type 'Message'.
```

`first` 如果是 `any`，这两种写法都不会有意见。会报错，说明编译器拿到了真实形状。

写不写注解，可以按位置判断：

- **函数边界要写。** 参数和返回类型是调用方唯一能看到的约定。`formatMessage(message: Message): string` 让读代码的人不用进函数体，就知道它收什么、交回什么。
- **数据入口要写。** 接口返回的数组、组件收到的 props、模块导出的常量，这些地方写 `Message[]`、`Message`。形状一变，错误在入口就出现。
- **局部变量可以不写。** `const first = ...`、`const snippet = ...`，推断已经够用。每个变量都补注解，只会让代码更长，改动时还多一处要同步。
- **返回值建议写。** 不写也能推断，但写上以后，函数体里不小心改成返回 `number` 会立刻报错，而不是等调用方踩到。

**注解写在边界上，中间靠推断**。这是让类型有用又不吵人的分法。

## 从留言字段到函数签名 {#basic-types}

一条留言用到了 JavaScript 里最常见的几类值。新建 `basic.ts`：

```ts
type Message = {
  id: number;
  author: string;
  text: string;
  createdAt: string;
};

const pinned: boolean = false;
const editedAt: string | null = null;
const tags: string[] = ["闲聊", "约饭"];
const meta: { total: number; page: number } = { total: 2, page: 1 };

type MessageFormatter = (message: Message) => string;

const shortFormat: MessageFormatter = (message) =>
  `${message.author}：${message.text}`;

console.log(
  shortFormat({
    id: 1,
    author: "小林",
    text: "今晚一起吃饭吗？",
    createdAt: "2026-10-24T19:02:00+08:00",
  }),
);
console.log(pinned, editedAt, tags.length, meta.total);
```

```bash
npx tsc basic.ts --strict --target es2020
node basic.js
```

输出：

```
小林：今晚一起吃饭吗？
false null 2 2
```

拆开看这些类型：

| 写法 | 表示什么 |
|---|---|
| `number` | 整数、小数、`NaN`、`Infinity` 都是它；没有单独的 `int` 或 `float` |
| `string` | 文本，单引号、双引号、反引号写出来的都算 |
| `boolean` | `true` 或 `false` |
| `string \| null` | 要么是字符串，要么是 `null`；不允许别的值混进来 |
| `string[]` | 字符串数组；`Array<string>` 是同一个意思 |
| `{ total: number; page: number }` | 对象，两个字段都必须有，类型分别是数字 |

`tags` 和 `meta` 故意写成两种对象形状：数组用 `[]` 后缀，单个对象用花括号描述字段。对象形状如果要在几个地方复用，就抽成 `Message` 这样的 `type`，别每次都抄一遍花括号。

再看函数类型。`(message: Message) => string` 表示「收一个 `Message`，返回 `string`」。`shortFormat` 声明成这个类型后，参数 `message` 不必再写注解，上下文已经告诉编译器它是什么。返回值也会被检查：

```ts
const wrongFormat: MessageFormatter = (message) => message.id; // TS2322: Type 'number' is not assignable to type 'string'.
```

`message.id` 是 `number`，函数类型要求返回 `string`，箭头函数写出来的那一刻就能发现。把 `message` 写成 `any` 再取 `.id`，这条检查就没了。

## any 和 unknown 差在哪 {#any-unknown}

接口回来的东西最不可信。先看两个都能装下「任何值」的类型，它们的脾气完全不同。新建 `loose.ts`：

```ts
const loose: any = "你好";
const count: number = loose;
console.log(count, typeof count);
```

```bash
npx tsc loose.ts --strict --target es2020
node loose.js
```

输出：

```
你好 string
```

`loose` 是 `any`，把它赋给 `number` 不报错。编译通过了，运行时 `count` 仍然是字符串。`any` 不是「更宽松的类型」，它是**关掉这一段的检查**：取属性、调用函数、赋值给任何类型，全放行，而且会沿着赋值继续传染。

换成 `unknown`，新建 `unknown-bad.ts`：

```ts
const payload: unknown = "你好";
const size: number = payload; // TS2322: Type 'unknown' is not assignable to type 'number'.
```

同样的值，这次编译不过。`unknown` 接受任何值进来，但在你证明它是什么之前，不许把它当别的类型用。取属性也一样：

```ts
const payload: unknown = "你好";
const textLength: number = payload.length; // TS18046: 'payload' is of type 'unknown'.
```

要让它工作，得先用 `typeof`、`in`、`instanceof` 或判空把范围缩小。新建 `boundary.ts`：

```ts
function readText(payload: unknown): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "text" in payload &&
    typeof payload.text === "string"
  ) {
    return payload.text.trim();
  }
  return "（没有正文）";
}

console.log(readText({ text: "  你好  " }));
console.log(readText({ body: "你好" }));
```

```bash
npx tsc boundary.ts --strict --target es2020
node boundary.js
```

输出：

```
你好
（没有正文）
```

四个条件各挡一类坏输入：`typeof payload === "object"` 先要求它是个对象；`payload !== null` 排除 `null`，因为 `typeof null` 也是 `"object"`；`"text" in payload` 要求字段存在；`typeof payload.text === "string"` 要求值真的是字符串。四条都过了，函数体里才允许调用 `.trim()`。

`any` 和 `unknown` 的选择很直接：**外部数据用 `unknown`，然后检查；`any` 只在自己明确知道在拆什么、并且很快会收拾的地方临时用**。用 `any` 把错误压下去，只是把报错时间从编译期挪到用户点按钮的时候。

## 编译之后，类型一个字都不剩 {#erased}

类型检查通过，不代表 `.js` 里还留着类型。重新编译 `board.ts`，把结果放到 `dist`：

```bash
npx tsc board.ts --strict --target es2020 --outDir dist
```

用编辑器打开 `dist/board.js`（PowerShell 里可以 `type dist\board.js`），内容像这样：

```js
"use strict";
const messages = [
    {
        id: 1,
        author: "小林",
        text: "今晚一起吃饭吗？",
        createdAt: "2026-10-24T19:02:00+08:00",
    },
    {
        id: 2,
        author: "阿岚",
        text: "好，七点见。",
        createdAt: "2026-10-24T19:03:00+08:00",
    },
];
function formatMessage(message) {
    return `${message.author}：${message.text}`;
}
console.log(formatMessage(messages[0]));
```

`type Message` 整段消失了，`message: Message` 只剩 `message`，`): string` 也不见了。**类型在编译时被擦除**，运行的是纯 JavaScript。浏览器和 Node 不知道 `Message` 是什么，也不会检查传进来的对象有没有 `createdAt`。

这不是缺陷，是 TypeScript 能直接跑在现有 JavaScript 生态里的原因：它只在开发阶段加一层检查，产物不需要新的运行时。代价是，任何绕过编译器的数据——`JSON.parse`、`fetch` 的响应、第三方脚本——都不会被这层检查碰过。

## 四个以为类型能替你做的事 {#pitfalls}

**「类型会在运行时检查。」** 不会。上一节的 `dist/board.js` 里没有任何类型信息。下面这段编译通过，运行时 `id` 仍然是字符串：

```ts
const data: unknown = JSON.parse('"7"');
const id = data as number;
console.log(typeof id);   // "string"
```

`as number` 只是让编译器相信你，不是转换函数。要在运行时确认，得写 `typeof data === "number"` 这样的检查。

**「any 只是比 unknown 宽松一点。」** 差得远。`any` 会让整条赋值链上的检查一起失效：

```ts
const loose: any = "你好";
const count: number = loose;
console.log(count.toFixed(2));   // 编译通过，运行时报错
```

`count` 被当成数字，调用了数字才有的 `toFixed`；运行时它其实是字符串，直接抛 `TypeError`。`unknown` 在这里会先要求你确认类型，根本走不到这一步。

**「每个变量都该写类型。」** 不必要的注解会让代码变吵，还会制造第二份需要同步的真相。`const first = messages[0]` 已经是 `Message`，再写 `const first: Message` 没有增加信息。把注解留给函数边界和数据入口。

**「`as` 能把值转成想要的类型。」** 它能把编译器的嘴堵上，不能改变运行时。下面这段的输出是 `121`，不是 `13`：

```ts
const raw = "12";
const price = raw as unknown as number;
console.log(price + 1);
```

`raw` 还是字符串，`+` 做的是拼接。看到自己写出 `as unknown as`，先停一下：这通常说明前后两个类型本来就不该直接接上，中间需要一个真正的解析步骤，比如 `Number(raw)`。

## 类型写到什么程度才划算 {#tradeoffs}

类型写得越细，编译期能挡住的错误越多，维护成本也越高。分界线可以按下面几条来划。

**公开接口写清楚，内部实现留余地。** 导出的函数、组件 props、API 响应、共享数据结构，这些地方值得完整注解；一个只在这个文件里用两行的临时变量，交给推断。

**外部输入先当 `unknown`。** 从网络、文件、`localStorage` 拿到的值，形状由外部决定。先 `unknown`，在边界处验证，验证后再让内部代码使用具体类型。直接把 `JSON.parse` 的结果断言成 `Message`，等于把检查责任推给未来的自己。

**把 `strict` 打开。** 这一篇的命令都带 `--strict`。它可以一次打开 `strictNullChecks` 等一组检查；不开的话，`null` 和 `undefined` 能悄悄混进不该出现的分支，很多错误要等运行时才炸。团队项目通常把 `strict` 写进 `tsconfig.json`，而不是每次敲命令。

**别比赛写复杂类型。** 条件类型、映射类型、递归类型能表达很精妙的关系，也能让读代码的人先花十分钟解谜。类型的作用是降低理解成本；一段类型比它保护的代码还长时，先考虑把数据结构简化。

**类型和测试各管一段。** 类型能证明「这个对象有 `text` 字段且是字符串」，证明不了「这条留言属于当前用户」「金额没有超过余额」。形状之外的行为，仍然要靠测试和运行时校验。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这行会通过 `tsc` 吗？运行时 `id` 是什么？

```ts
const id: string = 1;
```

> **答案**
>
> 不会通过。报 `TS2322: Type 'number' is not assignable to type 'string'`。
>
> 注解不负责转换，只负责检查。确实要字符串，就在运行时转：`const id: string = String(1);`；如果这个字段本来就该是数字，把注解改成 `number`。

**第 2 题**：`const value: unknown = "hi"; console.log(value.toUpperCase());` 为什么会报错？怎么改？

> **答案**
>
> `unknown` 不允许直接使用，报 `TS18046: 'value' is of type 'unknown'`。先确认它是字符串：
>
> ```ts
> const value: unknown = "hi";
> if (typeof value === "string") {
>   console.log(value.toUpperCase());
> }
> ```
>
> 把 `unknown` 换成 `any` 也能让错误消失，但运行时如果传进来的是数字，`.toUpperCase` 仍然会崩。

**第 3 题**：写一个 `MessageFormatter` 类型，再写一个只返回 `Message.id` 的函数赋给它。`tsc` 会指出什么？

> **答案**
>
> ```ts
> type Message = {
>   id: number;
>   author: string;
>   text: string;
>   createdAt: string;
> };
>
> type MessageFormatter = (message: Message) => string;
>
> const formatter: MessageFormatter = (message) => message.id;
> // TS2322: Type 'number' is not assignable to type 'string'.
> ```
>
> 参数 `message` 不用注解，上下文已经给出 `Message`；返回的 `message.id` 是 `number`，与 `string` 不符。

## 继续阅读 {#related}

- [JavaScript 的变量与值](/learn/js-values)
- [联合类型与类型收窄](/learn/ts-unions)
- [interface、type 与结构契约](/learn/ts-interfaces)
- [类型注解：把接口约定写出来](/learn/python-annotations)

## 参考资料 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
