# CSS 选择器、层叠与盒模型

## 同一份 HTML，两副面孔 {#overview}

学完这一篇，你能用选择器改页面外观，判断两条冲突规则谁生效，并量出一个盒子实际占多宽。

上一篇写出来的留言板能用，但很朴素：白底黑字，输入框和按钮都是浏览器默认样式。给同一份 HTML 接上 CSS，页面可以变整齐、变窄、变色，而 HTML 一个标签都不用改。

样式出问题也很常见：明明写了规则，页面没反应；明明写了 `width: 200px`，量出来却是 236px。这两类问题都能按固定顺序查出来。

## 先把样式表接到页面上 {#attach-styles}

把上一篇的 `index.html` 改一下：在 `head` 里加一行 `<link>`，再给几个元素加 `class`，让 CSS 有稳定的抓手。

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>留言板</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="board">
    <h1>留言板</h1>

    <form class="compose" method="get">
      <label for="text">留言内容</label>
      <input id="text" name="text" placeholder="写点什么" required>
      <button type="submit">提交</button>
    </form>

    <h2>全部留言</h2>
    <ul class="messages">
      <li>第一条留言</li>
      <li>第二条留言</li>
    </ul>
  </main>
</body>
</html>
```

同一个文件夹里新建 `styles.css`：

```css
body {
  font-family: system-ui, "Microsoft YaHei", sans-serif;
  margin: 0;
  padding: 32px 16px;
  background: #f5f5f2;
  color: #222;
}

.board {
  box-sizing: border-box;
  max-width: 480px;
  margin: 0 auto;
  padding: 24px;
  background: #fff;
}

h1 {
  font-size: 24px;
  margin-top: 0;
  color: #1f4e79;
}

h1 {
  color: #b03a2e;
}

.compose {
  width: 200px;
  padding: 16px;
  border: 2px solid #333;
  background: #fafafa;
}

label {
  display: block;
  margin-bottom: 6px;
}

input,
button {
  font: inherit;
}

.compose input {
  box-sizing: border-box;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid #999;
}

button {
  border: 0;
  padding: 6px 14px;
  background: #1f4e79;
  color: #fff;
}

.compose button {
  margin-top: 8px;
}

.messages {
  padding-left: 20px;
}

.messages li {
  margin-bottom: 8px;
}

:focus {
  outline: 2px solid #d9822b;
  outline-offset: 2px;
}
```

保存后回到浏览器，刷新。你应该看到：

```text
背景：浅灰色
中间：一张白色卡片，宽度最多 480px，页面很宽时水平居中
标题：留言板，24px，暗红色
表单：一个浅灰色窄框，深色 2px 边框，里面竖排标签、输入框、蓝色按钮
列表：全部留言，两条带圆点的留言，条与条之间有间距
焦点：点输入框或按 Tab 时，出现橙色轮廓
```

标题是**暗红色**。可是样式表里第一条 `h1` 写的是 `#1f4e79`，一种深蓝色。记住这个现象，下一节就用它讲层叠。

先看选择器。每条规则由“选谁”和“改什么”组成：

| 选择器 | 挑中谁 |
|---|---|
| `body` | 整个页面主体 |
| `.board` | `class="board"` 的那个元素 |
| `h1` | 所有 `h1` |
| `.compose` | `class="compose"` 的表单 |
| `label` | 所有标签文字 |
| `input, button` | 两种控件，逗号表示“各算一条规则” |
| `.compose input` | 表单**里面**的输入框，空格表示后代 |
| `.messages li` | 列表里的每一项 |
| `:focus` | 当前获得焦点的元素，点进去或用 Tab 到达 |

`class` 只是一个钩子，名字没有魔法。HTML 里写 `class="compose"`，CSS 里写 `.compose`，两边对上就行。用类而不是直接选 `form`，是因为页面以后多出第二个表单时，样式不会误伤它。

`input, button { font: inherit; }` 让控件使用 `body` 的字体。浏览器默认给控件一套自己的字体，跟正文不一致，这行把它们拉回来。

`.compose input` 里的 `box-sizing` 是个铺垫：它让输入框把自己算窄一点，别撑出表单的 200px。为什么需要它，第 4 节量盒子时见分晓。

