# 联合类型与类型收窄

## 留言加载时有哪三种状态 {#three-states}

读完这一篇，你能用联合类型写出加载留言的三种状态，并让 TypeScript 检查你有没有漏掉一种。

打开留言板，可能发生三件事：请求还没回来、请求成功拿到一串留言、请求失败拿到一条错误信息。很多页面用三个变量分别记：`loading` 是布尔值，`messages` 可能为空，`error` 也可能为空。写起来方便，组合起来有八种，其中五种不该存在。

先把三种情况写成一个类型。新建项目并装编译器：

```bash
mkdir message-board
cd message-board
npm init -y
npm i -D typescript
```

如果上一篇的 `message-board` 目录还在，跳过第一行，直接从 `cd` 开始。

新建 `state.ts`：

```ts
type Message = {
  id: number;
  author: string;
  text: string;
  createdAt: string;
};

type MessagesState =
  | { status: "loading" }
  | { status: "success"; messages: Message[] }
  | { status: "error"; message: string };

function render(state: MessagesState): string {
  switch (state.status) {
    case "loading":
      return "加载中…";
    case "success":
      return state.messages.map((m) => `${m.author}：${m.text}`).join("\n");
    case "error":
      return `出错了：${state.message}`;
  }
}

const loading: MessagesState = { status: "loading" };

const success: MessagesState = {
  status: "success",
  messages: [
    {
      id: 1,
      author: "小林",
      text: "今晚一起吃饭吗？",
      createdAt: "2026-10-24T19:02:00+08:00",
    },
  ],
};

const error: MessagesState = { status: "error", message: "网络断了" };

console.log(render(loading));
console.log(render(success));
console.log(render(error));
```

```bash
npx tsc --strict --target es2020 state.ts
node state.js
```

你应该看到：

```
加载中…
小林：今晚一起吃饭吗？
出错了：网络断了
```

`MessagesState` 不是「一个有可选字段的对象」，而是**三个对象类型的联合**。同一时刻，`state` 只能是其中一个：

| 状态 | 一定有的字段 | 一定没有的字段 |
|---|---|---|
| `loading` | `status` | `messages`、`message` |
| `success` | `status`、`messages` | `message` |
| `error` | `status`、`message` | `messages` |

三个分支靠共同的 `status` 字段区分。这个字段的值 `"loading"`、`"success"`、`"error"` 是**字符串字面量类型**，不是宽泛的 `string`。字面量是收窄能成立的关键：编译器知道 `"loading"` 和 `"success"` 不可能同时出现。

## 为什么不要把所有字段写成可选 {#optional-trap}

把上面的联合改成一个对象，字段全部标成可选，看起来更「灵活」。新建 `loose.ts`：

```ts
type Message = {
  id: number;
  author: string;
  text: string;
  createdAt: string;
};

type LooseState = {
  status: "loading" | "success" | "error";
  messages?: Message[];
  message?: string;
};

const noData: LooseState = { status: "success" };

const contradictory: LooseState = {
  status: "loading",
  messages: [],
  message: "还在加载",
};
```

`noData` 说自己是成功，却没有 `messages`；`contradictory` 一边加载，一边带着留言和错误。两行都合法。先只放这些，运行 `npx tsc --noEmit --strict loose.ts`，**没有输出**——不是写对了，而是类型允许这些组合。

到了使用端，代价出现。在文件末尾加上读取函数：

```ts
function renderLoose(state: LooseState): string {
  if (state.status === "success") {
    return state.messages.map((m) => m.text).join("\n"); // TS18048: 'state.messages' is possibly 'undefined'.
  }
  return "";
}
```

再跑一次：

```bash
npx tsc --noEmit --strict loose.ts
```

这次会报：

```
loose.ts(24,12): error TS18048: 'state.messages' is possibly 'undefined'.
```

`state.status` 已经收窄成 `"success"`，`messages` 还是可选。编译器不知道「成功就一定有留言」，因为你没在类型里说过这件事。每个读 `messages` 的地方都得补一层判空，或者写 `!` 把检查关掉；`noData` 真的走到这里时，运行时会抛 `TypeError`。

