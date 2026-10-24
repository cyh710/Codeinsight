# 线程池：受控执行阻塞工作

## 先建立直觉 {#overview}

线程池维护一组可复用工作线程，让调用方提交任务并获取未来结果。它常用于把阻塞文件、数据库或第三方库操作移出异步事件循环。线程池提供执行资源，不自动保证被调用对象线程安全。

## 原理与执行过程 {#mechanism}

提交任务得到 Future，工作线程执行函数，结果或异常由调用方取得。最大工作线程数限制同时执行规模，排队任务还需要容量控制。Python 的线程对等待型工作很有用，但受解释器与扩展实现影响，不能保证纯 Python CPU 计算按线程数线性加速。

## 跟着例子理解 {#example}

```python
from concurrent.futures import ThreadPoolExecutor
def square(value):
    return value * value
with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(square, [1, 2, 3]))
print(results)
```

## 一步一步读懂 {#walkthrough}

线程池最多使用两个工作线程处理这些任务，map 按输入顺序提供结果。square 太轻，示例只说明接口，不构成性能收益证据。真实阻塞操作应在工作线程内部建立有线程约束的资源，例如保持 check_same_thread 的 SQLite 连接。

## 常见误解 {#pitfalls}

把同一连接交给多个线程可能违反资源约束。Future 取消通常不能强行停止已经执行的线程函数。线程数过多会增加切换和下游压力。异步函数不能不加区分地作为普通同步工作提交。

## 工程中的取舍 {#tradeoffs}

受控池比每次新开线程更容易管理。任务队列、等待上限和关闭策略同样重要。对 CPU 密集任务可评估进程或专用扩展，决策应来自测量而不是仅凭“并发”这个词。

## 接着探索 {#related}

- [异步编程：等待期间让出执行机会](/learn/async)
- [文件锁：协调对共享文件的访问](/learn/file-lock)

## 来源与版本 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
