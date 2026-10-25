# 泛型：保留输入与输出的类型关系

## 一条留言和它的第一条 {#overview}

读完这一篇，你能把取首项的 first 写成泛型，让调用方拿到 Message，而不是 any。

留言板要在页头显示最新一条留言。列表是 `Message[]`，你写了一个 `first(messages)`，只取第一条。

为了让它也能处理数字数组、字符串数组，你把参数写成 `any[]`。函数确实什么都能收，但交回来的东西也变成了 `any`。

`any` 的意思是"别再检查了"。后面会看到，属性名拼错 tsc 也不出声，错误留到浏览器里才炸。泛型要解决的就是这个：同一段代码适用于多种类型，同时保留"输入什么、输出什么"的关系。

## 把 first 从 any 改成泛型 {#first-generic}

新建 `board.ts`，放进下面这段：

```ts
type Message = {
  id: string;
  author: string;
  content: string;
};

const messages: Message[] = [
  { id: "m1", author: "小林", content: "周报写完了" },
  { id: "m2", author: "小周", content: "明早一起看" },
];

function first(items: any[]) {
  return items[0];
}

const msg = first(messages);
console.log(msg.author.toUpperCase());
console.log(msg.auther.toUpperCase()); // tsc 不报错，运行时 TypeError
```

编译，再运行：

```bash
npx tsc board.ts --strict --target es2022
node board.js
```

终端的前两行是：

```
小林
TypeError: Cannot read properties of undefined (reading 'toUpperCase')
```

`tsc` 一行错也没报。`msg` 的类型是 `any`，所以 `msg.auther` 这种拼写错误被直接放行，编辑器的自动补全也给不出 `Message` 的字段。运行时它读到 `undefined`，调用 `.toUpperCase()` 才崩，调用栈指向 `console.log` 那一行。

把 `first` 换掉：

```ts
function first<T>(items: T[]): T | undefined {
  return items[0];
}
```

`<T>` 声明了一个类型参数。`items: T[]` 说的是"某个类型的数组"，`T | undefined` 说的是"同一个类型的一项，或者空数组时的 undefined"。

现在 `const msg = first(messages)` 的类型是 `Message | undefined`。拼错的属性会在编译时被点名：

```ts
const msg = first(messages);
if (msg) {
  console.log(msg.author.toUpperCase());
  console.log(msg.auther.toUpperCase());
  // TS2551: Property 'auther' does not exist on type 'Message'. Did you mean 'author'?
}
```

把 `auther` 改回 `author`，编译通过，运行输出 `小林`。

`first` 没有为 `Message` 写死。`first([1, 2])` 的类型是 `number | undefined`，`first(["a", "b"])` 是 `string | undefined`。同一个函数，三种结果，关系都在。

## T 是怎么从参数走到返回值的 {#inference}

调用 `first(messages)` 时，tsc 做了一次类型匹配：参数要求 `T[]`，实参是 `Message[]`，所以 `T` 取 `Message`。返回类型里的 `T` 跟着变成 `Message`，合起来就是 `Message | undefined`。

这个推断不需要你手写类型参数。下面三种写法等价，第一种最常用：

```ts
const a = first(messages);              // Message | undefined
const b = first<Message>(messages);     // 显式指定 T，结果同上
const c = first<string>(["小林"]);      // string | undefined
```

如果调用处不检查就取属性，tsc 会拦：

```ts
const msg = first(messages);
msg.author.toUpperCase();
// TS18048: 'msg' is possibly 'undefined'.

const title: string = first(messages);
// TS2322: Type 'Message | undefined' is not assignable to type 'string'.
//   Type 'undefined' is not assignable to type 'string'.
```

前一个错误不是泛型的毛病，而是返回类型诚实地说出了"可能没有"。空数组没有第一项，函数返回 `undefined`；类型把这件事写明，调用方就得先判断。后一个错误更能看出关系：编译器知道结果是 `Message | undefined`，不会让你把它当普通字符串。

