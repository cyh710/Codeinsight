# 模块、包与导入

## 两个文件怎么共用一个函数 {#overview}

学完这一篇，你能把代码拆成几个文件，用 import 正确接起来，并看懂模块入口、包和循环导入报错。

小林先写了一个 `pricing.py`，里面有算总价的函数。第二天要写打印小票的 `cli.py`，他把函数复制了一份。第三天改税率，只改了一边，小票上的数字就和网页对不上了。

复制代码的问题不是麻烦，是**两份会分头变**。导入让第二个文件直接用第一个文件里的函数，只有一份实现。

这一篇从一个 `shop/` 目录开始，先跑通，再拆开看 import 到底做了什么。

## 搭出 shop 目录跑一遍 {#shop-layout}

在任意一个空目录里，建出这样的结构：

```
shop/
├── __init__.py
├── pricing.py
└── cli.py
```

`shop/pricing.py`：

```python
print("pricing 模块被执行了")


def total(price, count):
    return price * count


def with_tax(amount, rate=0.1):
    return round(amount * (1 + rate), 2)
```

`shop/cli.py`：

```python
from shop.pricing import total, with_tax

if __name__ == "__main__":
    print(total(12, 3))
    print(with_tax(total(12, 3)))
```

`shop/__init__.py`：

```python
from .pricing import total

print("shop 包加载完成")
```

在 **`shop/` 的上一级目录**运行：

```bash
python -m shop.cli
```

你应该看到：

```
pricing 模块被执行了
shop 包加载完成
36
39.6
```

四行输出，顺序值得留意。`pricing 模块被执行了` 最先出现，`shop 包加载完成` 第二，两个数字最后才出来。

原因在 `-m` 的启动方式：Python 先导入 `shop` 这个包，因此执行 `__init__.py`；`__init__.py` 的第一行又导入了 `.pricing`，于是 `pricing.py` 的顶层 `print` 先跑。等包初始化完，才轮到 `cli` 作为主程序执行，打印 36 和 39.6。

后面几节会把这条链拆开。

## 一行 import 到底执行了什么 {#import-execution}

先离开 `shop/`，在一个新目录建两个文件。

`counter.py`：

```python
print("counter 顶层代码执行")

count = 0


def bump():
    global count
    count += 1
```

`app.py`：

```python
import counter
import counter
from counter import count

print("count 是", count)
counter.bump()
print("count 还是", count)
print("模块里的 count 是", counter.count)
```

运行 `python app.py`，输出：

```
counter 顶层代码执行
count 是 0
count 还是 0
模块里的 count 是 1
```

文件里写了两次 `import counter`，`counter 顶层代码执行` 只出现一次。

**第一次 `import counter`：**

1. 在 `sys.modules` 里找有没有叫 `counter` 的模块。
2. 没找到，就去文件系统里找 `counter.py`。
3. 从头执行这个文件的顶层代码：打印、把 0 赋给 `count`、定义 `bump`。
4. 把这个模块对象登记进 `sys.modules`，并在 `app.py` 里绑定名字 `counter`。

**第二次 `import counter`：** 在 `sys.modules` 里找到了，直接用，不再执行顶层代码。

**`from counter import count`：** 先确保 `counter` 已加载，然后从模块里取出 `count` 当前指向的对象，绑定到 `app.py` 的名字 `count`。这里取出的是整数 0。

接下来 `counter.bump()` 执行 `global count; count += 1`。它改的是**模块对象上的属性** `counter.count`，所以最后一行打印 1。

但 `app.py` 里的 `count` 仍然指向 0。`from ... import` 在导入那一刻就把名字绑好了，之后模块里把 `count` 重新指向新整数，本地这个名字不会跟着换。

这和函数参数那条规律一样：**重新绑定名字看不见，原地修改对象才看得见。** 如果 `count` 是一个列表，模块里原地 append，你的本地名字也会看到变化；但模块里写 `count = [...]` 新列表，本地拿到的还是旧的。

`import` 不是把源代码粘贴到当前文件。它执行一次、留下一个模块对象，之后大家共享这个对象。

顶层代码里有 `print`，所以一导入就看得见。真实项目里，读配置、连数据库、发请求如果写在顶层，也会在 import 时执行。这是导入的副作用，也是为什么主逻辑常放进函数并加一个入口判断。

## 脚本、包，以及 -m 运行 {#script-or-package}

回到 `shop/`。对比两条命令。

第一条前面跑过：

```bash
python -m shop.cli
```

输出里有 36 和 39.6。

第二条：

```bash
python -c "import shop.cli"
```

输出只有：

```
pricing 模块被执行了
shop 包加载完成
```

`cli.py` 被导入了，`pricing.py` 和 `__init__.py` 的顶层代码都执行了，但两个数字没打印。因为 `cli.py` 里的打印写在：

