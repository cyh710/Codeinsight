# 生成器：按需产生一串值

## 先建立直觉 {#overview}

生成器通过 yield 逐步产生值，让调用方需要一项时再继续计算。它适合处理大数据流或分阶段遍历，不必先构造完整列表。函数暂停时仍保留局部状态，因此也有资源生命周期需要管理。

## 原理与执行过程 {#mechanism}

含 yield 的函数被调用时返回生成器对象。每次迭代运行到下一个 yield，结束时表示没有更多项。yield from 可以委托另一个可迭代对象。一次性迭代器消费后通常不能自动从头再来，重复遍历可能需要重新创建。

## 跟着例子理解 {#example}

```python
def squares(limit):
    for value in range(limit):
        yield value * value
values = squares(3)
print(next(values))  # 0
print(list(values))  # [1, 4]
```

## 一步一步读懂 {#walkthrough}

创建 values 时没有生成完整列表。next 执行到第一次 yield，得到 0。list 继续消费剩余项，所以结果没有再次包含 0。这个例子可以帮助理解流式读取：看到第一项不代表所有处理已经完成。

## 常见误解 {#pitfalls}

生成器对象存在不代表函数体已全部执行。中途停止迭代时，内部资源可能需要显式关闭或由外层上下文管理。把生成器转换成列表会重新承担完整内存成本。异常可能在后续消费时才出现。

## 工程中的取舍 {#tradeoffs}

按需计算降低峰值内存并改善首项延迟，但错误时机与重复读取更复杂。需要随机访问或多次遍历时，列表可能更简单。对流式 API，应明确结束、取消和失败事件，而不能把“已经开始流”当作“成功完成”。

## 接着探索 {#related}

- [上下文管理器：把进入与退出配对](/learn/context-manager)
- [异步编程：等待期间让出执行机会](/learn/async)
- [列表、元组、字典与集合](/learn/python-containers)

## 来源与版本 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
