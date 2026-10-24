# 条件与循环：程序怎样选择下一步

## 先建立直觉 {#overview}

条件让程序根据数据选择路径，循环让同一段处理作用于多个值或反复执行。代码从上往下写，不意味着每一行都会执行；判断条件、提前返回和异常都可能改变流程。读业务代码时，先识别这些分支和退出点，再理解具体计算。

## 原理与执行过程 {#mechanism}

if 计算表达式的真值并选择分支；for 从可迭代对象依次取值；while 在每轮开始时检查条件。break 结束最近一层循环，continue 跳过本轮剩余语句。循环的 else 在循环没有被 break 中断时执行，不能把它当作 if 的 else。处理资源时，循环内的异常和提前退出都要考虑清理。

## 跟着例子理解 {#example}

```python
prices = [12, 35, 89]
total = 0
for price in prices:
    if price >= 50:
        continue
    total += price
print(total)  # 47
```

## 一步一步读懂 {#walkthrough}

第一次取出 12，条件不成立，所以加到 total。第二次取出 35，同样累加。第三次取出 89，进入 continue，跳过累加。所有元素处理完后输出 47。若把 continue 改成 break，就会停止扫描后续商品；如果后面还有一个便宜商品，它也不会再被处理。两者表达的是不同业务规则。

## 常见误解 {#pitfalls}

range 的结束值不包含在结果里，容易出现少处理一项的问题。不要边遍历列表边随意删除元素，这会改变索引对应关系。while 条件不变可能造成无限循环；网络重试除了次数，还需要时间上限和退出条件。空列表为假，不等于它和 None 在业务含义上总能互换。

## 工程中的取舍 {#tradeoffs}

直白的循环通常最易调试；列表推导式适合简单转换，不适合把复杂分支塞进一行。早返回可以减少嵌套，但要保证资源与状态的收尾。阅读流程时，可以用一组很小的输入手算各轮状态，并加入空输入、边界值和提前退出的情形。

## 接着探索 {#related}

- [变量、值与类型](/learn/python-values)
- [函数、参数与返回值](/learn/python-functions)
- [列表、元组、字典与集合](/learn/python-containers)

## 来源与版本 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