```python
if __name__ == "__main__":
```

`__name__` 是每个模块自带的名字。用 `python -m shop.cli` 运行，`cli` 是主程序，`__name__` 是 `"__main__"`，条件成立。用 `import shop.cli` 导入，`__name__` 是 `"shop.cli"`，条件不成立，块里的代码跳过。

这个判断解决的是“同一个文件，既想能被导入，又想能单独运行”。导入时不该自动干活，直接运行时才干活。

`shop/` 是一个**包**：一个目录，里面有 `__init__.py`。导入包时，Python 先执行 `__init__.py`。这里的 `__init__.py` 用相对导入：

```python
from .pricing import total
```

开头的点表示“当前这个包”，所以它找的是 `shop.pricing`。写成 `from shop.pricing import total` 在这里也能跑，但把包改名就得多改几处；包内的相对导入不依赖包名。

`__init__.py` 常用来做三件事：初始化包级别的状态、从子模块里挑出对外的名字、给包写说明。这里的 `from .pricing import total` 就是让 `shop.total` 可以直接用。

`-m` 的意思是“把某个模块当主程序运行”。它会把当前目录放进搜索路径，然后找到 `shop.cli` 执行。少了 `-m`，直接写：

```bash
python shop/cli.py
```

会失败，最后一行是：

```
ModuleNotFoundError: No module named 'shop'
```

因为直接运行脚本时，Python 把**脚本所在的目录** `shop/` 放进搜索路径。`cli.py` 里写的是 `from shop.pricing import ...`，它要在 `shop/` 的上一级找 `shop`，但那一级不在路径里，于是找不到。这个错误和文件不存在无关，是“从哪里开始找”的问题。

## 循环导入为什么会炸 {#circular-import}

再建一个目录 `loop/`：

```
loop/
├── main.py
├── a.py
└── b.py
```

`a.py`：

```python
from b import b_name

a_name = "A"


def hello():
    return f"{a_name} 认识 {b_name}"
```

`b.py`：

```python
from a import a_name

b_name = "B"
```

`main.py`：

```python
import a

print(a.hello())
```

运行 `python main.py`，终端最后会停在这一句（解释器附加的重名提示随版本和路径变化，这里略去）：

```
ImportError: cannot import name 'a_name' from 'a'
```

把过程按时间排一遍：

1. `main.py` 导入 `a`，`a.py` 开始执行。
2. `a.py` 第一行导入 `b`，`b.py` 开始执行。
3. `b.py` 第一行要从 `a` 里拿 `a_name`。
4. 但 `a.py` 还停在第一行，`a_name = "A"` 根本还没执行到。
5. `a` 确实在 `sys.modules` 里，所以报的不是“找不到模块”，而是“模块找到了，里面没有这个名字”。

`a` 是一个只建了一半的模块。循环导入的错误大多长这样：不是文件不存在，是**你要的名字还没来得及出现**。

一种修法是两边都只导入模块，等真正用到时再取属性：

`a.py`：

```python
import b

a_name = "A"


def hello():
    return f"{a_name} 认识 {b.name}"
```

`b.py`：

```python
import a

name = "B"
```

`main.py` 不变。再运行 `python main.py`：

```
A 认识 B
```

这次 `b.py` 的 `import a` 拿到的仍是半成品 `a`，但它只把模块对象绑到名字上，没有立刻访问 `a.a_name`。等 `main.py` 调用 `a.hello()` 时，两个模块都已经执行完，`b.name` 才被取出来。

关键在于**访问属性的时机**。如果 `b.py` 在顶层写 `print(a.a_name)`，就算改成 `import a` 也照样炸。

另外两种修法：

- 把两边都要用的东西挪到第三个模块 `common.py`，让 `a` 和 `b` 都只依赖 `common`，依赖变成单向的。
- 把其中一个 import 移进函数，等调用时再导入。

第二种能让报错消失，但依赖被藏进了函数体，问题会推迟到运行时才暴露。先试着把依赖关系理顺，实在理不顺再用它。

## 导入关系不是调用关系 {#import-vs-call}

`cli.py` 里只有一行导入，从 `pricing` 拿了两个名字：

```python
from shop.pricing import total, with_tax
```

但运行时，`total` 被调用了两次，`with_tax` 被调用了一次：

```python
print(total(12, 3))
print(with_tax(total(12, 3)))
```

从 `cli` 出发，导入图上只有一条边：`cli` 依赖 `pricing`。调用了几次、按什么顺序调，导入语句里看不出来。

反过来也一样。`pricing.py` 里有个函数可能从来没被调用；`cli.py` 里导入的某个名字也可能只是放在那里没用。导入关系说明的是“谁允许知道谁”，不是“程序实际跑了哪条路”。

`python -c "import shop.cli"` 是最好的证据：`shop.cli` 确实被导入了，`pricing` 也执行了，但因为入口判断没成立，`total` 一次都没调用，屏幕上没有 36。

