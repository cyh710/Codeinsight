# interface、type 与结构契约

## 一条留言，两种写法 {#two-ways}

读完这一篇，你能用 interface 或 type 描述留言，知道两者何时能换、何时不能，也明白运行时数据为什么可能不守约定。

前端要渲染留言，后端说会返回 `id`、`author`、`text`、`createdAt`。你想先在类型文件里把这个形状写下来。`interface` 和 `type` 都能做这件事，先各写一遍。

建项目，装编译器：

```bash
mkdir message-board
cd message-board
npm init -y
npm i -D typescript
```

如果前面的 `message-board` 目录还在，跳过第一行，直接从 `cd` 开始。

新建 `message.ts`：

```ts
interface Message {
  id: number;
  author: string;
  text: string;
  createdAt: string;
}

type MessageAlias = {
  id: number;
  author: string;
  text: string;
  createdAt: string;
};

interface Formatter {
  (message: Message): string;
}

type FormatterAlias = (message: Message) => string;

const fromInterface: Message = {
  id: 1,
  author: "小林",
  text: "今晚一起吃饭吗？",
  createdAt: "2026-10-24T19:02:00+08:00",
};

const fromType: MessageAlias = {
  id: 2,
  author: "阿岚",
  text: "好，七点见。",
  createdAt: "2026-10-24T19:03:00+08:00",
};

const short: Formatter = (message) => `${message.author}：${message.text}`;
const shortAlias: FormatterAlias = short;

function format(message: Message): string {
  return shortAlias(message);
}

console.log(format(fromInterface));
console.log(format(fromType));
```

```bash
npx tsc --strict --target es2020 message.ts
node message.js
```

你应该看到：

```
小林：今晚一起吃饭吗？
阿岚：好，七点见。
```

`interface Message` 声明一个对象类型，成员逐个列出。`type MessageAlias = { ... }` 给一个对象类型表达式起名。这两块描述的是同一个形状，`fromType` 传给要求 `Message` 的 `format` 也不报错——名字不同，形状相同。

函数类型也能互写：`interface Formatter` 用调用签名 `(message: Message): string`，`type FormatterAlias` 用箭头写法。对调用方来说，它们都是「收一条留言，返回字符串」。

这两种写法在描述对象形状时基本等价。真正需要选的时候，看下面几处差异。

## 什么时候能互换，什么时候不能 {#interchangeable}

| 需求 | `interface` | `type` |
|---|---|---|
| 描述对象字段 | 可以 | 可以 |
| 描述函数类型 | 可以，用调用签名 | 可以，用箭头写法 |
| 给联合类型起名 | 不能 | 可以 |
| 同名声明自动合并 | 可以 | 不能 |
| 给 `string`、元组等起别名 | 不能 | 可以 |

最硬的一条差异是联合类型。加载留言时的三种状态只能写成 `type`：

```ts
type MessageState =
  | { status: "loading" }
  | { status: "success"; messages: Message[] }
  | { status: "error"; message: string };
```

`interface` 描述的是**一个**对象形状，没有「这几选一」的语法。你可以勉强写一个带可选字段的接口，但那会允许「加载中同时有留言和错误」这种组合，正是联合类型要排除的东西。

另一条差异是声明合并。新建 `merge.ts`，同名的 `interface` 会合并成员：

```ts
interface Message {
  id: number;
  author: string;
  text: string;
  createdAt: string;
}

interface Message {
  pinned?: boolean;
}

const message: Message = {
  id: 1,
  author: "小林",
  text: "今晚一起吃饭吗？",
  createdAt: "2026-10-24T19:02:00+08:00",
  pinned: true,
};

console.log(message.pinned);
```

```bash
npx tsc --strict --target es2020 merge.ts
node merge.js
```

输出：

```
true
```

两段 `interface Message` 被当成同一个类型的补充。库的类型扩展、插件给宿主类型加字段，靠的就是这个机制。`type` 不行，新建 `merge-bad.ts`，同名写两次是重复声明：

