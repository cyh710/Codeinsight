# 可选字段、null 与安全访问

## 留言的作者栏为什么有三种“空” {#overview}

读完这一篇，你能分清 undefined、null 和空字符串，并在接口边界把它们收成页面能直接用的确定值。

留言板允许匿名。接口返回的数据里，作者栏有时整个字段都没有，有时是 `null`，有时是空字符串 `""`。页面上看起来都是"没有名字"，但业务含义不一样：没提交、账号注销、用户提交了空值。

TypeScript 能把这三种情况留在类型里，前提是你在接口处没有把它们统统写成 `string`。

## 三种空值跑一遍 {#three-kinds}

新建 `board.ts`：

```ts
type RawMessage = {
  id: string;
  author?: string | null;
  content: string;
  editedAt?: string | null;
};

const raw: RawMessage[] = [
  { id: "m1", author: "小林", content: "周报写完了", editedAt: "2026-10-24T09:00:00Z" },
  { id: "m2", content: "路过" },
  { id: "m3", author: null, content: "账号已注销" },
  { id: "m4", author: "", content: "还没想好署名" },
  { id: "m5", author: "小周", content: "明早一起看", editedAt: null },
];

function describeAuthor(msg: RawMessage): string {
  if (msg.author === undefined) return "没给 author 字段";
  if (msg.author === null) return "明确为空（账号注销）";
  if (msg.author === "") return "给了空字符串";
  return `作者：${msg.author}`;
}

for (const msg of raw) {
  console.log(`${msg.id} ${describeAuthor(msg)}`);
}

console.log(raw[0].editedAt);
console.log(raw[1].editedAt);
console.log(raw[4].editedAt);
```

编译并运行：

```bash
npx tsc board.ts --strict --target es2022
node board.js
```

你应该看到：

```
m1 作者：小林
m2 没给 author 字段
m3 明确为空（账号注销）
m4 给了空字符串
m5 作者：小周
2026-10-24T09:00:00Z
undefined
null
```

后三行分别是：有编辑时间、字段缺失、明确为 `null`。

用一张表对照：

| 值 | 类型上表示 | 典型来源 |
|---|---|---|
| `undefined` | 字段缺失，或变量没赋值 | JSON 里根本没有这个键 |
| `null` | 明确为空 | 后端显式返回 `null`，例如账号已注销 |
| `""` | 有值，值是空字符串 | 表单提交了空输入，或 `trim()` 之后为空 |

`undefined` 和 `null` 都会被 `?.`、`??` 接住，空字符串不会。这是后面所有判断的分界线。

JSON 里没有 `undefined` 这个值。后端不返回 `author` 这个键时，`JSON.parse` 出来的对象上就没有它，读 `msg.author` 得到 `undefined`。别把"字段没来"和"字段来了但是 null"当成同一件事，接口契约要写清楚哪一个表示什么。

`editedAt` 也一样。m2 没有这个字段，m5 明确写了 `null`。如果业务上"从没编辑过"只应该有一种表示，那就选一个并在接口文档里定死；两种都收，下游就得写两套判断。这里保留两种，是为了让你看清类型上的差别。

## 可选链、空值合并和逻辑或的分工 {#operators}

跑这一小段：

```ts
type RawMessage = {
  id: string;
  author?: string | null;
  content: string;
};

const pageSize: number | undefined = 0;
console.log(pageSize ?? 20);
console.log(pageSize || 20);

const draftAuthor = "";
console.log(JSON.stringify(draftAuthor ?? "匿名"));
console.log(JSON.stringify(draftAuthor || "匿名"));

const msg: RawMessage = { id: "m6", content: "刚写的" };
console.log(msg.author?.toUpperCase());
console.log(msg.author?.trim() || "匿名");
```

输出：

```
0
20
""
"匿名"
undefined
匿名
```

逐行看：

- `pageSize` 是 `0`。`0 ?? 20` 得到 `0`，因为 `??` 只在左边是 `null` 或 `undefined` 时替换。`0 || 20` 得到 `20`，因为 `0` 是假值。如果 `0` 在业务里表示"不分页"，`||` 会把用户的设置悄悄改掉。
- `draftAuthor` 是空字符串。`"" ?? "匿名"` 保留空字符串；`"" || "匿名"` 换成"匿名"。哪一种对，取决于空字符串代表"用户提交了空名字"还是"无效输入"。类型不会替你决定。
- `msg.author` 不存在。`msg.author?.toUpperCase()` 在 `?.` 处停下，返回 `undefined`，不抛错。它没有把作者补出来，只是没让程序崩。