泛型在运行时不存在。`tsc` 把类型擦掉后，编译出的 JS 里没有 `<T>`，也没有为 `Message` 和 `number` 各生成一份 `first`。它只帮你检查类型，不改变函数怎么执行。

## extends 约束与默认类型参数 {#constraints}

`first` 不关心元素长什么样。换一个函数，它需要读 `id`：

```ts
type Message = {
  id: string;
  author: string;
  content: string;
};

const messages: Message[] = [
  { id: "m1", author: "小林", content: "周报写完了" },
  { id: "m2", author: "小周", content: "明早一起看" },
];

function findById<T extends { id: string }>(items: T[], id: string): T | undefined {
  return items.find((item) => item.id === id);
}

type Draft = { name: string };
const drafts: Draft[] = [{ name: "小林" }];

const found = findById(messages, "m2");   // Message | undefined
const nobody = findById(drafts, "m1");
// TS2345: Argument of type 'Draft[]' is not assignable to parameter of type '{ id: string; }[]'.
//   Property 'id' is missing in type 'Draft' but required in type '{ id: string; }'.
```

`T extends { id: string }` 是约束，不是类继承。它要求传进来的 `T` 至少有一个字符串类型的 `id`，别的字段随意。`Message` 满足，`Draft` 不满足，`findById(drafts, ...)` 在编译期就被拒绝。

去掉约束会怎样？函数体里的 `item.id` 会报 `TS2339: Property 'id' does not exist on type 'T'.`，因为 `T` 可能是任何东西。把约束写成 `T extends Message` 又太紧，只有 `Message` 能用，别的带 `id` 的记录类型进不来。

返回类型仍然写 `T | undefined`，所以 `found` 拿到的是 `Message`，不是宽成 `{ id: string }`。约束只规定"至少有什么"，不抹掉"实际是什么"。

默认类型参数是另一种省事写法：

```ts
interface ListResponse<T = Message> {
  items: T[];
  total: number;
}

const res: ListResponse = { items: messages, total: messages.length };
// res.items 是 Message[]

const draftRes: ListResponse<Draft> = { items: drafts, total: drafts.length };
// 需要别的类型时，显式写 T
```

`<T = Message>` 的意思是不写类型参数时用 `Message`。它适合"大多数调用都是这个类型"的接口；没有明显默认值的容器不要硬加，否则读者要多想一层。

## keyof 与 T[K]：按字段名取值 {#keyof}

写一个读字段的小函数，字段名由调用方给：

```ts
function getField<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

const msg: Message = { id: "m1", author: "小林", content: "周报写完了" };
const author = getField(msg, "author");   // string
const id = getField(msg, "id");           // string
const bad = getField(msg, "auther");
// TS2345: Argument of type '"auther"' is not assignable to parameter of type 'keyof Message'.
```

拆开看：

- `keyof T` 是 `T` 所有属性名组成的联合。`keyof Message` 就是 `"id" | "author" | "content"`。
- `K extends keyof T` 把 `key` 限制在这几个字符串里，写错名字编译不过。
- `T[K]` 是索引访问类型，表示"`T` 里 `K` 这个字段的类型"。传 `"author"` 得到 `string`，传 `"id"` 也得到 `string`；如果字段是 `editedAt?: string`，就会得到 `string | undefined`。

这三样必须一起出现才有用。把返回类型改成 `any`，函数也能返回字段值，但调用方拿不到具体类型；把 `K` 改成 `string`，`obj[key]` 又过不了类型检查。

`getField` 的返回值跟着字段名变。`const n: number = getField(msg, "author")` 会报错，因为 `"author"` 对应 `string`。这不是运行时的判断，是编译期从字段名推出来的。

## 四个关于泛型的错误预期 {#limits}

**"泛型函数里可以 `new T()`。"** 不行。`T` 只是类型，不能当值用：

