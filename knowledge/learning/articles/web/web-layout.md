# Flex、Grid 与响应式布局

## 三条留言先排成一列 {#layout-overview}

学完这一篇，你能把留言板排成三行一列，再改成侧栏加主区，并让窄屏自动换排法。

留言板只有三个块：标题、输入框和提交按钮、留言列表。宽屏上看着没问题，把窗口拖窄一半，输入框会被压成一条细缝，长留言还会把页面撑出横向滚动条。

布局处理的就是这些位置关系。Flex 让子元素沿着一条轴排队；Grid 把页面切成行和列；`@media` 在窗口宽度变化时换一套排法。下面始终用同一份留言板内容，只改外层怎么排。

## 用 Flex 把输入框和按钮放一行 {#flex-composer}

新建 `board.html`，把整段代码存进去，双击用浏览器打开。

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>留言板</title>
  <style>
    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: system-ui, sans-serif;
      background: #f3f3f1;
      color: #1f2328;
    }

    .board {
      max-width: 720px;
      margin: 32px auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    h1 {
      margin: 0;
      font-size: 28px;
    }

    .composer {
      display: flex;
      gap: 8px;
    }

    .composer input {
      flex: 1;
      min-width: 0;
      padding: 10px 12px;
      font: inherit;
      border: 1px solid #aaa;
      border-radius: 6px;
    }

    .composer button {
      flex: 0 0 auto;
      padding: 10px 16px;
      font: inherit;
      color: white;
      background: #1f6feb;
      border: 0;
      border-radius: 6px;
    }

    .messages {
      margin: 0;
      padding: 0;
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .messages li {
      padding: 12px 16px;
      background: white;
      border: 1px solid #ddd;
      border-radius: 6px;
    }
  </style>
</head>
<body>
  <main class="board">
    <h1>留言板</h1>

    <form class="composer">
      <input aria-label="留言内容" placeholder="写点什么">
      <button type="submit">提交</button>
    </form>

    <ul class="messages">
      <li>第一条留言</li>
      <li>第二条留言</li>
    </ul>
  </main>
</body>
</html>
```

浏览器里应看到类似这样的结构：

```
留言板

[ 写点什么                    ] [ 提交 ]
[ 第一条留言 ]
[ 第二条留言 ]
```

整个页面是一列，输入框和按钮那一行里再分成左右两块。

**第一步，外层三行怎么来的。** `.board` 设了 `display: flex` 和 `flex-direction: column`，它的三个直接子元素——标题、表单、列表——就沿纵向依次排。`gap: 16px` 在它们之间留出空隙，不需要靠外边距硬凑。

**第二步，表单里的横向一行。** `.composer` 也设了 `display: flex`，但没有写方向，默认就是 `row`。两个子元素因此从左到右排。

**第三步，`flex: 1` 分的是剩余宽度。** 输入框的 `flex: 1` 是 `flex-grow: 1; flex-shrink: 1; flex-basis: 0%` 的简写。按钮按自己的内容宽度占位，间距先扣掉，剩下多少宽度，输入框就拿多少。它并不是“宽度等于 100%”，否则按钮会被挤出容器。

**第四步，按钮为什么不跟着长。** `flex: 0 0 auto` 表示不放大、不缩小、基准尺寸用内容宽度。提交按钮的字数变了，按钮跟着变宽，输入框相应少拿一点剩余空间。

`min-width: 0` 也不是装饰。输入框默认有一个由内容算出的最小宽度，窗口很窄时它可能不肯继续缩，结果撑破整行。把它设成 0，收缩才真的能发生。

再看两条轴：

| 容器 | 主轴方向 | `justify-content` 管什么 | `align-items` 管什么 |
|---|---|---|---|
| `.board` | 纵向 | 三行之间怎么分配剩余高度 | 每一行在横向怎么对齐 |
| `.composer` | 横向 | 输入框和按钮怎么分配剩余宽度 | 两个元素在垂直方向怎么对齐 |

这张表里的“横向”“纵向”不是 Flex 固定的。它们由 `flex-direction` 决定。

## 主轴换方向，对齐也跟着换 {#flex-axes}

`justify-content` 永远管主轴，`align-items` 永远管交叉轴。方向一换，两条轴在屏幕上的方向就跟着换。

在 `.board` 里，主轴是上下方向。临时加两行：

```css
.board {
  min-height: 100vh;
  justify-content: center;
}
```

刷新后，三块内容作为一组被挪到窗口垂直中间。`justify-content: center` 在这里做的是上下居中，不是左右居中。

再加 `align-items: center`，三块内容会缩到各自的内容宽度，并在横向居中。原因是 `.board` 的交叉轴是横向，`align-items` 决定子项在这条轴上的位置；它的默认值是 `stretch`，所以原来每块都撑满整行。

在 `.composer` 里恰好相反：

```css
.composer {
  justify-content: center;
  align-items: center;
}
```

`justify-content: center` 让输入框和按钮这组内容左右居中，`align-items: center` 让它们沿垂直方向对齐。这里有一个容易忽略的细节：输入框带着 `flex: 1`，会把剩余宽度全吃掉；没有剩余空间时，`justify-content` 看起来毫无变化。想观察左右居中的效果，先把输入框的 `flex` 改成 `flex: 0 0 240px`。

`flex: 1` 分配的是主轴上的空间。在横向的 `.composer` 里，它分宽度；如果把 `.composer` 改成 `flex-direction: column`，并且容器有明确高度，它分的就变成高度。这也是为什么布局方向改了以后，不能只检查“看起来有没有居中”。

## 侧栏和主区用 Grid 分格 {#grid-shell}

内容不变，换一个页面骨架：左侧放导航，右侧放顶栏和留言区。

新建 `grid.html`：

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>留言板 · 分栏</title>
  <style>
    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: system-ui, sans-serif;
      color: #1f2328;
    }

    .shell {
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      grid-template-rows: 64px minmax(0, 1fr);
      grid-template-areas:
        "side top"
        "side main";
      gap: 1px;
      min-height: 100vh;
      background: #c9c9c9;
    }

    .side {
      grid-area: side;
      padding: 20px;
      background: #24303f;
      color: white;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .side a {
      color: #cfe0f7;
    }

    .top {
      grid-area: top;
      padding: 16px 24px;
      background: white;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .main {
      grid-area: main;
      padding: 24px;
      background: #f3f3f1;
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-width: 0;
      overflow: auto;
    }

    .composer {
      display: flex;
      gap: 8px;
    }

    .composer input {
      flex: 1;
      min-width: 0;
      padding: 10px 12px;
      font: inherit;
      border: 1px solid #aaa;
      border-radius: 6px;
    }

    .composer button {
      flex: 0 0 auto;
      padding: 10px 16px;
      font: inherit;
      color: white;
      background: #1f6feb;
      border: 0;
      border-radius: 6px;
    }

    .messages {
      margin: 0;
      padding: 0;
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .messages li {
      padding: 12px 16px;
      background: white;
      border: 1px solid #ddd;
      border-radius: 6px;
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="side">
      <strong>留言板</strong>
      <a href="#">全部留言</a>
      <a href="#">我的留言</a>
    </aside>

    <header class="top">
      <span>全部留言</span>
      <span>2 条</span>
    </header>

    <main class="main">
      <form class="composer">
        <input aria-label="留言内容" placeholder="写点什么">
        <button type="submit">提交</button>
      </form>

      <ul class="messages">
        <li>第一条留言</li>
        <li>第二条留言</li>
      </ul>
    </main>
  </div>
</body>
</html>
```

宽屏下应看到左边 220 像素的导航，右边上顶栏、下留言区：

```
┌──────────┬──────────────────────────┐
│ 留言板   │ 全部留言          2 条   │
│ 全部留言 ├──────────────────────────┤
│ 我的留言 │ [ 写点什么...... ] [提交]│
│          │ [ 第一条留言 ]           │
│          │ [ 第二条留言 ]           │
└──────────┴──────────────────────────┘
```

`grid-template-columns` 定下两条列轨道：左边 220 像素，右边占剩余空间。`grid-template-rows` 定下两条行轨道：顶栏 64 像素，下面占剩余高度。

`grid-template-areas` 再把格子贴上名字：

```
"side top"
"side main"
```

`side` 在上、下两行都出现，所以侧栏跨两行；`top` 和 `main` 各占一个右格。三个子元素分别写 `grid-area: side`、`grid-area: top`、`grid-area: main`，浏览器就把它们放进对应的格子里，DOM 顺序不用为了视觉位置重排。

`fr` 分的是**扣掉固定轨道和间距之后剩下的空间**。这里两列的总宽先减去 220 像素和 1 像素间距，剩下的全给右列；换成一个百分比，百分比会按整个容器算，容易和间距打架，还可能超出 100%。

`minmax(0, 1fr)` 比单写 `1fr` 多管一件事。网格轨道的自动最小尺寸通常等于内容的 min-content；如果留言里塞进一条没有空格的超长地址，右列可能被它撑宽，整个页面出现横向滚动。`minmax(0, 1fr)` 把最小尺寸压到 0，`.main` 上的 `min-width: 0` 再允许子项收缩，`overflow: auto` 负责在真正放不下时给出局部滚动条。

注意这里同时用了 Grid 和 Flex：页面大骨架交给 Grid，顶栏、侧栏、主区内部的一行或一列继续用 Flex。它们不是只能二选一。

## 窗口变窄，同一条留言换一种排法 {#responsive-reflow}

把窗口拖到 640 像素以下，220 像素侧栏再占着左列，留言区就只剩很窄的一条。这时要换模板，不是重写内容。

在 `grid.html` 的样式表结束前追加：

```css
@media (max-width: 640px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto minmax(0, 1fr);
    grid-template-areas:
      "side"
      "top"
      "main";
  }

  .side {
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
    padding: 12px 16px;
  }

  .top {
    padding: 12px 16px;
  }

  .main {
    padding: 16px;
  }
}

@media (max-width: 480px) {
  .composer {
    flex-direction: column;
  }

  .composer input {
    flex: 0 0 auto;
  }

  .composer button {
    width: 100%;
  }
}
```

窗口刚缩到 640 像素以下时，结构变成：

```
[ 留言板  全部留言  我的留言 ]   <- 侧栏横排
[ 全部留言              2 条 ]   <- 顶栏
[ 写点什么...... ] [ 提交 ]      <- 输入框和按钮仍在一行
[ 第一条留言 ]
[ 第二条留言 ]
```

继续缩到 480 像素以下，表单那一行也拆开：

```
[ 写点什么..................]
[ 提交.....................]
[ 第一条留言 ]
[ 第二条留言 ]
```

这三档变化里，DOM 和文案没有动。宽屏是侧栏加右列；640 像素以下变成一列三行，侧栏横排；480 像素以下输入框和按钮从一行变成两行。

变的是三组声明：

- 列轨道从 `220px minmax(0, 1fr)` 变成 `1fr`，没有侧栏列了。
- 行轨道从两行变成三行，`side`、`top`、`main` 各占一行。
- 480 像素以下，`.composer` 的方向从横向变成纵向，并且输入框不再吃剩余空间，按钮占满整行。

`@media (max-width: 640px)` 里的规则要放在基础规则之后。相同优先级时，后写的覆盖先写的；顺序反了，窄屏规则会被后面的基础规则盖掉。断点数字不是魔法，640 和 480 只是这份例子的选择；换成项目里的导航宽度和正文最小可读宽度，再用真实窗口试。

## 四个看起来对、实际会歪的写法 {#layout-pitfalls}

**“`justify-content` 和 `align-items` 都是居中用的，随便写一个。”** 它们管的是不同的轴。把 `.board` 临时改成 `justify-content: center; align-items: center;`，三块内容在纵向居中，同时每一块缩到内容宽度、在横向居中。只写 `justify-content: center`，三块仍然横向撑满。轴和属性对不上，调很久也调不到想要的方向。

**“`flex: 1` 等于 `width: 100%`。”** 它分的是剩余空间。把 `.composer button` 也改成 `flex: 1`，输入框和按钮会按比例分掉剩余宽度，输入框不再独占一行。再把按钮改成 `flex: 0 0 300px`，窗口不够宽时按钮保持 300 像素，输入框被压到很窄；这就是“按钮不缩、输入框缩”的代价。

**“用了 Grid，窄屏自然就排好了。”** Grid 只执行你写的轨道。删掉整段 `@media`，窗口缩到 320 像素，左列仍然固定 220 像素，右列只剩很少空间，长内容会把页面撑出横向滚动条。窄屏重排需要显式的模板变化，或者用可自动折行的布局，不是 `display: grid` 自带的。

**“给滚动区域加了 `overflow: auto` 就一定能滚。”** 滚动区域还需要一个被限制的高度或宽度。在这个骨架里，第二行是 `minmax(0, 1fr)`，主区高度被网格行约束，`overflow: auto` 才有意义。把行轨道改成 `auto`，内容会把行撑高，页面跟着变长，主区内部没有可滚的剩余空间。祖先不约束，子元素就无从“溢出”。

## 什么时候别急着上 Grid {#layout-tradeoffs}

只有一行按钮、一排标签，或者三张卡片横向排开时，Flex 加 `flex-wrap` 就够了。Grid 适合需要同时对齐行和列的地方：侧栏跨行、顶栏和主区共享右列、卡片按固定列宽铺开。页面只有一个方向的关系，Grid 的模板反而多一层维护。

这套留言板的窄屏策略也有代价。640 像素以下把侧栏放到顶部，导航会占据首屏，留言内容需要往下滚；如果侧栏很长，也可以改成折叠按钮或只保留当前入口。没有一种排法对所有内容都合适，判断标准是窄屏下用户最先要做的事还能不能一眼看到。

布局改完别只看两条短留言。塞一条没有空格的超长地址，塞二十条留言，把浏览器缩到 320 像素，再把字号放大到 200%。长内容会暴露 `min-width`、`overflow` 和固定轨道的问题；只测理想数据，页面看起来永远正常。

还有一件常被忽略的事：Grid 和 Flex 改变的是视觉位置，不改变 DOM 顺序。读屏、键盘 Tab 和复制文本仍按 DOM 走。导航放在 DOM 的前面还是后面，要按阅读顺序决定，别只为了宽屏截图把重要按钮用 `order` 挪到后面。

## 三道改布局的小题 {#self-check}

**第 1 题**：`board.html` 里，为什么输入框写 `flex: 1`，按钮写 `flex: 0 0 auto`？如果两个都写 `flex: 1`，看起来会怎样？

> **答案**
>
> `flex: 1` 让输入框拿走按钮和间距之外的剩余宽度；`flex: 0 0 auto` 让按钮保持内容宽度，不参与放大缩小。
>
> 两个都写 `flex: 1`，它们会一起分剩余空间，输入框不再独占。按钮会明显变宽，输入框相应变窄。改完在浏览器里量一下两块的实际宽度，就能看到分配结果。

**第 2 题**：把 `.shell` 里的 `minmax(0, 1fr)` 改回 `1fr`，再往留言里放一条很长的无空格字符串。可能发生什么？

> **答案**
>
> 右列可能被这条字符串的 min-content 宽度撑开，页面出现横向滚动条，侧栏和顶栏的比例被打乱。
>
> `1fr` 的自动最小尺寸不是 0。`minmax(0, 1fr)` 允许轨道缩到 0，再配合 `.main { min-width: 0; overflow: auto; }`，超长内容才留在主区内部滚动。只改其中一个，效果可能不完整。

**第 3 题**：窗口从 800 像素拖到 500 像素，DOM 里有哪一块被删掉了吗？哪些东西真的变了？

> **答案**
>
> 没有删除。标题、表单、留言列表和三个区域都还在，DOM 顺序也没变。
>
> 变的是 Grid 模板和 Flex 方向：640 像素以下列轨道只剩一条，`side`、`top`、`main` 改成三行；侧栏从竖排变横排。480 像素以下，`.composer` 从横排变竖排，按钮占满一行。响应式布局换的是排法，不是内容。

## 沿着 CSS 和组件往下读 {#related}

- [CSS 选择器、层叠与盒模型](/learn/web-css)
- [HTML 结构与语义](/learn/web-html)
- [浏览器、前端与后端](/learn/web-client-server)
- [React 组件与 JSX](/learn/react-components)

## 布局资料的出处 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