`.board` 上的 `box-sizing: border-box` 是另一件事：它让 480px 这个上限把 24px 的内边距也算进去，卡片总宽不会超出 480。`.compose` 故意先不设，第 4 节量盒模型时用它看默认行为。

## 两条规则抢同一个颜色 {#cascade-fight}

刷新页面时，标题是暗红色。两条 `h1` 规则都改了 `color`，浏览器只能选一个。

它们的选择器完全相同，都是 `h1`。这种平局下，文件里更靠后的那条赢。第二条是 `#b03a2e`，所以标题红。

把两条规则对调：

```css
h1 {
  font-size: 24px;
  margin-top: 0;
  color: #b03a2e;
}

h1 {
  color: #1f4e79;
}
```

刷新，标题变蓝。同样两个选择器，换一下顺序，赢家就换了。字号那两行留着，是为了让你只看到颜色变化。

现在换一种写法。把规则改成：

```css
main h1 {
  font-size: 24px;
  margin-top: 0;
  color: #b03a2e;
}

h1 {
  color: #1f4e79;
}
```

`main h1` 在前，`h1` 在后，标题却是**红的**。这里不是后写的赢，因为两个选择器的“分量”不同。

分量叫优先级，按三个计数器比较：id 的数量、类与伪类的数量、元素的数量。

| 选择器 | id | 类/伪类 | 元素 | 结果 |
|---|---|---|---|---|
| `h1` | 0 | 0 | 1 | 被压过 |
| `main h1` | 0 | 0 | 2 | 生效 |
| `.compose input` | 0 | 1 | 1 | 比分量时排在 `h1` 前 |
| `:focus` | 0 | 1 | 0 | 按类计算 |
| `#text` | 1 | 0 | 0 | 高于上面所有不带 id 的规则 |

比较时从左往右看：先比 id 的数量；id 都是 0 时比类；类也一样多才比元素。三个数全相同，才回到“谁在后面谁赢”。

优先级不是全部。层叠的判定顺序大致是：

1. 来源与重要性：浏览器默认样式、你写的作者样式、用户样式、`!important` 各有权重。日常页面里最常见的是作者样式压过浏览器默认样式，`!important` 又能压过普通作者声明。
2. 层叠层：项目用了 `@layer` 时，先看层与层的顺序。
3. 选择器优先级：上面那三个计数器。
4. 源码顺序：前面都一样时，靠后的赢。

初学阶段遇到的冲突，几乎都在第 3 和第 4 步。看到一条规则被划掉，先算优先级；算出来一样，再比顺序。

内联样式（`<h1 style="color: green">`）比普通选择器都高，但低于带 `!important` 的规则。它把样式和结构混在一行里，排错时也容易被忽略。

## 200 像素的盒子占 236 像素 {#box-model}

看那个浅灰色表单框。样式里写的是 `width: 200px`，但它在页面上明显比 200px 宽。

浏览器量元素时，把一个盒子分成四层：

- 内容区：文字和输入框真正待的地方。
- 内边距 `padding`：内容和边框之间的留白。
- 边框 `border`：围住内容和内边距的线。
- 外边距 `margin`：盒子与其他元素之间的空隙。

`width` 默认只设**内容区**的宽度，这叫 `content-box`。`.compose` 的内容区 200px，左右各有 16px 内边距，再各加 2px 边框：

```text
200 + 16 + 16 + 2 + 2 = 236px
```

所以这个框实际占 236px，不是 200px。高度没有写死，由里面的标签、输入框、按钮撑开。

在 DevTools 里量一遍：右键表单框，选“检查”；在 Elements 面板选中 `.compose`；右侧切到 Computed（计算样式），找到盒模型图。内容框显示 200，四周标着 padding 16、border 2。把鼠标移到图上的某一块，页面上会高亮对应的区域。

现在给 `.compose` 加一行：

```css
.compose {
  box-sizing: border-box;
  width: 200px;
  padding: 16px;
  border: 2px solid #333;
  background: #fafafa;
}
```

刷新。框的外侧变成 200px，内容区剩下：

```text
200 - 16 - 16 - 2 - 2 = 164px
```

