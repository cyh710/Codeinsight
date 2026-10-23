# URL、JSON 与 API 契约

## 先建立直觉 {#overview}

URL 标识访问目标，JSON 表达可以传输的数据结构，API 约定双方怎样交互。它们不是同一件事：知道一个地址不代表知道请求字段；拿到一段 JSON 也不代表它符合接口需要的形状。工程协作依赖的是完整契约。

## 原理与执行过程 {#mechanism}

URL 包含协议、主机、路径、查询和片段等部分；片段通常用于客户端定位，不会作为普通 HTTP 请求路径发送。JSON 支持对象、数组、字符串、数字、布尔和 null，不支持函数与循环引用。字段名称、是否可空、版本和错误形状都应在契约里明确。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```javascript
const topicId = 'sql-select';
const address = `/api/knowledge/topics/${encodeURIComponent(topicId)}`;
const response = await fetch(address);
if (!response.ok) throw new Error('章节读取失败');
const topic = await response.json();
console.log(topic.title);
```

## 一步一步读懂 {#walkthrough}

先对路径参数编码，避免特殊字符改变地址结构。fetch 取得响应后检查状态。json() 只负责解析文本，不验证 topic.title 真的是字符串。真实应用需要在可信边界校验数据，并在契约变更时同步调用方。浏览器里的 /learn/topic#example 可以是站内阅读目标，不必等于后端数据接口地址。

## 常见误解 {#pitfalls}

JSON 不是 JavaScript 任意表达式，不能用 eval 解析。数字在不同语言中可能有不同精度边界。查询参数与路径参数混用会让调用难以追踪。不要让模型编造一个看起来像链接的地址就直接执行动作，应先解析成系统认识的目标。

## 工程中的取舍 {#tradeoffs}

统一 snake_case 或 camelCase 比两端反复映射更简单。新增可选字段通常比删改已有字段容易兼容，但仍要更新类型和文档。知识来源引用与代码行号引用应保持不同结构，避免把教材中的示例误当作项目文件。

## 接着探索 {#related}

- [HTTP 请求与响应](/learn/web-http)
- [interface、type 与结构契约](/learn/ts-interfaces)
- [结构化日志：记录可以关联的事件](/learn/structured-logging)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
