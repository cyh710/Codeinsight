# 文件、路径与资源生命周期

## 先建立直觉 {#overview}

文件把数据保存在程序进程之外，路径告诉操作系统去哪里找它。相对路径依赖当前工作目录，绝对路径指向明确位置。路径对象本身只是位置描述，不代表文件存在，也不代表当前程序有权读取。

## 原理与执行过程 {#mechanism}

打开文件会获得需要关闭的资源。文本模式负责按照编码把字节转换成字符串，二进制模式直接处理字节。写入时应考虑是覆盖、追加还是先写临时文件后替换。pathlib 帮助组合跨平台路径，但不能替代访问范围检查和业务授权。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
from pathlib import Path

path = Path("notes") / "hello.txt"
path.parent.mkdir(exist_ok=True)
path.write_text("你好", encoding="utf-8")
with path.open(encoding="utf-8") as stream:
    text = stream.read()
print(text)
```

## 一步一步读懂 {#walkthrough}

路径拼接表达目录关系。mkdir 建立父目录；write_text 把字符串编码后写入。with 打开文件，离开代码块时关闭句柄。换一个启动目录，这里的相对路径可能指向另一个 notes。复现工程问题时，应同时记录文件路径与工作目录，不要只记录文件名。

## 常见误解 {#pitfalls}

默认编码可能随系统变化；读写中文应明确编码。先检查 exists 再打开并不能消除并发变化，文件可能在两步之间消失。把用户输入直接拼成路径可能越过允许目录，需要在服务端解析后验证。关闭文件只释放资源，不等于完成数据库事务提交。

## 工程中的取舍 {#tradeoffs}

一次读完整文件简单，但大文件应考虑流式处理。临时文件加原子替换可以避免读者看到写到一半的文件，但原子替换和掉电持久性也不是同一保证。保存重要状态还需要确定备份、校验和失败恢复策略。

## 接着探索 {#related}

- [异常与错误处理](/learn/python-exceptions)
- [上下文管理器：把进入与退出配对](/learn/context-manager)
- [文件锁：协调对共享文件的访问](/learn/file-lock)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