```ts
type Message = {
  id: number;
  author: string;
};

type Message = { // TS2300: Duplicate identifier 'Message'.
  text: string;
};
```

```bash
npx tsc --noEmit --strict merge-bad.ts
```

输出：

```
merge-bad.ts(1,6): error TS2300: Duplicate identifier 'Message'.
merge-bad.ts(6,6): error TS2300: Duplicate identifier 'Message'.
```

`type` 还能给基本类型、元组、映射类型起名，比如 `type UserId = string;`、`type Pair = [number, number];`。`interface` 只能描述对象形状（函数和类也算对象形状），写不了 `interface UserId = string`。

选择标准可以落到用途：**共享的对象契约用 `interface`，需要联合、交叉、基本类型别名时用 `type`**。同一个项目里保持一种风格，比争论哪个「更好」更有价值。

## 可选字段和只读字段改的是调用方 {#optional-readonly}

留言可能被编辑过，也可能从没编辑过。`id` 创建后不该改。新建 `readonly.ts`，这两件事分别用 `?` 和 `readonly` 写：

```ts
interface Message {
  readonly id: number;
  author: string;
  text: string;
  createdAt: string;
  editedAt?: string;
}

const message: Message = {
  id: 1,
  author: "小林",
  text: "今晚一起吃饭吗？",
  createdAt: "2026-10-24T19:02:00+08:00",
};

message.author = "小林（改了昵称）";

const alias = message as { id: number };
alias.id = 2;

console.log(message.author);
console.log(message.id);
console.log(message.editedAt?.slice(0, 10) ?? "没有编辑过");
```

```bash
npx tsc --strict --target es2020 readonly.ts
node readonly.js
```

输出：

```
小林（改了昵称）
2
没有编辑过
```

`editedAt?: string` 表示这个字段**可以不存在**。读取时类型是 `string | undefined`，所以用了 `?.`；没有编辑过时返回 `"没有编辑过"`。省略字段和写 `editedAt: undefined` 在默认配置下都能通过，打开 `exactOptionalPropertyTypes` 后才只允许省略。它与 `editedAt: string | null` 不同：后者要求字段存在，值可以是 `null`。后端 JSON 常把「没有」发成 `null`，两边要对齐，别让 `?` 和 `| null` 混着猜。

`readonly id` 禁止通过 `Message` 类型的引用改 `id`：

```ts
message.id = 2; // TS2540: Cannot assign to 'id' because it is a read-only property.
```

但上面代码里的 `alias` 声明成了 `{ id: number }`，没有 `readonly`，所以 `alias.id = 2` 通过，输出里的 `id` 变成了 2。`readonly` 是**编译期的写入约束，不是运行时冻结**；它只约束经过这个类型检查的写法，换个类型引用就能绕开。

还有一层：`readonly` 是浅的。它挡住 `message.editedAt = ...` 这种重新赋值，挡不住字段内部的变化。`readonly tags: string[]` 仍然允许 `tags.push(...)`；要禁止数组内容变化，得写 `readonly string[]`。真正要运行时不可变，用 `Object.freeze`，而且深嵌套对象需要逐层冻结。

可选和只读都会把成本推给调用方：每读一次可选字段就要处理 `undefined`，每传一次只读字段就可能需要复制。字段确实可缺、确实不该改时再用，别把所有字段都标成 `?` 或 `readonly` 求安心。

## extends 与交叉类型：拼接口的两种办法 {#extends-intersection}

留言有作者、有创建时间、有正文。把公共部分拆开，再拼起来，有两种写法。新建 `compose.ts`：

```ts
interface Authored {
  author: string;
}

interface Dated {
  createdAt: string;
}

interface Message extends Authored, Dated {
  id: number;
  text: string;
}

type MessageByIntersection = Authored &
  Dated & {
    id: number;
    text: string;
  };

const viaExtends: Message = {
  id: 1,
  author: "小林",
  text: "今晚一起吃饭吗？",
  createdAt: "2026-10-24T19:02:00+08:00",
};

const viaIntersection: MessageByIntersection = viaExtends;

console.log(viaIntersection.author);
```

