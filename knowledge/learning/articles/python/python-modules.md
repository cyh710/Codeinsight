# 模块、包与导入

## 先建立直觉 {#overview}

模块通常是一份可以导入的 Python 代码，包把多个模块组织在一个命名空间下。导入让一个文件使用另一个文件提供的函数或类，而不必复制实现。读工程时，导入关系能帮助你理解模块边界，但它不等于实际的业务调用链。

## 原理与执行过程 {#mechanism}

import 会寻找模块、在需要时执行其顶层代码，并把模块或对象绑定到当前作用域。已加载模块通常通过 sys.modules 复用，因此反复导入并不等于反复执行顶层逻辑。绝对导入从完整路径定位，相对导入依赖当前包。启动方式、工作目录与环境中的搜索路径会影响能否找到模块。

## 跟着例子理解 {#example}

```python
# prices.py
def total(price, count):
    return price * count

# app.py
from prices import total
print(total(12, 3))
```

## 一步一步读懂 {#walkthrough}

运行 app.py 时，解释器先定位 prices，再取得 total 这个对象。真正的乘法发生在 total(12,3) 调用时。from 并不是把函数正文粘贴到当前文件。可以把 prices 当成提供接口的模块，把 app 当成使用接口的调用方。若两个模块互相在顶层导入并立即访问尚未建立的对象，就可能出现循环导入问题。

## 常见误解 {#pitfalls}

本地文件命名为 json.py、typing.py 可能遮蔽标准库。相对导入失败不一定是文件不存在，也可能是把包内文件按错误方式直接运行。不要为了临时修复导入而到处修改 sys.path，这会让测试和部署依赖隐藏环境。

## 工程中的取舍 {#tradeoffs}

稳定的模块接口减少跨目录修改。顶层导入便于发现依赖，按需导入可以减少启动成本或打破局部循环，但会推迟失败。项目中应尽量让底层模块不依赖上层界面，避免为了复用一个小函数而引入整套应用启动副作用。

## 接着探索 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [程序怎样执行：从源文件到结果](/learn/python-execution)
- [类、对象与继承](/learn/python-classes)

## 来源与版本 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