输入框写着 `width: 100%`，它会跟着从 200px 缩到 164px。盒模型图里的数字也这样变。

`border-box` 只是把 padding 和 border 算进你写的宽度，外边距仍然不算。`outline` 也不在里面：它画在边框外面，不占布局空间。

`box-sizing` 不会被继承。`.board` 设了，里面的 `.compose` 不会自动跟着变；`input` 也不会从 `.compose` 那里继承，所以 `.compose input` 要单独写一行。很多项目会在样式表开头统一设置：

```css
*,
*::before,
*::after {
  box-sizing: border-box;
}
```

这样所有元素和伪元素的宽度都按同一种方式计算，省得每次加 padding 都重新算。代价是它改变了全局默认行为，接手老项目时要先确认有没有这行。

## 样式没生效时按这个顺序查 {#troubleshoot}

**先确认样式表加载了没有。** 刷新页面，Network 面板里找 `styles.css`，状态应该是 200。打开 Elements → Styles，能看到你的规则，说明文件到了。路径写错、文件名大小写不一致、忘了 `<link>`，都会让整份文件失效。浏览器缓存了旧文件时，按 `Ctrl+F5` 强制刷新。

**再确认选择器挑中了元素。** 在 Console 里运行：

```javascript
document.querySelectorAll(".compose").length
```

返回 `1` 说明挑中一个，返回 `0` 说明类名写错、元素不在页面里，或者你查的是另一份 DOM。把 `.compose` 换成你怀疑的选择器逐个试。

**看规则是不是被别处盖掉了。** Styles 面板里被盖掉的声明会显示删除线，旁边有链接指向赢的那条规则。鼠标悬停能看它为什么赢。优先算优先级，平局再看顺序，还不行再看有没有 `!important`。

**看声明本身合不合法。** 属性名拼错、值缺少单位，浏览器会直接丢掉这一条，其他声明照常生效。`width: 200` 少了 `px` 是无效值；`colour: red` 不是合法属性。Styles 面板里无效声明会有警告图标。少写分号会让两条声明粘成一条，往往一起失效，检查时别只看一半。

**确认你改的是当前那个元素和状态。** 页面里有没有重复 `id`，`label` 和 JS 是不是找错了对象；你看到的是不是 `:hover`、`:focus` 下的样子；改父元素的宽度，子元素未必跟着变。用 Elements 面板的箭头直接点页面上的元素，比对它和样式表里的选择器。

这几步从“文件有没有到”走到“这条声明有没有赢”，每一步都能排除一类原因。比对着样式表反复改像素快得多。

## 四个看着像 bug 的现象 {#pitfalls}

**“父元素设了 `color`，子元素也变了，说明所有属性都会继承。”** 只有一部分属性会继承，比如 `color`、`font-family`、`line-height`。`width`、`margin`、`border`、`background` 默认不继承。临时给 `.board` 加 `color: #b03a2e`，列表文字会变红，因为颜色继承了；但每条留言不会因此各长出一圈边框。Computed 面板里会写“Inherited from”，能看出一个值是从哪里来的。

**“元素看不见，就是 `display: none`。”** 至少还有三种：`visibility: hidden` 保留原来的空间，只是不画出来；`opacity: 0` 看不见但仍占空间，鼠标还能点到；元素被别的东西盖住，或者宽高被压成 0。`display: none` 最彻底，盒子不生成，后面的内容会顶上来。在 DevTools 的盒模型图里，`visibility: hidden` 和 `opacity: 0` 还留着尺寸，`display: none` 什么都不剩；被盖住或尺寸为 0 要看具体情况。

**“上下两个元素的 margin 会加起来。”** 普通文档流里，相邻的上下外边距会合并，取较大的那个。上面写 `margin-bottom: 30px`，下面写 `margin-top: 20px`，中间是 30px，不是 50px。左右外边距不会这样合并。放进 Flex 或 Grid 容器后，外边距也不按这条规则合并。量间距时如果算不平，先看是不是撞上了外边距合并。

**“加 `!important` 就能盖上去。”** 它确实能压过同一来源里的普通声明，所以很容易被当成万能补丁。下一次别人要盖你的规则，就得再写一个优先级更高或更靠后的 `!important`，冲突越滚越大。先找原来的规则为什么赢：是不是选择器太重、顺序不对、旧规则没删。把源头改掉，比叠加重要性标记可维护得多。

