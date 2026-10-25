# 状态提升与 Context

## 左侧换项目，右侧为什么没反应 {#lifting-problem}

学完这一篇，你能把兄弟组件共用的状态交给父级保管，并在层级很深时用 Context 取值，而不是复制第二份状态。

留言板左边是一列项目，右边是当前项目的留言。如果左边自己存一份 `selectedId`，右边也存一份，再靠 Effect 把右边那份改成左边的新值，最初通常能跑。

项目切快一点，右侧可能先闪一下旧留言，或者两边短暂地指向不同项目。多一个入口修改选择，就多一处同步代码。

这类“两边必须一致”的事实不该有第二份。把 `selectedId` 提到两个组件的共同父级，左边只报告用户点了谁，右边只读这个值。

## 把 selectedId 交给 App 保管 {#lifting-example}

新建一个 Vite 项目：

```bash
npm create vite@latest message-board -- --template react
cd message-board
npm install
npm run dev
```

把 `src/App.jsx` 换成下面的完整代码：

```jsx
import { useState } from 'react';

const projects = [
  { id: 'weekend', name: '周末计划' },
  { id: 'reading', name: '读书会' },
];

const initialMessages = {
  weekend: [
    { id: 'w1', text: '周六去爬山吗？' },
    { id: 'w2', text: '我带水和面包。' },
  ],
  reading: [{ id: 'r1', text: '这周读《小王子》。' }],
};

let nextId = 10;

function ProjectList({ projects, selectedId, onSelect }) {
  return (
    <aside>
      <h2>项目</h2>
      <ul>
        {projects.map((project) => (
          <li key={project.id}>
            <button
              type="button"
              onClick={() => onSelect(project.id)}
              aria-pressed={project.id === selectedId}
            >
              {project.name}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function MessageArea({ project, messages, onAddMessage }) {
  const [draft, setDraft] = useState('');

  function handleSubmit(event) {
    event.preventDefault();
    onAddMessage(draft);
    setDraft('');
  }

  return (
    <section>
      <h2>{project.name}</h2>

      <form onSubmit={handleSubmit}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={`给「${project.name}」写留言`}
        />
        <button type="submit">提交</button>
      </form>

      {messages.length === 0 ? (
        <p>这个项目还没有留言。</p>
      ) : (
        <ul>
          {messages.map((message) => (
            <li key={message.id}>{message.text}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function App() {
  const [selectedId, setSelectedId] = useState(projects[0].id);
  const [messagesByProject, setMessagesByProject] = useState(initialMessages);

  const selectedProject = projects.find((project) => project.id === selectedId);
  const messages = messagesByProject[selectedId] ?? [];

  function addMessage(text) {
    const trimmed = text.trim();
    if (!trimmed) return;

    setMessagesByProject((current) => ({
      ...current,
      [selectedId]: [
        { id: `m${nextId++}`, text: trimmed },
        ...(current[selectedId] ?? []),
      ],
    }));
  }

  return (
    <main>
      <h1>留言板</h1>
      <div style={{ display: 'flex', gap: 24 }}>
        <ProjectList
          projects={projects}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        <MessageArea
          project={selectedProject}
          messages={messages}
          onAddMessage={addMessage}
        />
      </div>
    </main>
  );
}
```

你应该看到：

```text
左边有两个项目按钮，当前选中的「周末计划」按钮带有按下状态。
右边标题是「周末计划」，下面有两条留言和一个输入框。
点左边的「读书会」，右边标题和列表一起换成读书会的一条留言，输入框里没提交的草稿还保留着。
在读书会提交一条新留言，它只出现在读书会；切回周末计划，原留言没有被改。
```

## 数据往下走，回调往上走 {#props-flow}

`App` 持有当前选择和按项目保存的留言数据。`selectedId` 是左右两区必须共用的事实；`messagesByProject` 跟着当前项目走，交给同一个所有者保管，切换项目时就能稳定取到对应的一组。`selectedProject` 和 `messages` 都是从它们算出来的，不再单独存一份 state。

`ProjectList` 拿到 `selectedId` 决定哪个按钮显示为选中，拿到 `onSelect` 来报告点击。它不保存自己的选中值。`onSelect` 直接用了 `setSelectedId`，因为签名正好匹配；如果父级还要记录日志或校验权限，可以包一层函数，但入口仍然只有一个。

`MessageArea` 拿到当前项目、当前留言和添加留言的回调。它没有修改父级数组，只在提交时调用 `onAddMessage(text)`。真正的新数据由 `App` 创建，再作为新的 props 流回来。

`draft` 留在 `MessageArea` 自己手里。项目列表不关心用户正在输入什么，兄弟组件也不需要这份草稿，所以没有把它提升。**只把必须同步的事实放上去，不是把所有 state 都搬到最顶层。**

这套方向可以记成：数据往下走，事件往上走。父级拥有数据，子级通过回调表达“用户想改什么”。子级不能直接改 props，所以不会出现两个组件各改一半的情况。

## 层级太深时用 Context 传值 {#context-example}