`?.` 只对 `null` 和 `undefined` 短路。`""`、`0`、`false` 都会继续往下走：

```ts
const empty = "";
console.log(empty?.length);   // 0，不是 undefined
const zero: number | undefined = 0;
console.log(zero?.toFixed(0)); // "0"
```

`??` 和 `||` 的差别可以记成一张表：

| 左侧值 | `a ?? b` | `a || b` |
|---|---|---|
| `undefined` | `b` | `b` |
| `null` | `b` | `b` |
| `0` | `0` | `b` |
| `""` | `""` | `b` |
| `false` | `false` | `b` |
| `NaN` | `NaN` | `b` |

选择依据是业务含义，不是"哪个写起来短"。计数、价格、开关这类可能合法为 `0` 或 `false` 的值，用 `??`；只把空字符串也当缺失的文本，才用 `||`。

## 非空断言只是让编译器闭嘴 {#non-null-assertion}

```ts
type Message = {
  id: string;
  author?: string;
  content: string;
};

const msg: Message = { id: "m1", content: "路过" };
console.log(msg.author!.toUpperCase()); // tsc 通过，运行时 TypeError
```

`tsc --strict` 不会报错。编译并运行：

```bash
npx tsc board.ts --strict --target es2022
node board.js
```

报错的第一行是：

```
TypeError: Cannot read properties of undefined (reading 'toUpperCase')
```

`!` 只是从类型里删掉 `null` 和 `undefined`，运行时的值一点没变。`msg.author` 仍然是 `undefined`，`.toUpperCase()` 仍然会崩。

它少数合理的用法，是你刚刚做过检查、但编译器没跟上的地方：

```ts
const author = msg.author;
if (author === undefined) {
  throw new Error("这条留言没有作者");
}
console.log(author.toUpperCase());
```

这段代码不需要 `!`。把值放进局部变量再判断，编译器能跟着收窄；`!` 把这个过程跳过了，也把以后重构时的保护跳过了。

`!` 和逻辑非的 `!` 是两个东西。`!msg.author` 是取反，`msg.author!` 是断言。读代码时看清位置。

## strictNullChecks 打开前后 {#strict-mode}

同一段代码，用两个设置各跑一次：

```ts
type Message = {
  id: string;
  author?: string;
  content: string;
};

function label(msg: Message): string {
  return msg.author.toUpperCase(); // TS18048: 'msg.author' is possibly 'undefined'.
}

const fallback: string = undefined; // TS2322: Type 'undefined' is not assignable to type 'string'.
```

先关掉：

```bash
npx tsc board.ts --noEmit --strictNullChecks false
```

没有输出，编译通过。`undefined` 可以赋给 `string`，可选字段也能直接当 `string` 用。

再打开：

```bash
npx tsc board.ts --noEmit --strictNullChecks true
```

你应该看到：

```
board.ts(8,10): error TS18048: 'msg.author' is possibly 'undefined'.
board.ts(11,7): error TS2322: Type 'undefined' is not assignable to type 'string'.
```

打开之后，`author?: string` 就是 `string | undefined`。读属性前必须收窄；`undefined` 也不能再冒充 `string`。

`strict: true` 是 `strictNullChecks` 加上其它几项严格检查的总开关。新项目从第一天就打开，成本最低；老项目打开时会冒出一批错误，那些位置通常正是可能崩的地方——数据从接口进来、还没判断就开始用。

注意一个细节：`author?: string` 只说明字段可以缺席，不说明它的值可以是 `null`。接口真的会返回 `null` 时，要写 `author?: string | null`，否则 `null` 会从类型下面漏过去。

## 在接口边界把空值收成确定值 {#boundary}

真正的分界线在数据进入组件之前。接口类型可以宽松，组件内部要确定：

```ts
type RawMessage = {
  id: string;
  author?: string | null;
  content: string;
  editedAt?: string | null;
};

type Message = {
  id: string;
  author: string;
  content: string;
  editedAt: string | null;
};

function normalize(raw: RawMessage): Message {
  return {
    id: raw.id,
    content: raw.content,
    author: raw.author?.trim() || "匿名用户",
    editedAt: raw.editedAt ?? null,
  };
}

console.log(normalize({ id: "m2", content: "路过" }));
```

输出：

```
{ id: 'm2', content: '路过', author: '匿名用户', editedAt: null }
```

`normalize` 接收 `RawMessage`，交回 `Message`。转换之后，`author` 一定是字符串，`editedAt` 一定是字符串或 `null`。后面的组件不用再写 `?.` 和 `??`，也不用猜字段在不在。

`author: raw.author?.trim() || "匿名用户"` 这一段做了三次收口：

