# TypeScript 的类型注解与推断

## 先建立直觉 {#overview}

TypeScript 在 JavaScript 基础上增加静态类型检查，帮助你在运行前发现一些接口不一致。类型注解描述值的形状，推断根据上下文自动得到类型。它不会把外部输入自动变成正确数据，也不会替你验证所有业务规则。

## 原理与执行过程 {#mechanism}

编译器分析变量、表达式与控制流，判断调用和赋值是否符合约定。类型通常会在生成 JavaScript 时被擦除，所以运行时不会自动检查接口。对外部 JSON，可以先视为 unknown，再经过检查缩小范围；直接把它断言成某类型只是告诉编译器相信你。

## 跟着例子理解 {#example}

```typescript
function total(price: number, count: number): number {
  return price * count;
}
const amount = total(12, 3); // 推断为 number
// total('12', 3) 会被类型检查器指出不匹配。
```

## 一步一步读懂 {#walkthrough}

函数签名要求两个数字并返回数字。amount 不必重复写注解，编译器能从返回类型推断。若后端把 price 返回成字符串，JavaScript 运行时仍可能发生转换；需要在网络边界明确检查或解析。通过类型检查只能证明静态约定的一部分，不能证明金额、权限和库存规则正确。

## 常见误解 {#pitfalls}

any 会绕过大量检查，unknown 要求先确定值的形状。as 不是转换函数。把错误压成 any 能暂时让构建通过，却把风险转移到用户操作时。类型检查器的配置会影响检查力度，应与项目实际配置一起阅读。

## 工程中的取舍 {#tradeoffs}

公开接口值得明确注解，局部简单变量可以依赖推断。过多复杂类型会增加阅读成本，过少约束则错过静态检查价值。优先让类型表达业务不变量，再用测试验证计算、状态和外部交互。

## 接着探索 {#related}

- [JavaScript 的变量与值](/learn/js-values)
- [联合类型与类型收窄](/learn/ts-unions)
- [类型注解：把接口约定写出来](/learn/python-annotations)

## 来源与版本 {#sources}

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
