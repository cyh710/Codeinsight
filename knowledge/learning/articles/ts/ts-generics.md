# 泛型：保留输入与输出的类型关系

## 先建立直觉 {#overview}

泛型让一段代码适用于不同类型，同时保留它们之间的关系。例如，从数组取第一项时，返回类型应该跟数组元素类型一致。用 any 虽然也能接受不同输入，却会丢失这层关系。

## 原理与执行过程 {#mechanism}

类型参数像类型层面的占位符，由调用处推断或显式提供。约束可以表达某个类型必须具备哪些能力，但不应要求与实际操作无关的属性。泛型本身通常在编译后消失，不会创建运行时类型对象。

## 跟着例子理解 {#example}

```typescript
function first<T>(items: T[]): T | undefined {
  return items[0];
}
const name = first(['小林', '小周']);
const id = first([1, 2]);
```

## 一步一步读懂 {#walkthrough}

第一次调用推断 T 为 string，第二次为 number。因为数组可以为空，函数明确返回 T|undefined。若为了让使用者少写检查而去掉 undefined，类型就掩盖了真实边界。真正的复用既保留成功结果类型，也保留失败或空结果可能性。

## 常见误解 {#pitfalls}

类型参数不是运行时值，不能直接用 T 创建对象或判断 typeof。过多泛型可能让本来简单的数据流难以理解。一个类型参数如果没有连接多个位置，通常应重新考虑是否需要它。

## 工程中的取舍 {#tradeoffs}

通用容器、请求结果与仓库接口适合泛型；具体业务约束往往用明确类型更清楚。先实现清楚的一种情况，再抽取真实共性，比预先构造万能接口更稳妥。

## 接着探索 {#related}

- [interface、type 与结构契约](/learn/ts-interfaces)
- [可选字段、null 与安全访问](/learn/ts-nullability)

## 来源与版本 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