读项目时，这两张图要分开看：

- **导入图**告诉你模块边界和依赖方向。它适合回答“改这个底层模块，哪些上层会受影响”。
- **调用图**告诉你运行时谁调了谁。它适合回答“这个函数为什么被执行了”。

排查“为什么这里跑了两遍”，看 import 没有用，得看调用栈、日志，或者在函数里打一行输出。导入只发生一次，不代表函数只调用一次。

顶层导入和延迟导入也是取舍。顶层导入把依赖摆在外面，缺东西启动就报错；把 import 挪进函数，可以避开循环、少加载用不到的东西，但失败会推迟到运行中，读代码时也不容易发现这个依赖。两者都能用，别把延迟导入当成隐藏依赖的手段。

## 三个会浪费半天的坑 {#pitfalls}

**“文件名和标准库撞了也没关系，我导入的是自己的。”** 有关系。新建一个目录：

```
shadow/
├── json.py
└── use_json.py
```

`json.py`：

```python
print("我自己的 json")
```

`use_json.py`：

```python
import json

print(json.dumps({"a": 1}))
```

在 `shadow/` 里运行 `python use_json.py`，去掉 traceback 中间几行，你会看到：

```
我自己的 json
AttributeError: module 'json' has no attribute 'dumps'
```

脚本所在目录排在搜索路径最前面，所以 `import json` 先找到了你的 `json.py`，标准库的 `json` 根本没机会加载。解释器可能还会补一句“是不是和标准库重名”，那句话说的就是这个。

别把自己的文件叫 `json.py`、`random.py`、`types.py`、`logging.py`。已经撞了就改名，不要靠调导入顺序去绕。

**“导入出问题，往 `sys.path` 里加一行路径就好了。”** 这行代码在你机器上可能立刻见效，但它把项目的目录结构写进了运行环境。换一台机器、跑测试、打成安装包之后，当前工作目录一变，这行就可能指向不存在的位置。

包内导入失败，先看清楚是“以什么方式启动”的问题。该用 `python -m 包.模块` 就用它，或者把项目按包安装。临时改 `sys.path` 会把真正的结构问题盖住。

**“把 import 全塞进函数里，循环导入就解决了。”** 有时确实能解决，因为导入被推迟到调用时。但代价是依赖不再出现在文件顶部，读代码的人要翻到函数里才知道它用了谁；错误也从启动时推迟到运行时。循环导入优先改结构，延迟导入留给确实需要它的地方。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：在 `shop/` 的上一级运行 `python shop/cli.py`，报 `ModuleNotFoundError: No module named 'shop'`。为什么？该怎么运行？

> **答案**
>
> 直接运行脚本时，Python 把脚本所在的 `shop/` 目录放进搜索路径。`cli.py` 里的 `from shop.pricing import ...` 需要找到 `shop` 包，也就是要在 `shop/` 的上一级找；那一级不在路径里，所以失败。
>
> 用模块方式运行：
>
> ```bash
> python -m shop.cli
> ```
>
> `-m` 会把当前目录作为起点，并且把 `shop.cli` 当主程序执行。

**第 2 题**：`shop/cli.py` 里 `if __name__ == "__main__":` 下面的代码，什么时候执行，什么时候不执行？

> **答案**
>
> 用 `python -m shop.cli` 运行时，`cli` 是主程序，`__name__` 是 `"__main__"`，块里的代码执行。
>
> 用 `import shop.cli` 导入时，`__name__` 是 `"shop.cli"`，条件不成立，块里的代码跳过。不过 `cli.py` 顶层的导入语句仍然会执行。

**第 3 题**：`a.py` 里 `from b import b_name`，`b.py` 里 `from a import a_name`，用 `main.py` 导入 `a`，为什么报 `ImportError`？给出两种修法。

> **答案**
>
> `main` 导入 `a` 后，`a` 开始执行，第一行又去导入 `b`；`b` 第一行要 `a` 的 `a_name`，可 `a` 才执行到第一行，`a_name` 还没赋值。`a` 在 `sys.modules` 里，但只是个半成品，所以是“名字不存在”，不是“模块不存在”。
>
> 修法一：两边都只 `import 模块`，到函数里再访问属性。
>
> ```python
> # a.py
> import b
> a_name = "A"
> def hello():
>     return f"{a_name} 认识 {b.name}"
>
> # b.py
> import a
> name = "B"
> ```
>
> 修法二：把共用部分挪到 `common.py`，让 `a` 和 `b` 都只依赖 `common`，依赖变成单向的。

## 继续阅读 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [程序怎样执行：从源文件到结果](/learn/python-execution)
- [类、对象与继承](/learn/python-classes)
- [异常、捕获与抛出](/learn/python-exceptions)

## 参考资料 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
