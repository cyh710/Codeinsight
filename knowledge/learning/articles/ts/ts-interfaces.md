# interface、type 与结构契约

## 先建立直觉 {#overview}

interface 和 type 都能描述数据形状。它们帮助前后端与组件约定字段，不代表运行时已经建立了一个有校验能力的对象。TypeScript 很多地方按结构判断兼容性：只要具备要求的成员，就可能符合接口。

## 原理与执行过程 {#mechanism}

interface 常用于描述对象契约并支持声明合并，type 可以为联合、交叉和其他类型表达式命名。readonly 描述静态写入约束，不会自动深度冻结对象。可选字段、字段为 null 和字段缺失在业务上可能有不同意义。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```typescript
interface Topic {
  id: string;
  title: string;
  summary?: string;
}
type TopicResult = { items: Topic[]; total: number };
```

## 一步一步读懂 {#walkthrough}

Topic 要求 id 与 title 为字符串，summary 可以缺失。TopicResult 明确列表响应不是裸数组，而是带总数的对象。若服务端返回 topics 而前端读取 items，类型文件本身无法改变网络数据，必须同步契约并在边界核验。

## 常见误解 {#pitfalls}

不要在多个文件手工维护同一接口的不同版本。readonly 不会阻止另一个未受约束的引用修改同一对象。接口名字相同不代表结构与语义相同；尤其要确认时间单位、ID 类型和空值含义。

## 工程中的取舍 {#tradeoffs}

共享类型减少重复，但领域模型和 HTTP 投影有时应分开，避免内部字段泄漏。新增兼容字段比改名容易，仍应同时更新文档、实现与调用方。清楚的错误类型也是契约的一部分。

## 接着探索 {#related}

- [TypeScript 的类型注解与推断](/learn/ts-types)
- [URL、JSON 与 API 契约](/learn/web-api)
- [泛型：保留输入与输出的类型关系](/learn/ts-generics)
- [为 React props 与事件声明类型](/learn/ts-react)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)；作者：Microsoft Corporation and contributors；CC-BY-4.0。版本：Handbook；导入日网页快照; sha256:9ac056d32d3ff58bb0a62c73c0495899ca985c26ca1e49690fe560b861f7aa68。
