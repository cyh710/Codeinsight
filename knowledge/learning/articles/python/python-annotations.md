# 类型注解：把接口约定写出来

## 先建立直觉 {#overview}

类型注解说明函数期望接收和返回什么数据，帮助读者、编辑器和静态检查工具发现不一致。Python 注解通常不会自动限制运行时传入的对象，所以它是接口表达的一部分，不是输入校验的替代品。

## 原理与执行过程 {#mechanism}

参数后的冒号描述输入类型，箭头后的注解描述返回类型。list[str] 表达元素类型；str | None 表示可能没有字符串。静态工具分析可能的执行路径，运行时仍按照实际对象操作。类型协议可以描述对象需要具备的行为，而不要求继承同一个具体类。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
def find_name(user_id: int, names: dict[int, str]) -> str | None:
    return names.get(user_id)

name = find_name(7, {7: "小林"})
if name is not None:
    print(name.upper())
```

## 一步一步读懂 {#walkthrough}

find_name 的接口告诉读者：用整数键查名字，但可能查不到。调用方通过 is not None 排除空值，后续再调用字符串方法。这个检查在业务上也必要，而不是仅为满足工具。若外部 JSON 把 user_id 传成字符串，仍需转换或拒绝，注解本身不会自动完成这一步。

## 常见误解 {#pitfalls}

Any 会弱化静态检查，不应为消除报错而到处使用。类型断言或 cast 通常不转换数据。把所有返回都写成 str，却在失败路径返回 None，会同时误导读者和工具。不同 Python 版本支持的注解语法与求值方式可能不同。

## 工程中的取舍 {#tradeoffs}

清楚的公开接口值得写完整注解，复杂内部泛型应权衡阅读成本。类型检查擅长发现形状和调用不一致，测试擅长验证业务行为，两者互补。动态边界仍需要运行时校验；不能把“类型检查通过”当作网络输入或数据库内容一定正确的证明。

## 接着探索 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [列表、元组、字典与集合](/learn/python-containers)
- [TypeScript 的类型注解与推断](/learn/ts-types)
- [抽象基类与协议：约定可以替换的能力](/learn/abstract-base)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