如果 `ProjectList` 和 `MessageArea` 中间隔了好几层布局组件，每一层都得把 `selectedId`、`messages`、回调原样往下转，代码会变得很吵。Context 允许上层提供一个值，深层组件直接读取，不必逐层传 props。

把 `src/App.jsx` 换成这份 Context 版本。界面行为和上一版相同，项目清单与留言区都没有接收 props：

```jsx
import { createContext, useContext, useState } from 'react';

const projects = [
  { id: 'weekend', name: '周末计划' },
  { id: 'reading', name: '读书会' },
];

const initialMessages = {
  weekend: [
    { id: 'w1', text: '周六去爬山吗？' },
    { id: 'w2', text: '我带水和面包。' },
  ],
  reading: [{ id: 'r1', text: '这周读《小王子》。' }],
};

let nextId = 10;

const ProjectContext = createContext(null);

function useProject() {
  const value = useContext(ProjectContext);

  if (value === null) {
    throw new Error('useProject 必须放在 ProjectProvider 里面');
  }

  return value;
}

function ProjectProvider({ children }) {
  const [selectedId, setSelectedId] = useState(projects[0].id);
  const [messagesByProject, setMessagesByProject] = useState(initialMessages);

  const selectedProject = projects.find((project) => project.id === selectedId);
  const messages = messagesByProject[selectedId] ?? [];

  function addMessage(text) {
    const trimmed = text.trim();
    if (!trimmed) return;

    setMessagesByProject((current) => ({
      ...current,
      [selectedId]: [
        { id: `m${nextId++}`, text: trimmed },
        ...(current[selectedId] ?? []),
      ],
    }));
  }

  const value = {
    projects,
    selectedId,
    setSelectedId,
    selectedProject,
    messages,
    addMessage,
  };

  return (
    <ProjectContext.Provider value={value}>
      {children}
    </ProjectContext.Provider>
  );
}

function ProjectList() {
  const { projects, selectedId, setSelectedId } = useProject();

  return (
    <ul>
      {projects.map((project) => (
        <li key={project.id}>
          <button
            type="button"
            onClick={() => setSelectedId(project.id)}
            aria-pressed={project.id === selectedId}
          >
            {project.name}
          </button>
        </li>
      ))}
    </ul>
  );
}

function MessageArea() {
  const { selectedProject, messages, addMessage } = useProject();
  const [draft, setDraft] = useState('');

  function handleSubmit(event) {
    event.preventDefault();
    addMessage(draft);
    setDraft('');
  }

  return (
    <section>
      <h2>{selectedProject.name}</h2>

      <form onSubmit={handleSubmit}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={`给「${selectedProject.name}」写留言`}
        />
        <button type="submit">提交</button>
      </form>

      {messages.length === 0 ? (
        <p>这个项目还没有留言。</p>
      ) : (
        <ul>
          {messages.map((message) => (
            <li key={message.id}>{message.text}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Sidebar() {
  return (
    <aside>
      <h2>项目</h2>
      <ProjectList />
    </aside>
  );
}

function Content() {
  return (
    <div>
      <MessageArea />
    </div>
  );
}

export default function App() {
  return (
    <ProjectProvider>
      <main>
        <h1>留言板</h1>
        <div style={{ display: 'flex', gap: 24 }}>
          <Sidebar />
          <Content />
        </div>
      </main>
    </ProjectProvider>
  );
}
```

你应该看到和上一版一样的界面：点左边的项目，右边标题、留言和草稿行为都不变。区别在代码里：`Sidebar`、`Content` 没有把任何 props 往下转，`ProjectList` 和 `MessageArea` 都从 `useProject()` 取自己需要的那部分。

## Context 不是状态容器 {#context-not-store}

`createContext` 只创建了一条传递通道。真正保存 `selectedId` 和 `messagesByProject` 的，还是 `ProjectProvider` 里的两个 `useState`。Context 不负责持久化、不发请求、不比较业务数据，也不会在 Provider 卸载后保留状态。

还有一处很容易忽略：Provider 的 `value` 是一个新对象。

```jsx
const value = {
  projects,
  selectedId,
  setSelectedId,
  selectedProject,
  messages,
  addMessage,
};
```

Provider 每重新渲染一次，这个对象字面量就新建一次。React 用 `Object.is` 比较前后两次的 `value`，引用不同就把所有消费者标记为需要更新。`ProjectList` 只用了 `projects` 和 `selectedId`，但在 `addMessage` 修改留言、Provider 重渲染时，它也会跟着渲染，因为 `value` 整体换了。

如果项目选择这部分会被频繁重渲染，可以把选择相关的值单独 memo 化（记得从 React 引入 `useMemo`）：

```jsx
const value = useMemo(
  () => ({ selectedId, setSelectedId }),
  [selectedId],
);
```

更稳妥的做法是按变化频率拆 Context：主题一个，项目选择一个，留言数据一个。主题切换时，只订阅主题的组件重渲染；项目消费者不必知道主题变了。一个巨大的“应用 Context”会让所有消费者订阅同一份大对象，Context 没有内置的字段级选择器来避免这件事。

Context 也管不了数据从哪里来。`localStorage` 里存的是浏览器当时的一份快照，不是服务端最新的留言，也不能当权限依据。需要持久化时，仍然要明确写入时机和冲突处理。