- `?.` 处理 `undefined` 和 `null`。
- `trim()` 把只有空格的作者变成空字符串。
- `||` 把空字符串换成"匿名用户"。

这里的 `||` 是有意的：业务上空白作者和空字符串都显示成匿名。换成 `??` 就会保留 `""`，页面会出现一个空的名字。

`editedAt: raw.editedAt ?? null` 是另一种选择：只把 `null` 和 `undefined` 归一成 `null`，其它值原样保留。如果后端把空字符串塞进日期字段，它会被保留下来，因为类型 `string | null` 允许任何字符串。类型不校验内容，内容要靠边界检查：

```ts
function parseEditedAt(value: string | null | undefined): string | null {
  if (value == null) return null;
  const time = Date.parse(value);
  if (Number.isNaN(time)) {
    throw new Error(`editedAt 不是合法时间：${value}`);
  }
  return value;
}
```

`value == null` 用了宽松相等，同时覆盖 `null` 和 `undefined`，这是少数适合用 `==` 的地方。`Date.parse("")` 得到 `NaN`，空字符串在这里被拒绝，而不是悄悄变成 `null`。

哪些字段该给默认值、哪些该报错，看业务：

- 可有可无的展示字段，给明确默认值，比如缺作者显示"匿名用户"。
- 必填字段缺失，应该在边界抛错或返回失败结果，不要用默认值掩盖。
- 权限、身份这类字段缺失时，不能默认成管理员或所有者；应该拒绝这次操作。
- 加载中、确实没有数据、请求失败，最好用不同的状态表示，别都渲染成空列表。

状态可以用联合类型写死：

```ts
type ViewState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "ready"; messages: Message[] };
```

调用方处理 `ViewState` 时，每个分支都清楚；比一个 `Message[]` 加几个布尔值更难写错。

## 四个会把空值藏起来的写法 {#pitfalls}

**"`?.` 一包，缺失数据就安全了。"** 它只是不崩，返回值还是 `undefined`。`msg.author?.toUpperCase()` 在作者缺失时得到 `undefined`，页面可能显示空白；如果作者是必须的，应该在边界报错，而不是一路 `?.` 到 UI。

**"`??` 和 `||` 可以互换。"** 0、空字符串、`false`、`NaN` 在 `||` 右侧都会被替换。计数和开关要用 `??`；换成 `||`，用户的 `0` 就没了。

**"加了 `!` 就真的有值。"** `!` 不产生值，只改类型。上面的 `msg.author!` 照样在运行时崩。

**"所有字段都标成可选最安全。"** 恰好相反。把必填字段标成 `?`，每个使用方都要自己猜"没有时怎么办"，接口契约也失去意义。可选只留给真的可以缺席的字段。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面两句分别输出什么？

```ts
const pageSize: number | undefined = 0;
console.log(pageSize ?? 20);
console.log(pageSize || 20);
```

> **答案**
>
> 第一句输出 `0`，第二句输出 `20`。
>
> `??` 只在左侧是 `null` 或 `undefined` 时替换，`0` 是有效值，所以保留。`||` 把 `0` 当假值，换成 20。分页大小允许为 0 时，这里必须用 `??`。

**第 2 题**：接口给出 `author?: string | null`，写一行表达式，把缺失、`null`、纯空格和空字符串都显示成"匿名用户"。

> **答案**
>
> ```ts
> const label = raw.author?.trim() || "匿名用户";
> ```
>
> `?.` 接住 `null` 和 `undefined`，`trim()` 把纯空格变成空字符串，`||` 再把空字符串换成默认文案。
>
> 只用 `??` 不够：`raw.author ?? "匿名用户"` 会保留 `""` 和 `"   "`。

**第 3 题**：为什么 `msg.author!` 不能替代空值判断？给一个会崩的输入。

> **答案**
>
> `!` 只改类型，不检查运行时的值。类型检查会被绕过，值仍然可能是 `undefined`：
>
> ```ts
> const msg: Message = { id: "m1", content: "路过" };
> console.log(msg.author!.toUpperCase());
> // tsc 通过；运行时 TypeError: Cannot read properties of undefined (reading 'toUpperCase')
> ```
>
> 应该先判断 `msg.author !== undefined`，或者让接口边界保证 `author` 一定有值。

## 继续阅读 {#related}

- [TypeScript 的类型注解与推断](/learn/ts-types)
- [联合类型与类型收窄](/learn/ts-unions)
- [泛型：保留输入与输出的类型关系](/learn/ts-generics)
- [URL、JSON 与 API 契约](/learn/web-api)

## 参考资料 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
