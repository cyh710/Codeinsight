# 列表、元组、字典与集合

## 先建立直觉 {#overview}

容器把多个值组织起来。列表按顺序保存元素，元组保存一组通常不改变的结构，字典把键映射到值，集合保存不重复的成员。选哪种容器，取决于你要按顺序遍历、按键查找，还是判断某个值是否存在。

## 原理与执行过程 {#mechanism}

列表和元组用位置索引，字典与集合依赖哈希来定位键或成员。字典键与集合成员必须可哈希；可变列表通常不能作为键。字典保留插入顺序，但按键查找和按位置访问仍是不同操作。列表 append 修改原对象；sorted 返回新列表；list.sort 原地排序并返回 None。

## 跟着例子理解 {#example}

以下是独立教学示例，不代表被分析项目的实际代码。

```python
products = {"pen": 35, "book": 12}
selected = ["book", "pen", "book"]
unique_ids = set(selected)
total = sum(products[item] for item in selected)
print(total)  # 59
```

## 一步一步读懂 {#walkthrough}

products 用商品 ID 查价格。selected 保留购买顺序并允许重复；购买两本书时不能先去重。unique_ids 只适合回答“涉及哪些商品”，不能直接代替购物明细。sum 逐个读取 selected，得到 12+35+12。这个例子显示同一份业务数据可以有不同投影，但每种投影保留的信息不同。

## 常见误解 {#pitfalls}

空字典写 {}，空集合写 set()。字典中缺键可能抛 KeyError，应根据业务选择 get、默认值或明确报错。不能把不重复当作天然正确：日志、队列、购物记录中的重复有时正是要保留的信息。浅复制也不会递归复制内部对象。

## 工程中的取舍 {#tradeoffs}

用字典建立查找表能避免反复扫描列表，但需要额外内存和同步维护。集合适合成员检测，不适合依赖遍历顺序的协议。选择容器时先写出不变量，例如“允许重复且顺序重要”，再比较实现，避免仅因某种结构看起来高级就采用它。

## 接着探索 {#related}

- [变量、值与类型](/learn/python-values)
- [条件与循环：程序怎样选择下一步](/learn/python-control-flow)
- [函数、参数与返回值](/learn/python-functions)

## 来源与版本 {#sources}

本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。不把原文示例描述为用户项目事实。借鉴、翻译及改编部分保留相应来源许可；含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
