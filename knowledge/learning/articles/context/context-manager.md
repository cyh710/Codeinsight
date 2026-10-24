# 上下文管理器：把进入与退出配对

## 先建立直觉 {#overview}

上下文管理器通过 with 把进入资源和退出清理配对。无论主体正常结束还是抛异常，都能按约定执行退出逻辑。它能管理文件、锁、连接或临时状态，但具体退出行为由对象决定，不能只看到 with 就认定事务已提交。

## 原理与执行过程 {#mechanism}

同步上下文协议包含 __enter__ 与 __exit__，异步协议对应 async with。contextlib 可以把带 yield 的函数转换为上下文管理器。退出时可能关闭资源、提交、回滚或恢复状态，是否抑制异常也由实现决定。理解一个 with 应继续追对象类型与退出方法。

## 跟着例子理解 {#example}

```python
from contextlib import contextmanager
@contextmanager
def resource():
    print("进入")
    try:
        yield "句柄"
    finally:
        print("清理")
with resource() as handle:
    print(handle)
```

## 一步一步读懂 {#walkthrough}

进入时执行到 yield，yield 的值交给 handle。主体结束后恢复生成器，finally 打印清理。若主体抛异常，退出路径仍有机会运行。contextlib.closing 的退出只负责 close；文件对象与数据库连接的 with 约定又可能不同。

## 常见误解 {#pitfalls}

关闭连接不等于提交事务。退出方法返回真值可能抑制异常，这需要有意设计。不能依靠垃圾回收时机替代及时清理。异步取消也需要考虑清理是否可执行及是否又会被取消。

## 工程中的取舍 {#tradeoffs}

with 减少重复 try/finally，但隐藏行为必须通过类型和 docstring 说清楚。过度包装会让锁和事务边界难看见。公开接口应明确资源由谁拥有、何时释放以及异常怎样传播。

## 接着探索 {#related}

- [异常与错误处理](/learn/python-exceptions)
- [文件锁：协调对共享文件的访问](/learn/file-lock)
- [数据库事务：一致完成状态转换](/learn/db-transaction)

## 来源与版本 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