## 五处容易放错的状态 {#lifting-pitfalls}

**“两个组件都要用，就各存一份，再用 Effect 同步。”** 两份就可能在某一帧不一致，同步代码还要处理循环和先后顺序。找共同父级或明确的共享层，只留一份。

**“状态提升就是把所有 state 都搬到一个大 App 里。”** 只提升兄弟组件必须共同读取的事实。这个示例里的草稿只属于输入框，就没有上移。所有东西都放顶层会让父级重渲染范围变大，也会让状态归属变得模糊。

**“Context 是全局状态库，放进去就自动共享和持久化。”** Context 只是读取通道。状态仍由 Provider 里的 `useState` 或别的数据源提供；Provider 卸载，状态就没了。要持久化得自己写，要请求缓存得用数据层。

**“Provider 的 value 写成对象没关系，React 会浅比较每个字段。”** React 比较的是整个 value 的引用，不做字段级浅比较。对象字面量每次都是新引用，所有消费者都会更新。memo 化 value 或拆分 Context，才能缩小更新范围。

**“localStorage 里保存的项目就是当前事实。”** 它只是客户端上次写入的快照。另一个标签页可能已经改了项目，服务端也可能撤销了权限。需要权威数据时，从服务端重新读，并处理本地值和服务器值的差异。

## 什么时候不该共享 {#lifting-tradeoffs}

先让状态待在离使用位置最近的地方。只有两个以上组件需要读到同一份事实，并且必须保持一致时，才往上提。提升的范围越大，改动入口越多，重渲染覆盖的组件也越广。

Context 适合变化不频繁、读取范围广的值：主题、当前登录用户、当前项目、界面语言。高频变化、结构复杂、需要细粒度订阅的数据，交给带选择器和缓存机制的数据层通常更合适。工具不是关键，关键是状态归谁所有、谁能修改。

如果选中的项目需要分享链接、刷新后恢复，URL 参数往往比组件 state 更合适。它天然是一个外部事实，浏览器前进后退也能用。Context 可以把这个值分发下去，但不负责把它写进地址栏。

性能上先不要过度担心。把状态提上去会多渲染几个组件，规模小时完全不是问题。真的出现卡顿，再拆分 Context、memo 组件或调整状态位置；不要为了想象中的性能把所有状态拆得七零八落。

## 练习 {#self-check}

**第 1 题**：左右两个兄弟组件各自保存 `selectedId`，每次点击左边后，用一个 Effect 把右边的值改掉。这样做的问题是什么？

> **答案**
>
> 同一件事有了两份权威状态。点击后、Effect 运行前，右边还指向旧项目，界面可能闪一下；如果右边也能修改项目，两个 Effect 还可能互相触发。
>
> 应该把 `selectedId` 提升到共同父级，左边只调用 `onSelect`，右边只读 props。只保留一份值，就不需要同步 Effect。

**第 2 题**：为什么这个示例把 `selectedId` 和 `messagesByProject` 放在 `App`，却把输入框的 `draft` 留在 `MessageArea`？

> **答案**
>
> `selectedId` 同时决定左边哪个按钮选中、右边显示哪个项目，必须提升到共同父级。`messagesByProject` 只有留言区读取，本来可以留在留言区；这里让 `App` 保管，是为了让当前选择和对应项目的留言在同一个所有者手里，切换项目时不用重建留言区。
>
> `draft` 只有当前输入框使用，切项目时也不要求兄弟组件知道。留成局部状态，组件更独立，父级也不会因为用户每敲一个字就重渲染整个布局。

**第 3 题**：下面的 Provider 为什么会让所有消费者在每次 Provider 渲染时都更新？怎么改？

```jsx
function Provider({ children }) {
  const [selectedId, setSelectedId] = useState('weekend');

  return (
    <ProjectContext.Provider value={{ selectedId, setSelectedId }}>
      {children}
    </ProjectContext.Provider>
  );
}
```

> **答案**
>
> `value={{ selectedId, setSelectedId }}` 每次渲染都会创建一个新对象。React 用引用比较前后两次 value，认为它变了，于是所有消费者都重渲染，哪怕 `selectedId` 没变。
>
> 把 value 包进 `useMemo`：
>
> ```jsx
> const value = useMemo(
>   () => ({ selectedId, setSelectedId }),
>   [selectedId],
> );
> ```
>
> 这样只有 `selectedId` 变化时 value 才换引用。若 Context 里混了很多高频和低频字段，按用途拆成多个 Provider 更清楚。

## 继续阅读 {#related}

- [Props：组件之间怎样传数据](/learn/react-props)
- [State、重新渲染与状态快照](/learn/react-state)
- [URL、JSON 与 API 契约](/learn/web-api)
- [Hooks 的调用规则与组合](/learn/react-hooks)

## 参考资料 {#sources}

- [React 中文文档](https://zh-hans.react.dev/learn)；作者：React contributors and Chinese translators；CC-BY-4.0。版本：React 19；导入日网页快照; sha256:09ea40c4754c86de7a56932ec640aa2d9e634097c8eae09ac45ded52e6e637ad。