```bash
npx tsc --strict --target es2020 compose.ts
node compose.js
```

输出：

```
小林
```

`interface Message extends Authored, Dated` 继承两个接口的成员，再加上自己的 `id` 和 `text`。`type MessageByIntersection = Authored & Dated & {...}` 用交叉类型把三个形状合并。形状兼容时，两种写法得到的结果一样，`viaExtends` 能直接赋给 `MessageByIntersection`。

冲突时，差别就出来了。新建 `conflict.ts`：

```ts
interface A {
  id: number;
}

interface B {
  id: string;
}

interface C extends A, B {} // TS2320: Interface 'C' cannot simultaneously extend types 'A' and 'B'.

type D = A & B;

const d: D = { id: 1 }; // TS2322: Type 'number' is not assignable to type 'never'.

console.log(d);
```

```bash
npx tsc --noEmit --strict conflict.ts
```

输出：

```
conflict.ts(9,11): error TS2320: Interface 'C' cannot simultaneously extend types 'A' and 'B'.
  Named property 'id' of types 'A' and 'B' are not identical.
conflict.ts(13,16): error TS2322: Type 'number' is not assignable to type 'never'.
```

`interface C extends A, B` 在声明处就被拒绝：`id` 不可能同时是 `number` 和 `string`。交叉类型 `A & B` 不在声明处报错，它把 `id` 算成 `never`——没有任何值同时满足两个原始类型；等到你给 `d` 赋值时才炸。

**`extends` 会提前指出冲突，交叉类型把冲突留到使用处。** 拼已知兼容的形状，两者都好用；拼来自不同来源、可能同名字段冲突的类型，`extends` 的错误更早、更好读。

## 结构类型：形状对了就算兼容 {#structural-typing}

上面的 `fromType` 能传给要求 `Message` 的函数，已经露出结构类型的边。新建 `structural.ts`，再看两个更明显的例子：

```ts
interface Message {
  id: number;
  author: string;
  text: string;
  createdAt: string;
}

function format(message: Message): string {
  return `${message.author}：${message.text}`;
}

const rawFromServer = {
  id: 1,
  author: "小林",
  text: "今晚一起吃饭吗？",
  createdAt: "2026-10-24T19:02:00+08:00",
  serverVersion: 3,
};

class Draft {
  id = 0;
  author = "我";
  text = "";
  createdAt = new Date().toISOString();
}

const draft: Message = new Draft();

console.log(format(rawFromServer));
console.log(format(draft));
```

```bash
npx tsc --strict --target es2020 structural.ts
node structural.js
```

输出：

```
小林：今晚一起吃饭吗？
我：
```

`rawFromServer` 比 `Message` 多一个 `serverVersion`，照样能传给 `format`。TypeScript 只看**有没有满足要求的成员**：`id`、`author`、`text`、`createdAt` 都在，类型也对，就兼容。多出来的字段不影响赋值。

`Draft` 类根本没有写 `implements Message`，它的实例也能赋给 `Message`。类的公开字段构成了形状，形状匹配就行。`implements` 只是把这件事写成显式检查：`class Draft implements Message` 会在编译时确认 `Draft` 拥有全部成员；漏了 `createdAt` 会报错。它不会在运行时检查，也不会给类增加任何代码。

函数参数同理。`format` 要的是「有那四个字段的东西」，任何对象只要满足就收。这种按形状判断兼容性的规则叫**结构类型**，对公开字段来说，名字、继承关系、有没有写 `implements` 都不参与判断；带 `private` 成员的类例外。

方便的同时，它也容易放过错误。两个业务含义完全不同的对象，只要字段形状一样，就能互相赋值。比如 `{ id: number; author: string; text: string; createdAt: string }` 既可能是一条留言，也可能是某个草稿；编译器不会拦。需要区分时，可以用带标记的字段、类，或者品牌类型（`type MessageId = number & { readonly __brand: "MessageId" }`），但别为了每个 id 都造一个品牌类型。

对象字面量直接赋值时，还有一道额外检查：