**可选字段让定义处省了一行，让所有调用处多了一次判断，还允许了不该存在的状态。** 联合类型把「成功必有 `messages`」「失败必有 `message`」写进形状里，检查一次，处处受益。

## 收窄：类型是怎么被一步步问清楚的 {#narrowing}

联合类型本身只知道「可能是这几种之一」。要在某条分支里使用具体字段，得先让编译器确认现在到底是哪一种。这个过程叫收窄。

新建 `narrow.ts`：

```ts
type Message = {
  id: number;
  author: string;
  text: string;
  createdAt: string;
};

function label(value: string | number): string {
  if (typeof value === "string") {
    return value.toUpperCase();
  }
  return value.toFixed(2);
}

type Loaded = { messages: Message[] };
type Failed = { error: string };

function describe(payload: Loaded | Failed): string {
  if ("messages" in payload) {
    return `收到 ${payload.messages.length} 条留言`;
  }
  return `失败：${payload.error}`;
}

function messageOf(error: Error | string): string {
  if (error instanceof Error) {
    return error.message;
  }
  return error;
}

function initials(name: string | null): string {
  if (name === null) {
    return "匿名";
  }
  return name.slice(0, 1);
}

console.log(label("ok"), label(3));
console.log(describe({ messages: [] }));
console.log(describe({ error: "超时" }));
console.log(messageOf(new Error("断网")), messageOf("断网"));
console.log(initials(null), initials("小林"));
```

```bash
npx tsc --strict --target es2020 narrow.ts
node narrow.js
```

输出：

```
OK 3.00
收到 0 条留言
失败：超时
断网 断网
匿名 小
```

四种检查各管一类：

- `typeof value === "string"`：把 `string | number` 分成两支。`if` 里是 `string`，`else` 里编译器知道剩下的是 `number`，所以能调 `toFixed`。
- `"messages" in payload`：按**字段是否存在**区分两个对象类型。命中后 `payload` 是 `Loaded`，`payload.messages` 才是 `Message[]`。
- `error instanceof Error`：按**是不是某个类的实例**区分。它检查对象的原型链，只对类或构造函数创建的对象有意义；字符串、数字这类原始值永远不是实例。
- `name === null`：单独把 `null` 拿掉，`if` 之后 `name` 就是 `string`。`undefined` 用 `name === undefined` 或 `name != null` 一起处理。

`typeof null` 也是 `"object"`，所以处理对象输入时，判 `typeof x === "object"` 后面通常要再补一个 `x !== null`，否则 `null` 会混进对象分支，取字段时崩。

还有一种最常用的收窄：判别字段。`state.status === "success"` 命中后，编译器把 `state` 缩小到成功那一支；不命中，另外两支继续参与后面的判断。不用写 `as`，也不用重复检查字段。

反过来，没检查就想用专属字段，编译器会拒绝：

```ts
function count(state: MessagesState): number {
  return state.messages.length; // TS2339: Property 'messages' does not exist on type 'MessagesState'.
}
```

联合类型在收窄前只暴露所有成员共有的字段。`status` 三个分支都有，所以能读；`messages` 只有成功分支有，必须先证明当前是成功。

## switch 加上 never，漏掉状态就编译不过 {#exhaustive-check}

三个分支用 `if` 也能写，但状态一多，很容易漏。`switch` 配一个 `never` 兜底，可以把「漏状态」变成编译错误。新建 `exhaustive.ts`：

```ts
type Message = {
  id: number;
  author: string;
  text: string;
  createdAt: string;
};

type MessagesState =
  | { status: "loading" }
  | { status: "success"; messages: Message[] }
  | { status: "error"; message: string };

function assertNever(value: never): never {
  throw new Error(`没处理的状态：${JSON.stringify(value)}`);
}

function render(state: MessagesState): string {
  switch (state.status) {
    case "loading":
      return "加载中…";
    case "success":
      return state.messages.map((m) => m.text).join("\n");
    case "error":
      return `出错了：${state.message}`;
    default:
      return assertNever(state);
  }
}

console.log(render({ status: "loading" }));
```

