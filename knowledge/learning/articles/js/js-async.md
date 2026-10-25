# Promise 与 async/await

## 为什么三层回调会越写越深 {#overview}

学完这一篇，你能把三层嵌套的回调改成一段 async 函数，并分清什么时候该并发、什么时候必须排队。

留言板要显示一句话：小林最新一条留言有几条回复。这三样东西存在三个接口后面——先按 id 查用户，拿到用户名再查他的最新留言，拿到留言 id 再查回复数。每一步都得等网络。

用回调写，代码会一层套一层；用 Promise 写，嵌套变成链；用 async/await 写，看起来又像顺序代码了。三种写法干的是同一件事，输出也完全一样。

## 同一个任务的三层嵌套版本 {#callback-hell}

新建 `callback.js`：

```js
// 三个“接口”，各用 10ms 定时器模拟网络
function getUser(id, callback) {
  setTimeout(() => callback(null, { id, name: '小林' }), 10);
}

function getLastMessage(user, callback) {
  setTimeout(() => callback(null, { by: user.name, text: '晚上一起吃饭吗' }), 10);
}

function getReplies(message, callback) {
  setTimeout(() => callback(null, 3), 10);
}

getUser(7, (err, user) => {
  if (err) return console.error(err);

  getLastMessage(user, (err, message) => {
    if (err) return console.error(err);

    getReplies(message, (err, count) => {
      if (err) return console.error(err);
      console.log(`${user.name} 的最新留言「${message.text}」有 ${count} 条回复`);
    });
  });
});
```

```bash
node callback.js
```

你应该看到：

```
小林 的最新留言「晚上一起吃饭吗」有 3 条回复
```

这段能跑，问题在形状：

- 每层都要重复 `if (err)`，错误处理散在三处。
- 后一步要用前一步的结果，只能靠闭包往里传。想加第四步，就再缩进一层。
- 三个错误没有一个统一的出口，想在最外层集中处理做不到。
- 调用顺序写在缩进里，读代码时得一层层数括号。

回调本身没错，错的是用回调表达“下一步依赖上一步”这种链式关系。嵌套是症状，不是病因。

## 用 Promise 把嵌套摊平 {#promise-chain}

Promise 把“未来会有的结果”变成一个值。`getUser(7)` 立刻返回一个 Promise 对象，结果到了之后，挂在 `.then` 里的函数才执行。

新建 `promise.js`：

```js
function getUser(id) {
  return new Promise((resolve) => {
    setTimeout(() => resolve({ id, name: '小林' }), 10);
  });
}

function getLastMessage(user) {
  return new Promise((resolve) => {
    setTimeout(() => resolve({ by: user.name, text: '晚上一起吃饭吗' }), 10);
  });
}

function getReplies(message) {
  return new Promise((resolve) => {
    setTimeout(() => resolve({ ...message, count: 3 }), 10);
  });
}

getUser(7)
  .then(user => getLastMessage(user))
  .then(message => getReplies(message))
  .then(full => {
    console.log(`${full.by} 的最新留言「${full.text}」有 ${full.count} 条回复`);
  })
  .catch(err => console.error('读取失败：', err.message));
```

```bash
node promise.js
```

输出和上一节一字不差：

```
小林 的最新留言「晚上一起吃饭吗」有 3 条回复
```

`resolve(value)` 把 Promise 标记为成功并交出 `value`，`reject(err)` 标记为失败。`new Promise` 里那个函数叫执行器，`new` 的时候立刻同步执行；`setTimeout` 只是安排 10ms 后再调用 `resolve`。

关键在于 **`.then` 返回的是一个新的 Promise**，不是原来那个。链能接起来，靠的就是这个：

```js
Promise.resolve(1)
  .then(v => {
    console.log('第一个 then', v);   // 第一个 then 1
    return v + 1;
  })
  .then(v => {
    console.log('第二个 then 拿到', v); // 第二个 then 拿到 2
  });
```

```
第一个 then 1
第二个 then 拿到 2
```

第一个 `.then` 的回调返回 `2`，新 Promise 就以 `2` 兑现，第二个 `.then` 才收到 `2`。

如果回调返回的**又是一个 Promise**，新 Promise 不会把它当成普通值，而是等它落定，直接采用它的结果。这叫展平。上面的 `user => getLastMessage(user)` 返回 Promise，所以下一个 `.then` 拿到的不是 Promise 对象，而是留言对象。这就是链式调用能一路往下写的原因。

