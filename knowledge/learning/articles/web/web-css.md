# CSS 选择器、层叠与盒模型

## 先建立直觉 {#overview}

CSS 规定页面内容怎样呈现。选择器决定规则作用于哪些元素，层叠决定多条规则冲突时采用哪一条，盒模型描述内容、内边距、边框与外边距怎样占据空间。看到宽度异常时，应先检查这些层次，而不是不断修改像素。

## 原理与执行过程 {#mechanism}

一条规则由选择器与声明组成。声明冲突会受到来源、重要性、层叠层、选择器优先级和顺序影响，不能只记住“最后写的赢”。默认 content-box 下 width 通常只指定内容宽度；border-box 把内边距和边框计入指定宽度。外边距不包含在 border-box 的宽度内。

## 跟着例子理解 {#example}

```css
.card {
  box-sizing: border-box;
  width: 300px;
  padding: 16px;
  border: 1px solid #888;
}
.card strong { color: #245; }
```

## 一步一步读懂 {#walkthrough}

card 的外侧边框宽度是 300px，内部空间要扣除左右 padding 和边框。后面的选择器只匹配 card 内的 strong 元素。若把 box-sizing 改为 content-box，最终占据的边框盒宽度会变大。浏览器开发工具中的计算样式与盒模型能展示最终结果，帮助区分源码规则与实际生效规则。

## 常见误解 {#pitfalls}

增加 !important 往往会把局部问题变成下一次更难覆盖的规则。父元素颜色可能继承，但宽度一般不是按相同规则继承。元素被隐藏、透明或被遮挡是不同情况。固定高度可能让长文在不同字体或窗口宽度下溢出。

## 工程中的取舍 {#tradeoffs}

统一设计变量和有限的组件样式能降低重复维护。精确像素适合某些边界，弹性尺寸更适合不同窗口。教材长文需要考虑行宽、换行和代码块溢出；“能显示”与“容易阅读”应分别检查。

## 接着探索 {#related}

- [HTML：页面的结构与语义](/learn/web-html)
- [Flex、Grid 与响应式布局](/learn/web-layout)

## 来源与版本 {#sources}

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
