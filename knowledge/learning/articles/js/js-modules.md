# JavaScript 模块与 import/export

## 先建立直觉 {#overview}

模块让文件明确声明自己提供什么、依赖什么。export 导出能力，import 在另一个文件中使用。它帮助拆分工程，也让构建工具分析依赖；但模块边界不等于运行进程边界，导入代码仍可能在当前环境执行。

## 原理与执行过程 {#mechanism}

命名导出按名字匹配，默认导出按 default 取得。静态 import 通常放在模块顶层，动态 import 返回 Promise，可用于按需加载。浏览器模块、Node.js 模块与构建工具解析路径的规则有差异；ESM 和 CommonJS 也不是完全可互换的语法。

## 跟着例子理解 {#example}

```javascript
// prices.js
export function total(price, count) { return price * count; }

// app.js
import { total } from './prices.js';
console.log(total(12, 3));
```

## 一步一步读懂 {#walkthrough}

prices 显式导出 total。app 按同名导入并调用它。相对路径从导入文件的位置理解，而不是从任意启动目录理解。若编辑器能找到某个别名，构建工具却没有相同映射，开发时仍可能看似正常、实际构建失败。应同时看配置与真实产物。

## 常见误解 {#pitfalls}

默认导出和命名导出的花括号不能随意互换。循环依赖可能读取尚未初始化的绑定。导入一个模块不等于只执行其中被调用的函数，顶层副作用仍需关注。浏览器无法直接执行的语法可能依赖构建步骤转换。

## 工程中的取舍 {#tradeoffs}

稳定的小接口有利于复用和测试。动态导入可减少首屏加载，但要显示加载和失败状态。过度集中到一个总导出文件可能引入循环和不必要依赖，分组应服务于明确边界。

## 接着探索 {#related}

- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [模块、包与导入](/learn/python-modules)
- [React 组件与 JSX](/learn/react-components)

## 来源与版本 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
