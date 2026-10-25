# Effect、依赖与清理

## Effect 同步的是 React 外面的东西 {#effect-sync}

学完这一篇，你能用 Effect 同步窗口、请求和页面标题，并在项目切换或组件卸载时把上一次同步清理干净。

留言板切到另一个项目时，三件事要跟着变：浏览器标签页的标题、按项目取回的留言、窄窗口下的排版。窗口大小和 `document.title` 不在 React 的状态树里，留言也要从服务端按项目取回。它们都和 React 外面的东西有关。

React 的渲染只负责把 props 和 state 变成界面。**Effect 是组件和外部系统同步的地方**，不是“挂载时执行一次”的生命周期按钮。

适合放进 Effect 的事情有：订阅浏览器事件、按 id 请求数据、修改页面标题、初始化第三方控件。用户点提交、按关键词筛选已有留言、从现有 state 算一个总数，这些都不需要 Effect。

## 让窗口、请求和标题跟着项目走 {#effect-example}

新建一个 Vite 项目：

```bash
npm create vite@latest message-board -- --template react
cd message-board
npm install
npm run dev
```

把 `src/App.jsx` 换成下面的完整代码。Vite 模板的 `main.jsx` 用 `StrictMode` 包着 `App`，后面的重复执行现象和它有关。

```jsx
import { useEffect, useState } from 'react';

const projects = [
  { id: 'weekend', name: '周末计划' },
  { id: 'reading', name: '读书会' },
  { id: 'archive', name: '归档' },
];

const seededMessages = {
  weekend: [
    { id: 'm1', text: '周六去爬山吗？' },
    { id: 'm2', text: '我带水和面包。' },
  ],
  reading: [{ id: 'm3', text: '这周读《小王子》。' }],
};

let nextLocalId = 1;

function loadMessages(projectId, signal) {
  const delay = projectId === 'weekend' ? 900 : 150;

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      if (projectId === 'archive') {
        reject(new Error('这个项目的留言暂时读不到'));
        return;
      }
      resolve(seededMessages[projectId] ?? []);
    }, delay);

    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('请求已取消', 'AbortError'));
      },
      { once: true },
    );
  });
}

export default function App() {
  const [projectId, setProjectId] = useState('weekend');
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [draft, setDraft] = useState('');
  const [windowWidth, setWindowWidth] = useState(window.innerWidth);

  const project = projects.find((item) => item.id === projectId);
  const projectName = project?.name ?? '留言板';

  useEffect(() => {
    function handleResize() {
      setWindowWidth(window.innerWidth);
    }

    console.log('建立 resize 订阅');
    window.addEventListener('resize', handleResize);

    return () => {
      console.log('撤销 resize 订阅');
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;

    setStatus('loading');
    setError('');
    setMessages([]); // 项目已经换了，旧留言不该继续出现在新项目下面

    loadMessages(projectId, controller.signal)
      .then((data) => {
        if (disposed) return;
        setMessages(data);
        setStatus('ready');
      })
      .catch((problem) => {
        if (disposed || problem.name === 'AbortError') return;
        setError(problem.message);
        setStatus('error');
      });

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [projectId]);

  useEffect(() => {
    document.title = `${projectName} · 留言板`;
  }, [projectName]);

  function handleProjectChange(event) {
    const nextProjectId = event.target.value;
    setProjectId(nextProjectId);
    setMessages([]);
    setStatus('loading');
    setError('');
    setDraft('');
  }

  function handleSubmit(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;

    setMessages((current) => [
      { id: `local-${nextLocalId++}`, text },
      ...current,
    ]);
    setDraft('');
  }

  return (
    <main>
      <h1>留言板</h1>

      <label>
        当前项目：
        <select value={projectId} onChange={handleProjectChange}>
          {projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>

      <p>
        窗口宽度：{windowWidth}px（{windowWidth < 640 ? '窄屏' : '宽屏'}）
      </p>

      <form onSubmit={handleSubmit}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="写一条留言"
        />
        <button type="submit" disabled={status !== 'ready'}>
          提交
        </button>
      </form>

      {status === 'loading' && <p>加载中…</p>}
      {status === 'error' && <p>加载失败：{error}</p>}
      {status === 'ready' && messages.length === 0 && (
        <p>这个项目还没有留言。</p>
      )}
      {status === 'ready' && messages.length > 0 && (
        <ul>
          {messages.map((message) => (
            <li key={message.id}>{message.text}</li>
          ))}
        </ul>
      )}
    </main>
  );
}
```

你应该看到：

```text
页面先显示「加载中…」，约 0.9 秒后出现「周末计划」的两条留言。
浏览器标签页的标题变成「周末计划 · 留言板」。
把窗口拖窄到 640px 以下，页面里的「宽屏」变成「窄屏」。
切到「读书会」，留言换成一条《小王子》。
切到「归档」，显示「加载失败：这个项目的留言暂时读不到」。
从「周末计划」快速切到「读书会」，慢请求回来后不会覆盖读书会的列表。
在输入框提交新留言，它会出现在当前列表的第一条。
```

