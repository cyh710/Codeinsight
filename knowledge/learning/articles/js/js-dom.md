# DOM 与事件：点击怎样变成行为

## 点击按钮之后，页面里发生了什么 {#overview}

学完这一篇，你能用 JavaScript 读取输入框的内容，往列表里加一条留言，再让删除按钮自己找到要删的那一项。

留言板的静态部分已经有了：一个输入框、一个提交按钮、一个空的列表。点提交，页面毫无反应——HTML 只说明页面上有什么，不会自己动。

浏览器读到 HTML 后，会把它变成一棵节点树。`<body>` 下面挂着 `form` 和 `ul`，`form` 下面挂着 `input` 和 `button`。这棵树叫 DOM。JavaScript 改的不是 HTML 文本，而是这棵树；树变了，浏览器重画页面。

所以“点击变成行为”要凑齐三样东西：找到元素、在元素上挂监听器、在监听器里改树。下面用一个能跑的页面把这三样串起来。

## 写一个完整的留言板页面 {#build-the-page}

新建 `index.html`，把下面整段存进去，双击用浏览器打开：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>留言板</title>
</head>
<body>
  <h1>留言板</h1>

  <form id="form">
    <input id="input" placeholder="说点什么" autocomplete="off">
    <button type="submit">提交</button>
  </form>

  <ul id="list"></ul>

  <script>
    const form = document.querySelector('#form');
    const input = document.querySelector('#input');
    const list = document.querySelector('#list');

    form.addEventListener('submit', (event) => {
      event.preventDefault();          // 不让表单把整页刷掉

      const text = input.value.trim();
      if (text === '') return;         // 空白内容不入列表

      const item = document.createElement('li');
      const content = document.createElement('span');
      content.textContent = text;      // 当文字放进去，不当 HTML

      const remove = document.createElement('button');
      remove.className = 'remove';
      remove.textContent = '删除';

      item.append(content, remove);
      list.append(item);

      input.value = '';                // 提交完清空，方便连着写
      input.focus();
    });

    list.addEventListener('click', (event) => {
      const remove = event.target.closest('.remove');
      if (!remove) return;             // 点到的不是删除按钮，忽略
      remove.closest('li').remove();
    });
  </script>
</body>
</html>
```

先输入“今天开会改到三点”，点一次提交；再输入 `<b>hi</b>`，再提交一次。你应该看到（方括号表示按钮）：

```
留言板

[ 说点什么                    ] [ 提交 ]

· 今天开会改到三点   [删除]
· <b>hi</b>          [删除]
```

第二行原样显示 `<b>hi</b>`，尖括号还在，没有变成加粗的 hi。这个差别不是小事，下一节专门说。

## 从输入框到列表项的四步 {#walkthrough}

**第一步，找元素。** `document.querySelector('#form')` 按 CSS 选择器找第一个匹配的节点。`#form` 是 id 选择器，`.remove` 是 class 选择器，`li` 是标签选择器——和写 CSS 时一样。

找不到时它返回 `null`，后面的 `addEventListener` 会报 `Cannot read properties of null`。如果你的脚本放在 `<head>` 里，执行时 `<body>` 还没解析出来，就会撞上这个错。把内联脚本放到 `</body>` 前；外链脚本可以留在 `<head>` 里，但要给 `<script>` 加 `defer`。

**第二步，接住提交。** 监听的是 `form` 的 `submit`，不是按钮的 `click`。输入框里按回车会触发表单的隐式提交，浏览器通常还会顺带触发默认提交按钮的 `click`；但 `submit` 是表单级事件，点击、回车、代码里调用 `form.requestSubmit()` 都会经过它，不用关心默认按钮是哪一个。

`event.preventDefault()` 取消浏览器的默认动作——表单默认会带着数据请求新页面，整页一刷新，刚加的留言就没了。

`input.value.trim()` 取到用户输入并去掉首尾空格。`value` 永远是字符串，哪怕输入的是数字；空串直接 `return`，避免加一条空白留言。