`.catch` 接住链上任何一环的失败，包括 `.then` 回调里抛出的异常。放在链尾，等于给整条链一个统一出口。

## 用 async/await 写成顺序代码 {#async-await}

`promise.js` 里的三个函数不用改。新建 `async.js`，把三个函数原样抄过去，末尾换成：

```js
async function showLastMessage() {
  const user = await getUser(7);
  const message = await getLastMessage(user);
  const full = await getReplies(message);
  console.log(`${full.by} 的最新留言「${full.text}」有 ${full.count} 条回复`);
}

showLastMessage().catch(err => console.error('读取失败：', err.message));
```

```bash
node async.js
```

还是同一行输出：

```
小林 的最新留言「晚上一起吃饭吗」有 3 条回复
```

`await` 的意思是：等右边这个 Promise 落定，成功就把结果交出来，失败就把异常抛在当前位置。所以 `const user = await getUser(7)` 读起来像同步赋值，实际中间让出了等待时间。

`async` 加在函数前面有两个作用：函数里才能用 `await`；函数返回的**一定是一个 Promise**，哪怕你写 `return 42`，调用方拿到的是兑现为 42 的 Promise。

```js
async function answer() {
  return 42;
}

console.log(answer() instanceof Promise);   // true
answer().then(v => console.log(v));         // 42
```

```
true
42
```

`await` 只能写在 async 函数里。例外是 ES 模块的顶层，以及浏览器控制台——它们允许顶层 `await`。普通 `<script>` 和 CommonJS 文件里直接写会报语法错误。

错误处理有两条等价的路：链式用 `.catch`，顺序写法用 `try/catch`：

```js
async function withTryCatch() {
  try {
    const user = await getUser(7);
    return user.name;
  } catch (err) {
    return '无名氏';
  }
}

withTryCatch()
  .then(name => console.log(name))          // 小林
  .catch(err => console.log(err.message));
```

`catch` 能接住，是因为 `await` 把拒绝变成了当前位置的抛出。漏写 `await`，`try` 里拿到的是一个悬空的 Promise，异常不会进这个 `catch`，而是变成未处理的 Promise 拒绝。

## Promise 的三种状态与返回值 {#promise-states}

一个 Promise 只有三种状态：

| 状态 | 含义 | 怎么到达 |
|---|---|---|
| pending | 还没有结果 | `new Promise` 之后的初始状态 |
| fulfilled | 成功，带一个值 | 调用了 `resolve(value)` |
| rejected | 失败，带一个原因 | 调用了 `reject(err)`，或执行器里抛错 |

状态只能从 pending 变成其中一种，变了就定死，不会再改。之后再调 `resolve` 或 `reject` 都没用。

```js
const p = new Promise((resolve) => {
  setTimeout(() => resolve('好了'), 100);
});

console.log(p);                        // Promise { <pending> }
p.then(value => console.log(value));   // 100ms 后打印：好了
```

```
Promise { <pending> }
好了
```

浏览器控制台会把 Promise 显示成可展开的对象，格式和这里略有差别，但状态都写着 pending。Promise 本身不能被同步读取——你不能写 `p.value` 拿到结果，只能挂回调。

`.then(onFulfilled, onRejected)` 的两个参数都可以省略。`.catch(fn)` 等价于 `.then(undefined, fn)`。`.finally(fn)` 不管成功失败都执行，且不改变结果，适合关 loading。

链上任何一环抛出异常，都会把新 Promise 变成 rejected，跳过后面所有的成功回调，直到遇到 `.catch` 或 `.then` 的第二个参数。`.catch` 处理完如果正常返回，链又会回到成功状态——所以“捕获后继续往下走”是可以做到的。

## 并发用 Promise.all，串行用 for-await {#parallel-serial}

两个请求互不依赖时，不要一个等完再发下一个。下面这段可以直接跑：

```js
function wait(ms, value) {
  return new Promise(resolve => setTimeout(() => resolve(value), ms));
}

async function serial() {
  console.time('串行');
  const a = await wait(300, 'A');
  const b = await wait(300, 'B');
  console.timeEnd('串行');
  return [a, b];
}

async function concurrent() {
  console.time('并发');
  const [a, b] = await Promise.all([wait(300, 'A'), wait(300, 'B')]);
  console.timeEnd('并发');
  return [a, b];
}

serial().then(concurrent);
```