开发模式打开控制台，还会看到成对的订阅日志：

```text
建立 resize 订阅
撤销 resize 订阅
建立 resize 订阅
```

## 三段 Effect 各自在同步什么 {#effect-walkthrough}

**窗口宽度那段**：Effect 在组件提交后给 `window` 加监听。`handleResize` 只在浏览器触发 resize 时调用，然后 `setWindowWidth` 引起一次渲染。依赖数组是空的，因为这段代码没有读取任何会随渲染变化的 props 或 state；`setWindowWidth` 和 `window` 本身都是稳定的。

清理函数必须移除同一个 `handleResize`。函数写在 Effect 里面，每次运行都闭包住自己这一份，清理时正好拿得到。只加不删，组件多挂载几次就会叠出多个监听。

**项目数据那段**：依赖是 `[projectId]`。项目一变，React 先运行上一轮的清理函数，把旧请求标记为作废并调用 `abort()`，再运行新一轮的 Effect。这样晚到的旧结果既不会写进界面，底层计时器或网络请求也会被停掉。

代码用了两层保护。`disposed` 管界面：哪怕某个异步任务不支持取消，旧结果回来时也不能调用 `setMessages`。`AbortController` 管请求本身：它让真正支持取消的接口停止工作，少占资源。只有 `disposed` 不算取消，只是不看结果。

`handleProjectChange` 里也清空了 `messages` 并把状态设成加载中。因为 Effect 在提交并绘制之后才运行，只在 Effect 里清空的话，切换项目的那一帧可能还闪着上一个项目的列表。

**页面标题那段**：它只改 `document.title`，依赖是项目名。切项目时标题跟着换。这里不返回清理函数，因为页面存在期间标题就该保留；如果整个留言板会被卸载并需要恢复原来的标题，就可以在清理函数里保存和还原。

## 依赖数组与开发模式的重复执行 {#dependencies}

依赖数组不是“你希望它在什么时候运行”的开关。它声明这段 Effect 读取了哪些渲染值。每次渲染后，React 用 `Object.is` 比较数组里的每一项，有任何变化就清理旧 Effect，再运行新 Effect。

漏写很直接：Effect 闭包会一直拿着第一次渲染时的值。

```jsx
useEffect(() => {
  const timer = setInterval(() => {
    console.log(`当前项目：${project.name}`);
  }, 1000);

  return () => clearInterval(timer);
}, []); // 永远读第一次渲染时的 project
```

项目切到「读书会」后，控制台仍会每秒打印「周末计划」。因为依赖是空数组，Effect 从不重跑，回调里的 `project` 停留在第一次渲染的快照。把 `project.name` 填进依赖，React 才会在项目切换时换掉这个计时器。

多写也会出问题，而且往往不是你预期的“更安全”：

```jsx
useEffect(() => {
  loadMessages(projectId).then((data) => setMessages(data));
}, [projectId, messages]);
```

请求成功会调用 `setMessages`，`messages` 一变，Effect 又跑，再请求，再设置，形成循环。`projectId` 已经足够描述“按哪个项目取数据”，`messages` 是结果，不该拿来触发取数据。

依赖里放对象也要看身份。对象字面量每次渲染都是新对象，React 比较引用时会认为它变了：

```jsx
const options = { page: 1 }; // 每次渲染都新建

useEffect(() => {
  loadPage(options);
}, [options]); // 每次渲染后都会再执行
```

能拆成数字或字符串就拆开；确实需要对象，就把它变成稳定的 state、`useMemo` 结果，或者移到组件外面。

**开发模式会故意再执行一次。** `StrictMode` 在开发模式下会对初始挂载的 Effect 做一次额外的检查：运行 setup，立刻运行 cleanup，再运行一次 setup。上面那段 resize 日志就是这三步的结果。生产构建不会这样重复执行。

这个行为不是为了烦你。它逼着每个 Effect 做到两件事：setup 能独立建立一份完整资源，cleanup 能把这同一份资源完整撤销。如果你在 setup 里加监听、cleanup 里什么都不做，开发模式就会立刻暴露两个监听；生产环境虽然只加一个，但组件多次挂载后仍然会漏。

所以不要为了让日志安静，删掉 `StrictMode`，也不要为了让请求只发一次而随手删依赖。请求在开发模式下可能发两次，正确的处理是取消前一次，或者缓存和去重。清理写对了，第二次执行就只是多一次短暂的建立和撤销。

## 能算的和点击触发的，别绕进 Effect {#effect-boundaries}

能直接从现有数据算出来的值，在渲染时算：

```jsx
const visibleMessages = messages.filter((message) =>
  message.text.includes(keyword),
);
const countText = `${visibleMessages.length} 条留言`;
```

不要为它再建一个 state，然后用 Effect 监听 `messages` 和 `keyword` 去 `setVisibleMessages`。那会多一次渲染，还会出现“原数组已经变了、派生数组还没跟上”的中间状态。依赖链也会变长：A 的 Effect 改 B，B 的 Effect 改 C。