```ts
const message: Message = {
  id: 1,
  author: "小林",
  text: "在吗",
  createdAt: "2026-10-25T09:00:00+08:00",
  serverVersion: 3,
  // TS2353: Object literal may only specify known properties,
  // and 'serverVersion' does not exist in type 'Message'.
};
```

这叫多余属性检查，专门抓字面量里的拼写错误和多余字段。它只在**直接写字面量**时生效；像 `rawFromServer` 那样先赋给一个变量、再传给函数，就不会触发。它不是运行时的字段白名单，别指望它挡住网络来的多字段。

## 三条容易搞混的说法 {#misconceptions}

**「`readonly` 等于对象被冻结。」** 它只挡住编译期通过该类型的赋值，浅层有效，运行时对象照样能变：

```ts
interface Tagged {
  readonly tags: string[];
}

const tagged: Tagged = { tags: ["约饭"] };
tagged.tags.push("闲聊");
console.log(tagged.tags);   // [ '约饭', '闲聊' ]
```

`readonly` 管的是 `tagged.tags = [...]` 这种重新绑定，不管数组内部。另一个没有 `readonly` 的别名引用也能改同一个对象。要在运行时冻结，用 `Object.freeze`；它也是浅的，嵌套数组还要单独冻结。

**「写了 `interface`，运行时就会检查数据。」** 不会。编译后的 JavaScript 里没有 `interface`，浏览器和 Node 都不认识它。下一节用 `JSON.parse` 看一个具体后果。

**「多写一个字段一定会被拦住。」** 只在对象字面量直接赋值时。字面量里多写 `serverVersion` 会报 `TS2353`；先放进变量再赋值就能通过，因为结构类型允许额外成员。想严格限制字段，得在运行时验证，或者用额外的类型技巧，不能只靠 `interface`。

选 `interface` 还是 `type`，除了联合与声明合并这两条硬约束，还要看维护成本：

- **对象契约用 `interface`**，尤其是会被别的模块扩展、需要声明合并的公共类型。
- **联合、交叉、基本类型别名用 `type`**，这些是它独有的表达力。
- **内部模型和网络传输形状分开**。数据库里的 `Message` 可能带 `deletedAt`、`internalScore`，接口不该原样返回；分别定义 `Message` 和 `MessageResponse`，在边界处映射，避免内部字段泄漏。
- **别在多个文件手抄同一个接口**。字段一改，总有一份忘了同步；把类型放在一个模块里导出，或者从接口描述自动生成。
- **可选字段和 `readonly` 都要付调用成本**。能保证必有的字段就别标 `?`，没有明确不可变需求就别到处 `readonly`。

## 编译期的契约，运行时可能被别的形状填进来 {#runtime-contract}

写一个和后端约定不一致的响应，看看类型检查能管到哪里。新建 `json.ts`：

```ts
interface Message {
  id: number;
  author: string;
  text: string;
  createdAt: string;
}

const body = '{"id":"7","author":null,"text":"你好"}';
const parsed = JSON.parse(body) as Message;

console.log(parsed.id + 1);
console.log(parsed.createdAt.toUpperCase()); // 运行时 TypeError：createdAt 不存在
```

```bash
npx tsc --strict --target es2020 json.ts
node json.js
```

`tsc` 通过，`node` 输出：

```
71
TypeError: Cannot read properties of undefined (reading 'toUpperCase')
```

（后面是调用栈，这里省略。）

逐行看发生了什么。`JSON.parse` 的返回值是 `any`，编译器不知道里面是什么；`as Message` 是你向编译器保证「它是这个形状」。编译通过只证明这个保证在类型层面成立，不证明运行时数据真长这样。

实际 JSON 里，`id` 是字符串 `"7"`，所以 `parsed.id + 1` 做的是字符串拼接，得到 `"71"`。`author` 是 `null`，`createdAt` 根本不存在；读 `parsed.createdAt` 得到 `undefined`，再调 `.toUpperCase()` 就抛 `TypeError`。`interface` 在这一刻帮不上忙，它已经被编译掉了。

