# 异常与错误处理

## 先建立直觉 {#overview}

异常是程序无法按当前路径继续时发出的信号，例如文件不存在或字符串不能转成数字。处理异常的目标不是让程序永远不报错，而是让可恢复的问题得到处理、不可恢复的问题保留清楚的原因，并确保资源得到清理。

## 原理与执行过程 {#mechanism}

异常会沿调用栈向外传播，直到找到匹配的 except。finally 适合放必须执行的清理，else 表示 try 正常结束后的分支。业务失败、空结果和程序缺陷不应一律混成 None。重新抛异常时可以保留原始原因，便于定位真正失败的位置。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
def parse_count(text):
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("数量必须是整数") from exc
    if value < 0:
        raise ValueError("数量不能为负")
    return value
```

## 一步一步读懂 {#walkthrough}

输入“3”时 int 成功并返回 3。输入“三”时进入 except，得到面向用户的错误，同时 from exc 保留原始转换原因。输入“-2”虽然语法上可转成整数，却不满足业务约束，所以由另一个判断拒绝。技术合法与业务合法是两个不同层次。

## 常见误解 {#pitfalls}

裸 except 可能连退出和取消信号都吞掉。捕获所有异常后返回空列表，会让调用方无法区分“没有数据”和“读取失败”。finally 中 return 还可能覆盖先前异常。错误消息不要泄露密钥、完整请求或不必要的私密数据。

## 工程中的取舍 {#tradeoffs}

底层应提供足够诊断信息，界面层再转换成用户能理解的说明。重试只适合可能恢复的失败，并应有边界；参数错误通常不该重试。对 Agent 工具，失败需要成为模型可见的结构化结果，而不是让整轮崩溃或假装成功。

## 接着探索 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [上下文管理器：把进入与退出配对](/learn/context-manager)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