用户点击造成的动作，写在事件处理函数里。下面这句提交逻辑既不依赖渲染，也不需要等 DOM 更新：

```jsx
function handleSubmit(event) {
  event.preventDefault();
  addMessage(draft);
  setDraft('');
}
```

如果你写一个 Effect 监听 `draft` 去发消息，它会在用户每次敲键盘时运行，而不是在点击提交时运行。Effect 看不到“用户想提交”这个意图，事件处理函数看得到。

还有一种常见的绕路：props 变化后用 Effect 重置局部 state。

```jsx
useEffect(() => {
  setDraft('');
}, [projectId]); // 切换项目后，旧草稿会先留一帧
```

如果只想在项目变化时重置组件，给组件换 key 更直接：

```jsx
<Composer key={projectId} projectId={projectId} />
```

key 变化会卸载旧的 `Composer`，内部草稿直接消失，不会先渲染一帧旧值。如果草稿在父级 state 里，就在切换项目的事件里清空，或者按项目分开存。

## 五个容易留下的隐患 {#effect-pitfalls}

**“空依赖数组就是只执行一次。”** 它的意思是“不依赖任何会变化的渲染值”，不代表天然安全。如果 Effect 读了 props 或 state，空数组会让它一直读旧值。开发模式还会执行两次。只有在读取的全是稳定值时，空数组才合适。

**“漏了依赖，用 eslint-disable 压掉警告就行。”** 警告是在说闭包可能读到旧值。压掉以后，问题还在，只是没人再提醒。要么把值放进依赖，要么把读取移出 Effect，要么调整 Effect 的结构。

**“把旧结果标记成忽略，就等于取消了请求。”** 忽略只保护界面，网络请求、计时器、数据库查询可能还在跑。能用 `AbortController` 就真正取消；接口不支持取消时，再用 `disposed` 这类标记兜底。

**“从现有 state 能算出来的值，放进 Effect 再 setState 更稳。”** 多一份 state 就多一份可能不同步的数据，还多一次渲染。筛选、排序、计数、拼接标题，优先在渲染时算。

**“清理函数随便删掉当前那个监听就行。”** 清理要撤销的是**这一轮 Effect 建立的具体资源**。这次加的是 `handleResizeA`，清理时就删 `handleResizeA`，不能拿一个新建的函数或者全局最新值去删。闭包在这里是帮手，不是障碍。

## Effect 变多时怎么收住 {#effect-tradeoffs}

一段 Effect 只做一件事，边界最好能说成“同步窗口大小”或“按项目取留言”。几段 Effect 互相 `setState`、互相触发，追踪一个用户操作要跳好几处，就应该合并所有权或改用事件处理。

重复出现的请求逻辑可以抽成自定义 Hook，例如 `useProjectMessages(projectId)`，把 `status`、`error`、取消和竞态保护包在一起。前提是它真的被复用，或者这段同步本身足够复杂。只是把二十行代码挪到另一个文件，不叫抽象。

多个页面共享同一份服务端数据时，专门的请求层通常更合适：它会处理缓存、请求去重、重试和失效。只有一个组件取一次数据时，一个带清理的 Effect 更省事。

判断是否该保留一段 Effect，可以问一句：它有没有碰到 React 之外的东西？没有，就优先考虑渲染时计算或事件处理。

## 练习 {#self-check}

**第 1 题**：下面这段 Effect 有什么问题？

```jsx
useEffect(() => {
  document.title = project.name;
}, []);
```

> **答案**
>
> 依赖数组漏了 `project.name`。组件第一次渲染后标题就固定了，之后切换项目，标签页仍显示第一次的项目名。
>
> 改成：
>
> ```jsx
> useEffect(() => {
>   document.title = project.name;
> }, [project.name]);
> ```

**第 2 题**：开发模式下，窗口监听的日志是“建立、撤销、建立”。这算 bug 吗？

> **答案**
>
> 不算。`StrictMode` 在开发模式会重新执行一次初始 Effect，用来检查 cleanup 是否完整。日志说明代码确实撤销了监听，又建立了一份新的。
>
> 如果 cleanup 是空的，第二份监听就会和第一份叠在一起。修的是清理函数，不是删掉 `StrictMode`。

**第 3 题**：项目数据 Effect 里已经调用了 `controller.abort()`，为什么还要维护 `disposed` 标记？

> **答案**
>
> `abort()` 只能取消响应 signal 的异步操作，而且它和请求完成之间可能有一个时间窗口：结果已经排在回调队列里，之后才轮到 cleanup。更一般地，第三方 Promise 可能根本不响应取消。
>
> `disposed` 是这一轮 Effect 自己的闸门。旧回调看到它为 `true` 就直接返回，不写 state；`abort()` 负责尽量停掉底层工作。两者一个守住界面，一个处理资源，职责不同。

## 继续阅读 {#related}

- [State、重新渲染与状态快照](/learn/react-state)
- [Promise 与 async/await](/learn/js-async)
- [Hooks 的调用规则与组合](/learn/react-hooks)
- [网络请求、取消与失败处理](/learn/js-fetch)

## 参考资料 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
