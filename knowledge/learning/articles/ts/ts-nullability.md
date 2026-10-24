# 可选字段、null 与安全访问

## 先建立直觉 {#overview}

空值表达“没有数据”，但缺失字段、明确为 null 和空字符串可能代表不同业务状态。类型系统能提醒你处理这些情况，前提是接口没有把它们不准确地标成必有值。

## 原理与执行过程 {#mechanism}

strictNullChecks 会让 null 与 undefined 参与类型检查。可选链 ?. 在目标为空时停止属性访问，空值合并 ?? 只对 null/undefined 提供默认值。逻辑或 || 则会把 0、false、空字符串等假值也替换掉。选择哪一个必须依据业务含义。

## 跟着例子理解 {#example}

```typescript
const pageSize: number | undefined = 0;
console.log(pageSize ?? 20); // 0
console.log(pageSize || 20); // 20
const user: { profile?: { name: string } } = {};
console.log(user.profile?.name ?? '匿名');
```

## 一步一步读懂 {#walkthrough}

pageSize 为 0 时，?? 保留它，因为它不是缺失值。|| 会采用 20。是否允许 0 表示“不分页”由接口约定决定。可选链让 profile 不存在时不抛属性访问错误，却不能判断匿名名字是否适合当前操作。缺失权限不能简单用默认管理员角色填补。

## 常见误解 {#pitfalls}

可选链不是输入校验，更不能用来静默吞掉本应存在的数据。! 只是跳过检查，不会让值真的存在。把所有字段都写成可选会减弱契约，造成大量“猜空值”的代码。

## 工程中的取舍 {#tradeoffs}

为真正允许缺失的字段提供明确默认值；必需字段应在边界拒绝或报错。缺失、加载中与未找到最好分开表达，避免用户看到一个空白界面却不知道发生了什么。

## 接着探索 {#related}

- [TypeScript 的类型注解与推断](/learn/ts-types)
- [联合类型与类型收窄](/learn/ts-unions)
- [URL、JSON 与 API 契约](/learn/web-api)

## 来源与版本 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
