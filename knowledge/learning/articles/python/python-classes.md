# 类、对象与继承

## 先建立直觉 {#overview}

类描述一类对象拥有的数据与行为，对象是某一次具体实例。例如，Cart 类规定购物车如何添加商品，而小林的购物车和小李的购物车是两个对象，各自保存自己的商品。理解类时，先分清实例数据与共享的类数据。

## 原理与执行过程 {#mechanism}

调用类通常会创建实例并进行初始化。普通实例方法通过 self 访问当前对象；self 是惯例名字，不是另一个隐藏对象。实例属性经常在 __init__ 中建立。继承让子类沿方法解析顺序复用或覆盖行为，但不自动保证子类符合父类的业务约定。组合则通过保存另一个对象来使用其能力。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
class Cart:
    def __init__(self):
        self.items = []

    def add(self, name):
        self.items.append(name)

first = Cart()
second = Cart()
first.add("书")
print(second.items)  # []
```

## 一步一步读懂 {#walkthrough}

两次 Cart() 分别创建实例。__init__ 每次创建新的列表，因此 first.add 修改的不是 second.items。调用 first.add 时，first 会作为 self 传入。若把 items=[] 写到类体而不是初始化中，两个实例可能看到同一个共享列表，行为就会不同。读项目时应追实例在哪里创建、依赖如何传入以及哪些属性会被修改。

## 常见误解 {#pitfalls}

继承不是复制父类代码；改动父类可能影响所有子类。类属性与实例属性同名时的查找需要特别留意。使用 isinstance 进行分支并不总比定义统一接口更好。类很多不意味着结构清晰，只有数据与职责边界合理才会降低复杂度。

## 工程中的取舍 {#tradeoffs}

对象把状态和行为放在一起，适合需要持续维护状态的模块；简单数据转换可能一个函数就足够。继承层次过深会增加隐含约束，组合通常更便于替换依赖。先找对象生命周期和数据不变量，再决定是否需要基类、接口或依赖注入。

## 接着探索 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [抽象基类与协议：约定可以替换的能力](/learn/abstract-base)
- [依赖注入：把需要的能力交进来](/learn/dependency-injection)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
