# 装饰器：在定义时包装行为

## 先建立直觉 {#overview}

装饰器在函数或类定义时接收对象，再返回替代或增强后的对象。它常用于注册路由、缓存、日志和权限检查。表面的 @ 很短，背后可能改变调用行为；读代码时要知道包装发生在何时、实际调用的是哪个对象。

## 原理与执行过程 {#mechanism}

@decorate 放在 def 上方大致相当于定义后执行 f=decorate(f)。多个装饰器按嵌套顺序组合。带参数的装饰器通常先调用工厂得到装饰器。functools.wraps 有助于保留名称等元数据，但并不会自动保证包装函数与原函数在所有语义上相同。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
from functools import wraps
def traced(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        print(function.__name__)
        return function(*args, **kwargs)
    return wrapper
@traced
def add(a, b): return a + b
```

## 一步一步读懂 {#walkthrough}

定义 add 时 traced 已运行，add 绑定到 wrapper。以后调用 add 才打印原函数名并转交参数。wrapper 返回原调用结果，否则调用方可能得到 None。若原函数是协程，包装层还需要正确处理 await，不能只复制同步样例。

## 常见误解 {#pitfalls}

装饰器不是每次调用前重新定义。注册型装饰器可能主要在定义时产生副作用。多个权限或缓存装饰器的顺序会影响行为。静态工具看到装饰器名，也不能自动确认所有运行时包装结果。

## 工程中的取舍 {#tradeoffs}

横切逻辑集中可减少重复，但过多包装会隐藏控制流。对重要权限和事务，应保持约定可见并验证顺序。组合、显式调用和中间件也可能更清楚，选择应基于调用边界。

## 接着探索 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [延迟初始化与缓存工厂](/learn/singleton-lazy)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
