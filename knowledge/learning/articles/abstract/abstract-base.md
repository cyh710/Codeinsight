# 抽象基类与协议：约定可以替换的能力

## 先建立直觉 {#overview}

抽象基类定义子类应实现的能力，协议描述对象需要具备的结构。它们帮助上层依赖稳定接口，而不是绑定某个具体实现。例如，检索器只要求得到命中列表，就可以替换底层索引。接口还需要说明语义，不只是函数名字相同。

## 原理与执行过程 {#mechanism}

abc.ABC 与 abstractmethod 可以阻止不完整子类被正常实例化。typing.Protocol 常用于结构化静态检查，不要求显式继承。运行时协议检查的能力有限，不能验证参数与返回语义。行号、分数方向、错误行为和线程约束都应写进接口约定。

## 跟着例子理解 {#example}

```python
from abc import ABC, abstractmethod
class Searcher(ABC):
    @abstractmethod
    def search(self, query: str) -> list[str]:
        raise NotImplementedError
```

## 一步一步读懂 {#walkthrough}

Searcher 声明 search 必须由具体实现提供。它还没有说明列表是按什么顺序排序、无命中怎样表示，这些需要文档补齐。两个实现都返回 list[str]，仍可能在大小写、错误与排序上不兼容，替换测试需要验证这些不变量。

## 常见误解 {#pitfalls}

有抽象类不等于实现真的可替换。Protocol 不提供完整运行时输入验证。继承层次过深容易引入隐藏初始化与状态。接口中的类型注解也不能保证调用方遵守资源约束。

## 工程中的取舍 {#tradeoffs}

稳定接口降低替换成本，却增加维护抽象的工作。只有一个简单实现时，不必为每个小函数建立类层次。对语言解析、模型服务、存储和工具等真实变化边界，清楚的接口通常有长期收益。

## 接着探索 {#related}

- [依赖注入：把需要的能力交进来](/learn/dependency-injection)
- [类型注解：把接口约定写出来](/learn/python-annotations)

## 来源与版本 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