```bash
npx tsc --strict --target es2020 exhaustive.ts
node exhaustive.js
```

输出：

```
加载中…
```

`assertNever` 的参数类型是 `never`。三个分支都处理完以后，`default` 里的 `state` 已经被排除干净，剩下的类型就是 `never`，所以调用合法。函数体直接抛错，正常运行时不会走到。

现在给联合加第四种状态 `empty`，但忘了加 `case`。新建 `missing-case.ts`：

```ts
type MessagesState =
  | { status: "loading" }
  | { status: "success" }
  | { status: "error"; message: string }
  | { status: "empty" };

function assertNever(value: never): never {
  throw new Error(`没处理的状态：${JSON.stringify(value)}`);
}

function render(state: MessagesState): string {
  switch (state.status) {
    case "loading":
      return "加载中…";
    case "success":
      return "有留言";
    case "error":
      return `出错了：${state.message}`;
    default:
      return assertNever(state); // TS2345: Argument of type '{ status: "empty"; }' is not assignable to parameter of type 'never'.
  }
}

console.log(render({ status: "empty" }));
```

```bash
npx tsc --noEmit --strict missing-case.ts
```

输出：

```
missing-case.ts(20,26): error TS2345: Argument of type '{ status: "empty"; }' is not assignable to parameter of type 'never'.
```

`default` 里的 `state` 不再是 `never`，而是 `{ status: "empty" }`，`assertNever` 拒绝接收。错误落在 `default` 那一行，正好指向漏掉的分支。

如果 `default` 里写的是 `return "加载中…"`，编译不会报错。新状态会悄悄显示成加载中，等到用户截图来问，你才知道漏了。**兜底代码要么断言不可能，要么明确处理，别用一个看似安全的默认值盖住新情况。**

## 四个容易踩的联合类型坑 {#pitfalls}

下面用到 `LooseState` 的两段沿用前面的定义，它允许 `success` 状态不带 `messages`。

**「`!` 非空断言能补上缺失的数据。」** 它只是让编译器闭嘴，运行时什么都没补：

```ts
function count(state: LooseState): number {
  return state.messages!.length;   // 编译通过
}

console.log(count({ status: "loading" }));
```

`tsc` 通过，`node` 运行时抛：

```
TypeError: Cannot read properties of undefined (reading 'length')
```

`!` 适合那种「我已经在别处保证过，编译器看不出来」的场合。用它来绕开状态检查，等于把错误推迟到用户机器上。

**「`if (state.message)` 就是判空。」** 真假判断会顺手排除空字符串：

```ts
function showError(state: MessagesState): string {
  if (state.status === "error" && state.message) {
    return state.message;
  }
  return "（无错误信息）";
}

console.log(showError({ status: "error", message: "" }));
```

输出：

```
（无错误信息）
```

空字符串在这里是合法错误信息（比如后端只给了状态码），却因为 `""` 是假值被丢掉。数字字段用真假判断还会漏掉 `0`。想只排除「没有这个值」，写 `state.message !== undefined`；想连空串一起排除，就把 `&& state.message.trim() !== ""` 写清楚，别让 `if` 的隐式规则替你决定业务含义。

**「`as` 能把状态改过去。」** 转换只在类型层面发生，对象本身没变：

```ts
const state: LooseState = { status: "loading" };
const success = state as { status: "success"; messages: Message[] };
console.log(success.messages.length);   // 编译通过，运行时报错
```

这段能过 `tsc`，运行时抛 `TypeError: Cannot read properties of undefined (reading 'length')`。`as` 是「我知道我在干什么」的声明，不是状态迁移。状态要变，得真的构造一个新对象。

**「`status` 写成 `string` 也一样。」** 不一样。字面量类型的联合才能区分分支：

```ts
type WideState = {
  status: string;
  messages?: string[];
};

function read(state: WideState): string {
  if (state.status === "success") {
    return state.messages.join("\n"); // TS18048: 'state.messages' is possibly 'undefined'.
  }
  return "";
}
```