**第三步，造节点、插节点。** `createElement('li')` 只造出一个游离节点，还没有挂在页面上。`textContent = text` 把留言写进去。删除按钮单独造，给它 `remove` 这个 class，父级监听器靠它认出按钮。

`item.append(content, remove)` 一次把两个子节点放进 `li`，`list.append(item)` 再把 `li` 放到列表末尾。这之前，它不占页面任何位置。

**第四步，收尾。** `input.value = ''` 清空输入框，`input.focus()` 把光标放回去。不清空的话，用户得自己删掉旧内容才能写下一条。

## textContent 留住了标签，innerHTML 执行了标签 {#text-vs-html}

打开 DevTools 的控制台（F12 里的 Console），跑这两段：

```js
const box = document.createElement('div');
box.textContent = '<b>hi</b>';

console.log(box.textContent);        // <b>hi</b>
console.log(box.innerHTML);          // &lt;b&gt;hi&lt;/b&gt;
console.log(box.querySelector('b')); // null
```

```
<b>hi</b>
&lt;b&gt;hi&lt;/b&gt;
null
```

`textContent` 创建一个文本节点，把整串 `<b>hi</b>` 当成普通字符。`innerHTML` 读出来时会把 `<` 和 `>` 转义成 `&lt;`、`&gt;`，因为它们已经是文本的一部分。`querySelector('b')` 找不到元素，返回 `null`。

再试 `innerHTML`：

```js
const box2 = document.createElement('div');
box2.innerHTML = '<b>hi</b>';

console.log(box2.textContent);              // hi
console.log(box2.querySelector('b') !== null); // true
```

```
hi
true
```

`innerHTML` 把字符串当成 HTML 源码解析，`<b>` 变成真正的加粗元素。取 `textContent` 时，标签被剥掉，只剩 `hi`。

功能差别背后是安全差别。`textContent` 不可能把字符变成元素；`innerHTML` 会。用户提交 `<img src=x onerror="alert(1)">` 时，前者显示一串字符，后者会造出一个图片元素并触发 `onerror` 里的代码。插入的 `<script>` 通过 `innerHTML` 不会执行，但事件属性会——别指望这个区别救你。

规则很短：**用户输入一律走 `textContent`；确实要插 HTML，就用可信模板并经过清洗**。`innerHTML` 还会把原有子节点整个重建，挂在上面的监听器随之丢失。

## 一个监听器管住所有删除按钮 {#delegation}

页面里可能有几百条留言。给每个删除按钮单独绑监听器，写起来重复，后来新加的按钮还得再绑一次。现在只有一个监听器，挂在 `ul` 上。

点击删除按钮时，事件先从 `window` 一路传到按钮（捕获阶段），到达按钮本身是目标阶段，再沿祖先原路返回（冒泡阶段）。按钮 → `li` → `ul` → `body` → `document`，每一层都会收到同一个事件。监听器虽然挂在 `ul` 上，也能接到按钮的点击。

监听器里的两个属性要分清：

| 属性 | 指向 |
|---|---|
| `event.target` | 实际被点的节点，这里是删除按钮 |
| `event.currentTarget` | 监听器绑定的节点，这里是 `ul` |

`event.target.closest('.remove')` 从被点的节点往上找最近的 `.remove`。找到才说明点的是删除按钮；点到留言文字或列表空白处，返回 `null`，直接忽略。再 `closest('li')` 找到要删的整行。

这么写还有一个好处：后来用 `createElement` 加进来的按钮，不需要再绑任何东西，照样能删。

`event.preventDefault()` 和 `event.stopPropagation()` 是两件事。前者取消浏览器默认行为（提交表单、跳链接），后者阻止事件继续冒泡。想拦住表单提交，用前者；在 `ul` 上监听时调用后者，会让外层监听器收不到事件。

`removeEventListener` 要求传**同一个函数引用**。两个长得一样的箭头函数不是同一个对象：