## 写死 200 像素之后 {#sizing-tradeoffs}

`width: 200px` 让表单框固定，里面的文字变长就折行，字号变大可能挤，窗口变小也不会跟着缩。小控件、边框、图标用固定像素问题不大；一块要放正文的容器，通常用 `max-width` 加 `margin: 0 auto` 更稳。

`.board` 就是这样：窗口宽时最多 480px，并水平居中；窗口窄时自动缩到可用宽度。它没有写死 `width: 480px`，所以卡片本身不会在窄屏上横向溢出。不过里面的 `.compose` 仍然是固定 200px 内容宽，极窄的屏幕上它仍可能把卡片顶到边。弹性只作用在真正用了弹性的那一层。

高度要更小心。给一段文字容器写死 `height`，换一种字体、用户放大字号、窗口变窄导致多折几行，内容就会溢出。用 `min-height` 或干脆让内容撑开，通常更省事。

文字大小用 `rem` 会跟随用户或浏览器的根字号设置，用 `px` 则固定。哪个更合适取决于你要控制到什么程度；关键是知道自己在选哪一种，而不是随手写一个数。

颜色和间距重复出现时，可以收进变量：

```css
:root {
  --ink: #222;
  --accent: #1f4e79;
}

body {
  color: var(--ink);
}

button {
  background: var(--accent);
}
```

改一处，所有用到的地方一起变。只有一处颜色时不必上变量，多一层间接也是成本。

还有一条容易被当成装饰的决定：不要删掉焦点轮廓。它是键盘用户判断“我现在在哪”的最直接线索。可以像这份样式一样换成橙色，但要保证对比度足够、位置清楚。

读一个陌生页面的样式，从 Elements 面板里选中元素，看它实际应用了哪些规则，比从头读完整份 CSS 快。样式表和 DOM 的对应关系，在浏览器里是现成的。

## 三处样式修改练习 {#self-check}

**第 1 题**：下面两条规则，`<li class="message">` 的文字是什么颜色？把两条规则对调，结果会变吗？

```css
.message {
  color: #333;
}

li.message {
  color: #b03a2e;
}
```

> **答案**
>
> 暗红色 `#b03a2e`。
>
> `.message` 的优先级是（0, 1, 0），`li.message` 是（0, 1, 1）：类一样多，元素多一个的赢。对调顺序不会改变结果，因为优先级不同的规则不靠源码顺序决胜。

**第 2 题**：`.box` 设置了 `width: 300px; padding: 10px; border: 3px solid #333;`。它的边框盒有多宽？如果加上 `box-sizing: border-box`，内容区还剩多宽？

> **答案**
>
> 默认 `content-box` 下，300 只是内容区，左右各加 10px 内边距和 3px 边框：
>
> `300 + 10 + 10 + 3 + 3 = 326px`
>
> 加 `box-sizing: border-box` 后，边框盒保持 300px，内容区变成：
>
> `300 - 10 - 10 - 3 - 3 = 274px`
>
> 如果还有 `margin`，它不算在这两个宽度里，只影响盒子与其他元素的距离。

**第 3 题**：你给 `.compose` 加了 `background: yellow`，页面没变化。按什么顺序查？

> **答案**
>
> 一，Network 里 `styles.css` 是不是 200，Elements → Styles 里有没有这条规则；没有就是文件没加载或路径不对。
>
> 二，Console 里运行 `document.querySelectorAll(".compose").length`；返回 0 说明选择器没挑中元素。
>
> 三，Styles 面板里这条声明有没有被划掉；被划掉就看赢它的规则，算优先级和顺序，检查有没有 `!important`。
>
> 四，确认属性值合法、拼写正确，并且你检查的正是页面上那个元素。

## 从这一篇往外走 {#related}

- [HTML：页面的结构与语义](/learn/web-html)
- [Flex、Grid 与响应式布局](/learn/web-layout)
- [浏览器、前端与后端](/learn/web-client-server)
- [DOM 与事件：点击怎样变成行为](/learn/js-dom)

## 样式规则的参考来源 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