`status` 的类型是 `string`，`=== "success"` 只排除了一个值，排不掉 `"error"`、`"loading"` 或任何别的字符串；`messages` 仍然是可选。判别字段要用字面量联合或 `as const` 固定下来，别在声明时把它放宽成 `string`。

## 什么时候该用联合，什么时候不用 {#tradeoffs}

联合类型适合**有限、互斥、每个分支该带的字段不同**的情况：异步请求状态、表单提交结果、API 的多种返回、工具执行的成功与失败。

代价是真实的：每个分支都要写处理代码，类型定义变长，组件里多一个 `switch`。如果这些状态本来就不会互相冲突，或者只有一个字段可能缺席，联合类型是过度设计。

判断可以看三个问题：

1. **非法组合会造成 bug 吗？** `loading` 同时带着旧留言和错误信息，会让界面显示什么？如果这种组合一出现就出问题，用判别联合。
2. **调用方需要知道哪个字段一定存在吗？** 成功分支要用 `messages`，失败分支要用 `message`，联合能把这件事写死；可选字段做不到。
3. **状态会继续增加吗？** 会增加，`assertNever` 能逼着每次新增时处理所有分支；不会增加，简单的 `string | null` 可能就够了。

常见的坏味道是布尔标志加深层可选字段：`loading: boolean`、`error?: string`、`data?: T`。它允许「既在加载又失败」「加载完了但没有任何数据」这类组合，调用方只能靠注释和记忆猜。收敛成一个 `status` 字段，组合数从八种降到三种，判断也跟着变简单。

判别字段的值要稳定、可读，别用 `0/1/2` 这种要靠映射表才能读懂的数字。`"loading"`、`"success"`、`"error"` 出现在日志、测试和调试器里，本身就能说明问题。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：给 `MessagesState` 加一个 `{ status: "empty" }`，`render` 里补上 `case "empty"` 返回「还没有留言」。如果忘了补，编译器会指出什么？

> **答案**
>
> 会在 `assertNever(state)` 那一行报 `TS2345`，因为 `default` 里的 `state` 是 `{ status: "empty" }`，不是 `never`。
>
> ```ts
> type MessagesState =
>   | { status: "loading" }
>   | { status: "success"; messages: Message[] }
>   | { status: "error"; message: string }
>   | { status: "empty" };
>
> function render(state: MessagesState): string {
>   switch (state.status) {
>     case "loading":
>       return "加载中…";
>     case "success":
>       return state.messages.map((m) => m.text).join("\n");
>     case "error":
>       return `出错了：${state.message}`;
>     case "empty":
>       return "还没有留言";
>     default:
>       return assertNever(state);
>   }
> }
> ```

**第 2 题**：写一个 `formatValue(value: string | number): string`，字符串原样返回，数字保留两位小数。

> **答案**
>
> ```ts
> function formatValue(value: string | number): string {
>   if (typeof value === "string") {
>     return value;
>   }
>   return value.toFixed(2);
> }
> ```
>
> `typeof` 检查之后，`else` 分支里的 `value` 被收窄成 `number`，才能调用 `toFixed`。不写检查直接 `value.toFixed(2)` 会报 `TS2339: Property 'toFixed' does not exist on type 'string | number'`。

**第 3 题**：为什么 `{ status: "success" }` 能赋给 `LooseState`，却不能赋给 `MessagesState`？

> **答案**
>
> `LooseState` 的 `messages` 是可选字段，省略合法；`status` 又是 `"success"`，所以整体合法。
>
> `MessagesState` 的成功分支要求 `messages: Message[]` 必填，省略就违反形状。正是这个必填约束，让成功分支里的 `state.messages` 不再需要判空。

## 继续阅读 {#related}

- [TypeScript 的类型注解与推断](/learn/ts-types)
- [可选字段、null 与安全访问](/learn/ts-nullability)
- [State、重新渲染与状态快照](/learn/react-state)
- [URL、JSON 与 API 契约](/learn/web-api)

## 参考资料 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