```js
const onClick = () => console.log('点了');
button.addEventListener('click', onClick);

button.removeEventListener('click', onClick);      // 生效
button.removeEventListener('click', () => console.log('点了')); // 不生效
```

## 删不掉、点两次与空白留言 {#pitfalls}

**“提交完页面闪了一下，留言没了。”** 表单的默认行为是提交并刷新。处理函数里漏了 `event.preventDefault()`，或者在调用它之前就抛错，都会这样。先看控制台有没有红色报错。

**“`innerHTML` 只是显示效果不同。”** 它会把字符串解析成节点，用户输入里的 `<img onerror=...>` 会真的执行。显示用户内容用 `textContent`。

**“元素是后加的，父级监听器收不到。”** 收得到。事件冒泡发生在点击那一刻，跟监听器绑定时元素在不在无关。前提是监听器挂在一个稳定的祖先上，删按钮时别把祖先一起删了。

**“重新写个一样的函数就能 `removeEventListener`。”** 移除看的是引用是否相同，不是源代码是否相同。要移除，就把原函数存进变量。

**“删除就是点一下的事，不用管结果。”** 如果删除还要发请求，别在点击后立刻删掉整行就当保存成功了。请求可能失败。等服务器确认再删，或者先删、失败时把行恢复并提示。

## 什么时候该直接改 DOM {#tradeoffs}

页面只有一个留言板、一份列表时，直接改 DOM 最省事：找元素、造节点、插入，几行就完。引入框架反而多一层构建和概念。

当同一份数据要驱动好几处界面——列表、条数、空状态、按钮禁用——手写更新会越来越难对齐。每一处都得记得改，漏一处就出现“列表有两条，计数写着三条”。这时 React 那类状态驱动的写法更合适：你改数据，框架负责改 DOM。别在同一个节点上混用两套写法，否则谁也说不清界面该听谁的。

事件委托能减少监听器数量，但要有稳定的父容器，还要能准确识别目标。把监听器无条件挂在 `document` 上，等于让全页面的点击都经过它，判断错一次就会误伤别的按钮。

页面切换或组件卸载时，挂在 `window`、`document` 上的监听器和未完成的定时器要手动清理。节点本身被移除后，节点上的监听器会随节点一起被回收，但全局监听器不会。

排查交互问题时，先找用户动作对应的监听器，再看它改了哪个节点的什么属性。顺序反过来，先盯着界面猜代码，通常会绕远路。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：留言内容是一串 `<b>hi</b>`，分别用 `textContent` 和 `innerHTML` 插入，页面上各看到什么？

> **答案**
>
> `textContent` 显示原样的 `<b>hi</b>`，不会加粗；`innerHTML` 显示加粗的 **hi**，因为它把 `<b>` 解析成了元素。
>
> 用户输入用前者。后者只在内容可信、或已经过清洗时使用。

**第 2 题**：删除按钮是提交之后才创建的，为什么挂在 `ul` 上的监听器能收到它的点击？此时 `event.target` 和 `event.currentTarget` 分别是什么？

> **答案**
>
> 事件从被点的按钮向上冒泡，一路经过 `li` 和 `ul`，所以挂在 `ul` 上的监听器会触发。
>
> `event.target` 是实际被点的删除按钮，`event.currentTarget` 是监听器所在的 `ul`。用 `target.closest('.remove')` 判断是不是删除按钮，用 `currentTarget` 判断监听范围。

**第 3 题**：点提交后页面闪了一下，刚加的留言没了。通常漏了什么？

> **答案**
>
> 漏了 `event.preventDefault()`。表单的默认行为是提交并请求新页面，整页刷新后 JavaScript 重建的空列表就把留言盖掉了。
>
> 在 `submit` 处理函数的第一行调用它，取消默认动作。先改 DOM 再发请求，刷新会把两件事都清空。

## 继续阅读 {#related}

- [HTML：页面的结构与语义](/learn/web-html)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)
- [事件处理与受控输入](/learn/react-events)
- [URL、JSON 与 API 契约](/learn/web-api)

## 参考资料 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