解决办法是在边界处真的检查一遍，检查完再让内部代码相信类型。新建 `validated.ts`：

```ts
interface Message {
  id: number;
  author: string;
  text: string;
  createdAt: string;
}

function isMessage(value: unknown): value is Message {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "number" &&
    typeof candidate.author === "string" &&
    typeof candidate.text === "string" &&
    typeof candidate.createdAt === "string"
  );
}

const body = '{"id":"7","author":null,"text":"你好"}';
const parsed: unknown = JSON.parse(body);

if (isMessage(parsed)) {
  console.log(parsed.id + 1);
} else {
  console.log("数据形状不对");
}
```

```bash
npx tsc --strict --target es2020 validated.ts
node validated.js
```

输出：

```
数据形状不对
```

`isMessage` 的返回类型 `value is Message` 是**类型谓词**。函数体真的逐字段检查；返回 `true` 后，`if` 里面的 `parsed` 被收窄成 `Message`，`parsed.id` 才能当数字用。这里 `id` 是字符串，检查失败，走 `else`。

类型谓词本身也是一句承诺。如果你在函数体里直接 `return true`，编译器仍然相信，运行时照样崩。它把「检查」集中到了一个地方，但没有替你做检查；每个字段、嵌套对象、日期格式、id 的取值范围，都得按你的数据决定查到哪一层。

`JSON.parse` 只是入口之一。`fetch` 的响应、`localStorage` 里的旧数据、URL 查询参数、第三方 SDK 的回调，都会绕过 TypeScript 的检查。**接口是编译期契约；运行时收到的数据需要解析和验证，验证之后再交给内部代码。** 这条边界画清楚，`interface` 才有意义。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：为什么加载留言的三种状态不能用 `interface MessageState` 写？

> **答案**
>
> 因为 `interface` 只能描述一个对象形状，没有「三个对象选一个」的语法。状态是互斥的联合，需要用 `type`：
>
> ```ts
> type MessageState =
>   | { status: "loading" }
>   | { status: "success"; messages: Message[] }
>   | { status: "error"; message: string };
> ```
>
> 写成 `interface` 加三个可选字段，会允许非法组合，调用方还得处理所有字段的 `undefined`。

**第 2 题**：`readonly tags: string[]` 能阻止 `tags.push("闲聊")` 吗？怎样才算运行时不可变？

> **答案**
>
> 不能。`readonly` 只禁止重新赋值 `tags = [...]`，不禁止修改数组内容，所以 `push` 通过。
>
> 想禁止内容变化，类型上写 `readonly string[]`；想真的在运行时不可变，用 `Object.freeze(tags)`，但它是浅冻结，对象里嵌套的数组或对象还要逐层处理。

**第 3 题**：下面这段为什么能过 `tsc`，运行时却可能崩？怎么改？

```ts
interface Message {
  id: number;
  author: string;
  text: string;
  createdAt: string;
}

const message = JSON.parse('{"id":"7"}') as Message;
console.log(message.createdAt.toUpperCase());
```

> **答案**
>
> `JSON.parse` 返回 `any`，`as Message` 只是让编译器相信，没有检查字段。运行时没有 `createdAt`，读出来是 `undefined`，调用 `toUpperCase` 就抛 `TypeError`。
>
> 改成 `unknown` 加运行时检查，例如用一个 `isMessage(value: unknown): value is Message` 的函数逐字段验证，通过后再访问：
>
> ```ts
> const parsed: unknown = JSON.parse('{"id":"7"}');
> if (isMessage(parsed)) {
>   console.log(parsed.createdAt.toUpperCase());
> } else {
>   console.log("数据形状不对");
> }
> ```

## 继续阅读 {#related}

- [TypeScript 的类型注解与推断](/learn/ts-types)
- [联合类型与类型收窄](/learn/ts-unions)
- [URL、JSON 与 API 契约](/learn/web-api)
- [泛型：保留输入与输出的类型关系](/learn/ts-generics)

## 参考资料 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
