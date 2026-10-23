# Flex、Grid 与响应式布局

## 先建立直觉 {#overview}

布局决定内容区域怎样排列。Flex 主要解决一条轴上的分配与对齐，Grid 擅长同时组织行和列。响应式布局根据可用空间调整呈现，目标是保持内容可用，而不是让所有屏幕都显示完全相同的像素位置。

## 原理与执行过程 {#mechanism}

Flex 容器有主轴和交叉轴，方向改变后对齐含义也会改变。Grid 通过轨道定义空间；minmax 和 fr 能表达最小需求与剩余空间。嵌套布局时，子项默认最小尺寸可能阻止收缩，因此代码面板常需要 min-width:0 或 min-height:0。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```css
.workbench {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 360px;
  height: 100dvh;
}
.chat, .reader { min-width: 0; overflow: auto; }
```

## 一步一步读懂 {#walkthrough}

左栏和右栏给出示例宽度，中间栏分配剩余空间。minmax(0,1fr) 允许中间轨道在内容很长时仍然缩小。每个阅读区域独立滚动，避免长代码撑破整个页面。窗口很窄时还应有明确的折叠或切换策略，本段代码本身没有提供该策略。

## 常见误解 {#pitfalls}

overflow:auto 不会自动建立正确的可滚动高度，祖先布局也需要约束。固定定位和绝对定位可能脱离正常文档流。把窄屏问题都交给横向滚动，会让对话与阅读都难使用。响应式变化还应保留焦点和用户阅读位置。

## 工程中的取舍 {#tradeoffs}

Flex 与 Grid 可以组合使用，选择依据是内容关系。三栏适合并行比较对话和证据，但小窗口要权衡可读宽度。布局修改应验证短文、长文、超长标识符和代码块，避免只在理想数据下看起来正常。

## 接着探索 {#related}

- [CSS 选择器、层叠与盒模型](/learn/web-css)
- [React 组件与 JSX](/learn/react-components)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [MDN Web Docs：学习 Web 开发](https://developer.mozilla.org/zh-CN/docs/Learn_web_development)；作者：Mozilla Contributors；CC-BY-SA-4.0。版本：MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）; sha256:cf8584055bc8796da9416318ec93ce74a86ce8379fa6bb8a2839dde1c465507c。
