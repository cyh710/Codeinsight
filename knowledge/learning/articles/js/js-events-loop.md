# 事件循环、任务与微任务

## 先猜这段代码的输出顺序 {#overview}

学完这一篇，你能拿到一段混着 setTimeout 和 Promise 的代码，逐行说出真实输出顺序，并解释页面为什么会卡住。

下面这段只有十几行，但它的输出顺序和阅读顺序不一样。先别运行，拿张纸写下你猜的顺序：

```js
console.log('A 脚本开始');

setTimeout(() => console.log('B 定时器'), 0);

Promise.resolve().then(() => console.log('C then'));

queueMicrotask(() => console.log('D queueMicrotask'));

async function greet() {
  console.log('E async 函数体');
  await null;
  console.log('F await 之后');
}

greet();
console.log('G 脚本结束');
```

存成 `order.js` 跑 `node order.js`，或者整段贴进浏览器控制台。写完了再往下看。

## 逐行对答案 {#line-by-line}

真实输出是：

```
A 脚本开始
E async 函数体
G 脚本结束
C then
D queueMicrotask
F await 之后
B 定时器
```

代码里逐行标一遍：

```js
console.log('A 脚本开始');                            // 第 1 个输出
setTimeout(() => console.log('B 定时器'), 0);          // 回调第 7 个输出
Promise.resolve().then(() => console.log('C then'));   // 第 4 个输出
queueMicrotask(() => console.log('D queueMicrotask')); // 第 5 个输出

async function greet() {
  console.log('E async 函数体');                       // 第 2 个输出
  await null;                                         // 函数在此暂停
  console.log('F await 之后');                         // 第 6 个输出
}

greet();
console.log('G 脚本结束');                            // 第 3 个输出
```

为什么会这样：

1. 脚本整体是一个任务，从第一行往下执行。`A` 直接打印。
2. `setTimeout` 把回调交给计时器，0ms 到期后放进任务队列；此刻只是登记，没有执行。
3. `Promise.resolve().then` 登记一个微任务 `C`，`queueMicrotask` 登记一个微任务 `D`。顺序是 C、D。
4. 调用 `greet()`，函数体同步执行，打印 `E`。遇到 `await null`，后面的代码被登记成微任务，排在 C、D 之后，函数暂停并返回。
5. 回到调用处，打印 `G`。脚本这个任务结束，调用栈清空。
6. 清空微任务队列，依次打印 `C`、`D`、`F`。
7. 微任务清空后，才轮到任务队列里的定时器回调，打印 `B`。

`await` 后面的 `F` 排在一开始就登记的 `C`、`D` 之后，因为微任务按登记顺序执行。`B` 排在末尾，因为它进的是任务队列，不是微任务队列。

这段只用了 `setTimeout`、Promise、`queueMicrotask` 和 `await`，浏览器和 Node 的顺序一致。更细的调度规则各宿主有差异，别把某一个环境的顺序当成语言保证。

## 调用栈、任务队列与微任务队列 {#queues}

JavaScript 在主线程上只有**一个调用栈**。函数调用时压栈，返回时出栈。同步代码的执行，就是栈不断进出。

栈空了，不代表没事可做。还有两个队列在等：

| 队列 | 放什么 | 典型来源 |
|---|---|---|
| 任务队列 | 宏任务，一次取一个 | `setTimeout`、`setInterval` 回调、DOM 事件、网络完成 |
| 微任务队列 | 微任务，一轮清空 | `Promise.then/catch/finally`、`queueMicrotask`、`await` 后面的代码 |

事件循环反复做四件事：

1. 从任务队列取出一个任务，执行到调用栈清空。
2. 清空微任务队列。清空过程中新加入的微任务也要做完。
3. 浏览器有机会更新样式、布局并绘制。
4. 回到第 1 步。

**微任务一定在当前任务的末尾清空，宏任务要等下一轮。** 这条线决定了回调是插队，还是排到下一个任务后面。

拿例子对照：脚本是一个宏任务，C、D、F 是微任务，所以它们全在脚本结束之后、定时器之前跑完。定时器回调是下一个宏任务，得等微任务队列彻底空了才轮到。

“微任务队列清空过程中新加入的也要做完”有代价。如果微任务里不断再登记微任务，队列永远清不空，浏览器就没有机会进入第 3 步。页面看起来完全冻住，但其实代码在一刻不停地跑。

渲染不是每个任务后都必然发生。浏览器会合并、跳过，或者在需要时提前绘制。你能确定的是：同步代码和微任务没跑完，渲染没有机会开始。

## setTimeout(fn, 0) 为什么落在末尾 {#zero-timeout}

`setTimeout(fn, 0)` 的意思是“尽快安排”，不是“立刻执行”。计时器到期后，回调被放进任务队列，必须等当前任务结束、微任务清空，才可能被取出来。

在这个例子里它落在末尾，因为前面有一个正在执行的脚本任务和三个微任务。准确说法是：它排在当前任务和所有微任务之后。如果这时任务队列里已经有别的任务在等，它和那些任务的先后并不由这个 0 决定。

浏览器还会对定时器做钳制。嵌套层级很深的定时器会有最小间隔；后台标签页会被明显节流；系统繁忙时，实际执行时间只会更晚。`setTimeout(fn, 0)` 从来不是精确的 0ms 承诺，动画用它会对不齐帧，计时用它会有累积误差。

```js
const id = setTimeout(() => console.log('不会执行'), 1000);
clearTimeout(id);   // 在到期前取消
```

定时器回调执行时，它所在的宏任务同样遵循“先跑完、再清微任务”的规则。在回调里写 `Promise.resolve().then(...)`，那段微任务会在当前回调结束后立刻跑，不用再等一轮。

