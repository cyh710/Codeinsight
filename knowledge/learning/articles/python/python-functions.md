# 函数、参数与返回值

## 先建立直觉 {#overview}

函数是一段可以命名、重复调用的处理过程。参数让调用者提供输入，返回值让函数把结果交还给调用者。例如，计算价格的函数接收单价和数量，返回总价；调用者不必每次重写乘法，也更容易单独检查价格规则。

## 原理与执行过程 {#mechanism}

阅读函数可以先问三件事：它接收什么，做了什么，交回什么。def 定义函数；调用表达式让运行时把实参与形参绑定，然后执行函数体。位置参数按顺序对应，关键字参数按名字对应。return 结束当前函数并返回对象，没有显式 return 的路径会返回 None。参数绑定遵循名字与对象的规则：给形参重新赋值不改变调用方名字，但原地修改传入列表会被调用方看见。

函数还可能有副作用，例如打印、写文件或修改数据库。返回值描述数据如何交回，副作用描述外部状态如何改变；这两个维度应分开看。名字叫 save 的函数不一定真的成功保存，名字叫 get 的函数也可能顺便更新缓存，最终仍要读实现与返回约定。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
def calculate_total(price, quantity=1):
    total = price * quantity
    return total

amount = calculate_total(12, quantity=3)
print(amount)  # 36
```

## 一步一步读懂 {#walkthrough}

第一步，def 建立 calculate_total，函数体此时没有计算。第二步，调用传入 price=12 和 quantity=3；如果不传数量，它使用定义时给出的默认值 1。第三步，函数局部变量 total 得到 36。第四步，return 把这个整数交回调用处，amount 接住结果。最后 print 才负责显示；即使去掉 print，计算和返回仍会发生。

试着把 return total 改成 print(total)：屏幕仍会出现 36，但 amount 会得到 None。这是理解“显示结果”和“返回结果”差异的直接方法。再试两个调用，一个用关键字数量，一个省略数量，观察输入如何决定输出。教学例子只演示参数绑定，真实金额计算还需要确定舍入、币种和输入校验。

## 常见误解 {#pitfalls}

print 不是 return。函数内部的局部变量不能随意在外面读取。默认列表如 items=[] 会在不同调用间共享，应按需求在函数内创建新列表。带 async def 的函数被调用时通常得到协程对象，并不会像普通同步函数一样立即完成主体。遇到 *args、**kwargs 时，先理解参数打包，再追到实际调用方，不必因为签名较长就放弃阅读。

## 工程中的取舍 {#tradeoffs}

小而职责清楚的函数便于复用和测试，但过度拆分会让读者不断跳转。纯计算尽量用返回值表达结果，外部副作用清楚写进约定。工程中还应约定输入类型、异常、空结果以及是否修改参数。想理解项目里的函数，可以从一个调用位置开始，记下实参，再追它的返回值被谁使用；不必先读懂整个仓库。

## 接着探索 {#related}

- [变量、值与类型](/learn/python-values)
- [模块、包与导入](/learn/python-modules)
- [类型注解：把接口约定写出来](/learn/python-annotations)
- [JavaScript 函数、作用域与闭包](/learn/js-functions)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
