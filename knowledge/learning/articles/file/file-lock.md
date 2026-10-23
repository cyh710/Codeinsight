# 文件锁：协调对共享文件的访问

## 先建立直觉 {#overview}

文件锁用于协调可能同时访问某个共享资源的参与者，常见于多进程写文件或本地缓存。锁只有在所有相关写入方遵守同一协议时才有效。它与 Python 线程锁、数据库事务解决的范围不同。

## 原理与执行过程 {#mechanism}

调用方取得锁后进入临界区，完成后释放。等待超时避免无限卡住。锁文件的存在与操作系统锁是否仍被持有不一定相同，具体行为取决于库和平台。进程崩溃、网络文件系统和可重入需求都影响选择。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
from filelock import FileLock
from pathlib import Path
with FileLock("report.lock", timeout=5):
    Path("report.txt").write_text("完成", encoding="utf-8")
```

## 一步一步读懂 {#walkthrough}

FileLock 在进入代码块前尝试取得约定锁，写入完成或异常离开时释放。其他写者也必须使用同一锁路径，否则不会受到保护。相对锁路径依赖工作目录，所以不同进程应约定稳定位置。示例只说明协调，不包含完整原子写入与备份策略。

## 常见误解 {#pitfalls}

锁文件还在不代表锁一定被占用。持锁时等待网络或模型会扩大阻塞。不同锁与资源取得顺序不一致可能死锁。文件锁不会自动把多次数据库写入变成一个事务。

## 工程中的取舍 {#tradeoffs}

文件锁适合本地跨进程协调，数据库事务更适合数据库内部一致性，分布式锁还涉及租约与失效。优先缩小临界区，明确超时与失败提示。不要在没有平台验证时宣称跨所有文件系统可靠。

## 接着探索 {#related}

- [文件、路径与资源生命周期](/learn/python-files)
- [数据库事务：一致完成状态转换](/learn/db-transaction)
- [上下文管理器：把进入与退出配对](/learn/context-manager)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [filelock tutorial](https://py-filelock.readthedocs.io/en/latest/)；作者：filelock contributors；Unlicense。版本：导入日网页快照; sha256:d35da14ac06904caaf1f1252d8281a3170ff79919e609ffe79cf3c228c12d541。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
