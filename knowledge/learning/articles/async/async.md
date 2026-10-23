# 异步编程：等待期间让出执行机会

## 先建立直觉 {#overview}

异步编程让程序在等待 I/O 时处理其他工作。Python 中 async def 定义协程函数，await 在合适位置等待结果并让出执行机会。它适合大量等待型任务，不会自动把 CPU 密集工作变成并行计算。

## 原理与执行过程 {#mechanism}

事件循环调度协程。协程应在可等待的操作处配合调度，阻塞的同步调用可能卡住整个循环。取消需要沿任务传播并执行清理。并发发起多个请求与串行等待之间存在吞吐、资源和失败策略的取舍。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
import asyncio
async def greet(name):
    await asyncio.sleep(0.01)
    return f"你好，{name}"
async def main():
    values = await asyncio.gather(greet("甲"), greet("乙"))
    print(values)
asyncio.run(main())
```

## 一步一步读懂 {#walkthrough}

调用 greet 先得到协程对象，gather 让两个工作并发推进。sleep 在等待时让出执行机会，最终 main 收到两个结果。示例没有真正网络请求，只演示调度。把 sleep 改成同步 time.sleep，会阻塞当前线程，从而改变并发表现。

## 常见误解 {#pitfalls}

async 关键字不保证函数内部没有阻塞。创建任务后不保存或等待，可能让异常和生命周期失控。取消一个等待者不一定取消外部系统已经执行的动作。共享可变状态仍然可能在 await 边界产生竞争。

## 工程中的取舍 {#tradeoffs}

异步适合网络和流式服务，线程更适合某些阻塞库，进程可用于部分 CPU 工作。选择依据应是实际等待与计算比例。项目应跟踪后台任务、超时、取消和关闭流程，避免用户离开页面就丢失任务归属。

## 接着探索 {#related}

- [Promise 与 async/await](/learn/js-async)
- [线程池：受控执行阻塞工作](/learn/thread-pool)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