输出大致是这样（毫秒数每次不同，看差值）：

```
串行: 621.3ms
并发: 310.1ms
```

串行版本里，第二个 `wait` 要等第一个 `await` 回来才开始计时，总耗时约 600ms。并发版本里两个 `wait` 在数组构造时就同时启动了，`Promise.all` 只是等它们都完成，总耗时约 300ms。

`Promise.all` 返回的新 Promise 在所有输入都成功时成功，结果是按输入顺序排好的数组；任何一个失败，整体立刻 rejected。失败时**其他请求不会被取消**，它们还在跑，只是结果没人要了。需要每个结果无论成败都收下，就用 `Promise.allSettled`。

有依赖就必须串行。后一步的参数来自前一步，提前发没有意义。普通数组逐条处理，就在循环里 `await`：

```js
async function loadOneByOne(ids) {
  const results = [];
  for (const id of ids) {
    results.push(await wait(300, `留言 ${id}`));   // 上一条回来才发下一条
  }
  return results;
}
```

`for await...of` 用于数据源本身是异步迭代器的情况，比如逐条读取流。它的每次迭代会等异步值就绪；对普通数组用 `for...of` 加 `await` 就够了，两者在这里都是串行。

判断很简单：后一步用不用前一步的结果。用，就串行；不用，就并发。

## 四个容易被写法骗到的判断 {#pitfalls}

**“调用 async 函数，函数体全部异步执行。”** 函数体会同步执行到第一个 `await`。下面这段会先打印 `a`，再打印 `c`，然后打印 `b`：

```js
async function f() {
  console.log('a');
  await null;
  console.log('b');
}

f();
console.log('c');
```

```
a
c
b
```

`await` 暂停的是这个函数，不是整个程序。`f()` 立刻返回一个 Promise，调用方继续往下走。

**“两个 `await` 写在一起就是并发。”** 不是，那是串行。上面的 600ms 对 300ms 已经说明了。并发要先把 Promise 都创建出来，再一起等。

**“`try/catch` 能接住 async 函数里所有错误。”** 只能接住你 `await` 了的那些。没 `await` 的 Promise，异常落在那个 Promise 上，不会回到当前 `try`。

**“`Promise.all` 里一个失败，其他任务立刻停下。”** 不会。其他 Promise 继续执行，只是它们的结果被丢弃。用 `Promise.race` 加一个超时 Promise 也只是提前放弃等待，底层请求还在跑。要真的中止，得把 `AbortSignal` 传给请求，见《网络请求、取消与失败处理》。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：`loadOneByOne` 是串行的。如果这些留言互不依赖，怎么改成并发？

> **答案**
>
> ```js
> async function loadAll(ids) {
>   return Promise.all(ids.map(id => wait(300, `留言 ${id}`)));
> }
> ```
>
> `ids.map(...)` 在构造数组时就把所有 `wait` 都启动了，`Promise.all` 等的是全部完成。总耗时接近最慢的那一个，而不是每个 300ms 相加。
>
> 原任务里“用户 → 留言 → 回复”不能这么改，因为后一步依赖前一步的返回值。能并发的只有互不依赖的请求。

**第 2 题**：`.then` 的回调里 `return getUser(8)` 和 `return 8`，对下一条 `.then` 收到的值有什么不同？

> **答案**
>
> `return 8` 让新 Promise 以数字 8 兑现，下一条 `.then` 收到 `8`。
>
> `return getUser(8)` 让新 Promise 采用这个 Promise 的结果，下一条 `.then` 收到的是用户对象，不是 Promise 对象。这叫展平——否则链上会多出层层嵌套的 Promise。

**第 3 题**：下面代码的输出顺序是什么？

```js
async function f() {
  console.log('a');
  await null;
  console.log('b');
}

f();
console.log('c');
```

> **答案**
>
> ```
> a
> c
> b
> ```
>
> `f()` 同步执行到 `await null`，打印 `a` 后暂停；调用方接着打印 `c`；当前同步代码跑完，`await` 后面的部分作为微任务执行，打印 `b`。

## 继续阅读 {#related}

- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [网络请求、取消与失败处理](/learn/js-fetch)
- [事件循环、任务与微任务](/learn/js-events-loop)
- [异步编程：等待期间让出执行机会](/learn/async)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
