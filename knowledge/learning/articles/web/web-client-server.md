# 浏览器、前端与后端

## 先建立直觉 {#overview}

浏览器运行用户看到的页面，前端代码负责界面与交互；后端通常运行在另一进程，处理数据、权限和持久化。一个按钮可以在浏览器里立即改变颜色，也可以发请求让后端保存消息。界面有变化，不代表后端操作已经成功。

## 原理与执行过程 {#mechanism}

一次常见交互分为用户操作、前端事件处理、HTTP 请求、后端业务处理和响应渲染。浏览器与服务器各自有内存，前端修改对象不会自动修改数据库。后端也可能调用第三方服务。阅读项目需要跨越这些边界追踪同一份数据，而不能只找按钮文本或一个同名函数。

## 跟着例子理解 {#example}

```javascript
const response = await fetch('/api/messages');
if (!response.ok) throw new Error('读取消息失败');
const messages = await response.json();
console.log(messages);
```

## 一步一步读懂 {#walkthrough}

fetch 发起网络请求并返回 Promise。await 等待响应对象，不会直接得到消息数组。检查 HTTP 状态后，json() 再解析响应正文。后端返回什么字段，前端才能可靠读取什么字段。开发服务器可能通过代理把 /api 前缀转发给真正的后端，因此浏览器地址与后端路由不一定完全相同。

## 常见误解 {#pitfalls}

前端隐藏一个按钮不能代替后端权限检查。localhost 表示当前运行环境的本机，容器内和浏览器中的本机可能不是同一个地方。CORS 是浏览器跨源读取规则，不是完整身份认证。页面显示“已保存”应依据明确的成功结果，而不只是按钮已被点击。

## 工程中的取舍 {#tradeoffs}

前端能做即时反馈和格式检查，后端负责可信校验及共享状态。乐观更新改善响应速度，但失败时要能恢复。理解故障时可以沿边界检查请求是否发出、状态码、响应内容和界面状态，避免把所有问题都归因于模型或网络。

## 接着探索 {#related}

- [HTTP 请求与响应](/learn/web-http)
- [URL、JSON 与 API 契约](/learn/web-api)
- [网络请求、取消与失败处理](/learn/js-fetch)

## 来源与版本 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
