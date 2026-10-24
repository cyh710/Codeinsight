# 联合类型与类型收窄

## 先建立直觉 {#overview}

联合类型表示一个值可能属于几种情况，收窄通过实际检查确定当前是哪一种。它特别适合表达加载、成功和失败等互斥状态，让界面在访问结果前先处理状态，而不是假设所有字段总是存在。

## 原理与执行过程 {#mechanism}

编译器根据 typeof、属性存在性和判别字段等条件分析分支。共同的字面量字段能把复杂状态分成清楚的结构。一个布尔 loading 加上多个可选字段允许许多矛盾组合；判别联合可以减少这种无效状态。

## 跟着例子理解 {#example}

```typescript
type Result = { kind: 'ok'; value: string } | { kind: 'error'; message: string };
function show(result: Result) {
  if (result.kind === 'ok') return result.value;
  return result.message;
}
```

## 一步一步读懂 {#walkthrough}

Result 只有两种形状。检查 kind 后，成功分支允许访问 value，失败分支允许访问 message。若把两个字段都写成可选字符串，则可能出现既没值也没错误的对象。用类型表达互斥关系，可以在读代码时直接看到状态机的边界。

## 常见误解 {#pitfalls}

非空断言 ! 不会在运行时补数据。判断一个字段为真可能同时排除空字符串、0 等合法值，需按业务使用显式条件。新增状态后，应检查所有处理分支，避免旧代码默默落入不合适的默认分支。

## 工程中的取舍 {#tradeoffs}

判别联合会让类型定义更长，但减少调用方猜测。它适合 API 结果、异步状态与工具执行结果；对于简单的可选名字，可能只需要 string|null。类型设计应减少无效状态，而不是追求技巧复杂。

## 接着探索 {#related}

- [TypeScript 的类型注解与推断](/learn/ts-types)
- [可选字段、null 与安全访问](/learn/ts-nullability)
- [State、重新渲染与状态快照](/learn/react-state)

## 来源与版本 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