## 一段同步代码怎样冻住整页 {#blocking}

主线程同时负责执行 JavaScript、处理事件和渲染。一段同步代码不结束，这三件事都做不了。

新建一个页面，点按钮跑三秒：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>卡三秒</title>
</head>
<body>
  <button id="work">跑三秒</button>
  <p id="status">还没开始</p>

  <script>
    const status = document.querySelector('#status');

    document.querySelector('#work').addEventListener('click', () => {
      setTimeout(() => console.log('定时器终于跑了'), 0);

      const start = Date.now();
      while (Date.now() - start < 3000) {}   // 同步占住主线程

      console.log('同步代码跑完了', Date.now() - start, 'ms');
      status.textContent = '跑完了';
    });
  </script>
</body>
</html>
```

点一次按钮，控制台顺序是：

```
同步代码跑完了 3000 ms
定时器终于跑了
```

毫秒数每次略有不同，顺序不变。定时器在点击处理的**第一行**就安排了，可它只能等这个任务结束。三秒里页面不响应点击、不更新文字、不重绘——浏览器连“跑完了”这三个字都画不出来。

这也解释了为什么“代码已经执行”和“用户已经看到”不是同一时刻。`status.textContent` 赋值那一刻，DOM 已经改了，但屏幕要等浏览器获得渲染机会才更新。

把这段计算换成真实工作，比如解析一个很大的 JSON、给几万条数据排序、在循环里反复操作 DOM，效果一样。计算量多大不是关键，关键是它**一直占着调用栈**，中间没有让出的机会。

## 微任务插队，渲染不等人 {#pitfalls}

**“Promise 回调会让页面喘口气。”** 不会。微任务在当前任务结束后立刻全部执行，浏览器要等它们清空才能渲染。用递归微任务做分片，页面反而更卡：

```js
function spin() {
  Promise.resolve().then(spin);   // 一直往微任务队列里加活
}
spin();                           // 不要运行：页面会失去响应
```

这段会不断给自己续命，事件循环永远走不到渲染那一步。分片要让出到**下一个宏任务**，比如 `setTimeout(fn, 0)`，而不是微任务。

**“包进 Promise 就在后台线程跑了。”** Promise 的执行器和 `.then` 回调都在主线程。它解决的是等待期间能不能干别的，不是把计算搬走。真正要并行计算，得用 Web Worker。

**“`setTimeout` 写 0 就是马上执行。”** 它要排队，还要被钳制。想尽快让出，可以用 `setTimeout(fn, 0)`；想等浏览器空闲，可以考虑 `requestIdleCallback`（支持范围有限）；想跟着重绘节奏，用 `requestAnimationFrame`。

**“`async` 函数开了一个新线程。”** 没有。`await` 只是暂停这个函数，把后续代码登记成微任务，线程还是那一个。

## 长任务怎么切小 {#long-tasks}

一段计算要跑很久，又必须留在主线程，就把它切成小片，每片之间让出一次：

```js
async function processInChunks(items) {
  for (let i = 0; i < items.length; i += 100) {
    const chunk = items.slice(i, i + 100);
    chunk.forEach(handle);       // 每片只占一小段时间

    // 让出到下一个宏任务，浏览器才有机会渲染和处理输入
    await new Promise(resolve => setTimeout(resolve, 0));
  }
}
```

把 `handle` 换成你要执行的处理函数。每片多大，不能拍脑袋。用 `performance.now()` 或 DevTools 的 Performance 面板量：一片最好短到用户察觉不到卡顿，又别小到让出次数过多、总时间被调度开销吃掉。

计算特别重、又不碰 DOM 时，Web Worker 更合适。它在另一个线程跑，主线程继续响应。代价是数据要跨线程传递，结构化克隆有成本；Worker 里也拿不到 `document`，结果得发回主线程再渲染。为了一次排序就开 Worker，往往不划算。

判断顺序是：能不能少算（缓存、减少重复渲染）→ 能不能切片让出 → 再考虑 Worker。事件循环的知识用在这里：你要知道哪一步占住了调用栈，才知道该在哪里让出。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面代码的输出顺序是什么？

```js
console.log('1');
setTimeout(() => console.log('2'), 0);
Promise.resolve().then(() => console.log('3'));
console.log('4');
```

> **答案**
>
> ```
> 1
> 4
> 3
> 2
> ```
>
> 同步代码先打印 `1`、`4`；脚本任务结束后清空微任务，打印 `3`；定时器回调是下一个宏任务，打印 `2`。

**第 2 题**：为什么 `greet()` 里的 `E` 在 `G` 之前，而 `F` 在 `G` 之后？

> **答案**
>
> `greet()` 被调用后，函数体同步执行到第一个 `await`，所以 `E` 当场打印，早于调用方下一行的 `G`。
>
> `await null` 把后面的代码登记成微任务。函数先返回，调用方打印 `G`；等当前任务结束、清空微任务时，才轮到 `F`。

**第 3 题**：一个点击处理函数里有五秒的同步循环。用户在这五秒里又点了一个按钮，第二次点击会丢吗？什么时候处理？

> **答案**
>
> 一般不会丢。浏览器会等当前任务结束再派发点击，期间的点按可能被延迟，也可能被合并，但通常不会直接消失。
>
> 要等第一个处理函数返回、微任务清空后，第二次点击的监听器才会执行。这五秒里页面不重绘、输入无响应，用户看到的就是“卡死”。

## 继续阅读 {#related}

- [Promise 与 async/await](/learn/js-async)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [State、重新渲染与状态快照](/learn/react-state)
- [线程池：受控执行阻塞工作](/learn/thread-pool)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