```ts
function make<T>(): T {
  return new T();
  // TS2693: 'T' only refers to a type, but is being used as a value here.
}

function kind<T>(): string {
  return typeof T;
  // TS2693: 'T' only refers to a type, but is being used as a value here.
}
```

要用构造函数，得把构造函数本身作为参数传进来，或者给 `T` 一个带 `new` 签名的约束。`typeof T` 同理，类型在编译后已经没了。

**"调用方写 `first<any>(messages)` 就安全了。"** 不安全。显式传 `any` 会把输出也变成 `any`，等于回到文章开头那版。泛型不会纠正你主动放弃检查的行为。

**"类型参数越多，函数越通用。"** 每多一个类型参数，调用方就多一层要理解的东西。只有确实存在"两个位置必须是同一个类型"时，参数才有用。`function pair<A, B>(a: A, b: B)` 看着通用，但 `A` 和 `B` 没有彼此约束，调用方直接写具体类型更清楚。

**"泛型能根据值做运行时分支。"** 不能。`if (typeof value === "string")` 判断的是值，不是 `T`；编译器不会因为你在函数里判断了类型，就改变泛型参数。

## 什么时候不该写泛型 {#when-to-skip}

判断标准只有一条：**类型参数是否在至少两个位置承担同一个类型关系**。

`first<T>(items: T[]): T | undefined` 满足：元素从参数进，从返回出。`getField<T, K>` 满足：对象和字段名一起决定返回类型。`findById<T extends { id: string }>` 也满足：数组元素和返回值是同一个 `T`。

反例：

```ts
function printLabel<T>(label: T): void {
  console.log(label);
}

printLabel<string>("留言");
printLabel<number>(42);
```

`T` 只出现在参数里，返回 `void`，没有第二个位置跟它对应。这个函数用 `unknown` 或 `string` 就够了；写成泛型只是让调用方多写一个类型参数。

还有一种常见浪费：只有一个实现类型的 `ListResponse<T = Message>`。如果全项目只有 `Message` 一种列表，`interface ListResponse { items: Message[]; total: number }` 更好读。等第二种列表真的出现，再抽 `T`。

泛型的代价在签名上。类型参数越多，报错信息越长，调用方越难判断该传什么。先在具体类型上把逻辑写对，等第二个真实用例出现，再把它抽成泛型。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：为什么 `first(messages)` 的类型是 `Message | undefined`，而不是 `Message`？

> **答案**
>
> 因为数组可能是空的。空数组没有第一项，`items[0]` 的值是 `undefined`。返回类型把这个可能性写了出来，调用方必须先判断再取属性。
>
> 如果硬写 `T` 不带 `undefined`，在没开 `noUncheckedIndexedAccess` 的项目里照样能编译，但类型就在说谎：空数组时调用方仍会拿到 `undefined`。

**第 2 题**：照着 `first` 写一个 `last`，取数组末尾一项，保留元素类型。

> **答案**
>
> ```ts
> function last<T>(items: T[]): T | undefined {
>   return items[items.length - 1];
> }
>
> const msg = last(messages);   // Message | undefined
> const n = last([1, 2, 3]);    // number | undefined
> ```
>
> `T` 同时出现在参数和返回类型里，推断会沿着 `items` 的元素类型走。

**第 3 题**：`function printLabel<T>(label: T): void` 为什么不需要泛型？

> **答案**
>
> 因为 `T` 只出现一次，没有第二个位置跟它建立关系。函数不返回 `T`，也不接收第二个 `T`，调用方选中什么类型对函数的类型检查没有影响。
>
> 写成 `function printLabel(label: unknown): void` 或 `string` 都更直接；真要保留"原样返回"，再写成返回 `T` 就有意义了。

## 继续阅读 {#related}

- [TypeScript 的类型注解与推断](/learn/ts-types)
- [联合类型与类型收窄](/learn/ts-unions)
- [interface、type 与结构契约](/learn/ts-interfaces)
- [为 React props 与事件声明类型](/learn/ts-react)

## 参考资料 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
