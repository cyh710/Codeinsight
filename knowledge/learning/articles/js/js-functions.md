# JavaScript 函数、作用域与闭包

## 先建立直觉 {#overview}

函数把行为组织起来，作用域决定名字从哪里取得，闭包让函数保留对创建时词法环境的访问。前端回调经常在稍后执行，所以理解它捕获了什么，比只看函数现在写在哪里更重要。

## 原理与执行过程 {#mechanism}

函数可以作为值传入、返回或保存。词法作用域按定义位置决定，不按调用位置临时选择。闭包访问的是相关绑定；在 React 等场景中，每次渲染又可能创建新的绑定与函数。箭头函数没有自己的 this，与普通函数的调用语义不同。

## 跟着例子理解 {#example}

```javascript
function makeCounter() {
  let count = 0;
  return () => {
    count += 1;
    return count;
  };
}
const next = makeCounter();
console.log(next(), next()); // 1 2
```

## 一步一步读懂 {#walkthrough}

调用 makeCounter 建立局部 count，并返回内部函数。外层调用结束后，内部函数仍能访问该环境。第一次 next 把 count 改成 1，第二次改成 2。重新调用 makeCounter 会得到另一份环境，不会自动共享同一个计数器。可以用这一点理解事件回调保存状态的方式。

## 常见误解 {#pitfalls}

闭包不等于所有数据都固定不变；要看捕获的是哪一份绑定。普通函数作为对象方法调用与被单独拿出来调用，this 可能不同。异步回调里出现旧值时，应检查创建回调的时机和依赖，而不是盲目增加延迟。

## 工程中的取舍 {#tradeoffs}

闭包可以封装私有状态，也可能让大量对象被长期引用。复杂业务状态通常需要明确的生命周期与清理。函数作为依赖传入有利于测试，但过多匿名嵌套会使调用关系难读，可以适当命名并分离职责。

## 接着探索 {#related}

- [JavaScript 的变量与值](/learn/js-values)
- [函数、参数与返回值](/learn/python-functions)
- [Effect、依赖与清理](/learn/react-effects)
- [事件循环、任务与微任务](/learn/js-events-loop)

## 来源与版本 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
