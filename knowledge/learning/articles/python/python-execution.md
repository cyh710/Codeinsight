# 程序怎样执行：从源文件到结果

## 一个项目从哪个文件开始跑 {#overview}

读完这一篇，你能分清一个 Python 文件被运行时和被导入时各自会发生什么，并能在项目里找到真正的入口。

小林接手一个记账项目。目录里有 main.py、cli.py、storage.py、models.py，他以为 Python 会按文件名顺序把每个文件跑一遍，于是先打开 models.py 读。读到第三行有一句 print 时他停住了：这里为什么会输出？谁在调用它？

答案不在文件名里，而在启动方式里。文件里写的是所有可能执行的语句，实际跑哪几条，由谁启动、谁调用决定。**运行和导入，走的是同一套执行机制**。先别读，先跑。

## 两个文件，先跑四遍 {#two-files}

新建一个空目录，进入它，写入两个文件。

lib.py：

```python
print("[lib] 顶层代码执行")

def add_expense(amount):
    print("[lib] add_expense 被调用")
    return amount

if __name__ == "__main__":
    print("[lib] __name__ 是", __name__)
```

main.py：

```python
print("[main] 开始")

import lib

print("[main] import 结束")
print("[main] lib 的名字是", lib.__name__)
lib.add_expense(12)
print("[main] 收尾")
```

第一种跑法，运行 main.py：

```bash
python main.py
```

你应该看到：

```
[main] 开始
[lib] 顶层代码执行
[main] import 结束
[main] lib 的名字是 lib
[lib] add_expense 被调用
[main] 收尾
```

第二种，单独运行 lib.py：

```bash
python lib.py
```

```
[lib] 顶层代码执行
[lib] __name__ 是 __main__
```

第三种，不经过 main.py，直接导入，而且导入两次：

```bash
python -c "import lib; import lib"
```

```
[lib] 顶层代码执行
```

`import lib` 写了两次，输出只有一次。

第四种，把 lib.py 当模块运行：

```bash
python -m lib
```

```
[lib] 顶层代码执行
[lib] __name__ 是 __main__
```

同一份 lib.py，四种启动方式。顶层 print 有时执行，`if` 那一段也时有时无。差别不在文件内容，而在谁启动它。

## 输出顺序是怎么排出来的 {#walkthrough}

**第一步，main.py 从第一行开始。** `print("[main] 开始")` 先执行，屏幕出现第一行。

**第二步，`import lib` 找到 lib.py，并把它的顶层代码执行一遍。** import 不是"登记一个名字"就结束，它要先把模块建出来。所以 `[lib] 顶层代码执行` 出现在这里，且排在 `[main] import 结束` 之前。

**第三步，`def add_expense(...)` 只绑定名字。** 这条语句创建一个函数对象，把名字 `add_expense` 绑到它上面。函数体里的 print 没有运行，因此你没有看到 `add_expense 被调用`。

**第四步，`if __name__ == "__main__":` 判断失败。** 这时 lib 是作为模块被导入的，它的 `__name__` 是 `"lib"`，不是 `"__main__"`。条件为假，整块跳过。

**第五步，控制权回到 main.py。** import 语句结束，接着打印 `[main] import 结束`。下一行打印 `lib.__name__`，值是 `lib`，正好印证上一步的判断。

**第六步，`lib.add_expense(12)` 才第一次进入函数体。** 打印 `[lib] add_expense 被调用`。函数返回 12，但返回值没有赋给任何名字，所以不显示。

**第七步，打印 `[main] 收尾`，main.py 结束。**

单独运行 `python lib.py` 时，Python 把这份文件当作主程序，给它的 `__name__` 是 `"__main__"`。顶层 print 执行，def 绑定名字，if 条件为真，于是打印出名字。函数体仍然没执行，因为没有人调用 `add_expense`。

这也解释了第三、第四种跑法：导入两次只执行一次，是因为第一次导入后模块被记住了；`python -m lib` 和 `python lib.py` 输出一样，是因为两种方式都把这份代码当作主程序执行，`__name__` 都是 `"__main__"`。

## import 背后发生了什么 {#import-mechanics}

Python 执行一个文件，大致分四步：读取源文件、解析语法并编译成代码对象、准备运行环境、执行顶层语句。编译通常先于执行，所以**整个文件有语法错误时，前面任何一行都不会跑**；运行时错误则是在执行到那一行才发生。

对导入来说，还有一层缓存。第一次 `import lib` 时，Python 找到 lib.py，编译并执行它的顶层语句，然后把模块对象存进 `sys.modules`。第二次 `import lib` 直接取缓存，不再执行。这就是上面"导入两次、输出一次"的原因。

模块从哪里找？运行时，启动脚本所在的目录排在搜索路径前面，所以 main.py 旁边的 lib.py 能被直接找到。换一个工作目录再运行，`import lib` 可能就报 `ModuleNotFoundError`。这不是代码变了，是搜索路径变了。

函数定义和类定义在这里不一样。`def` 只是把函数体存进一个函数对象，调用时才进入函数体；`class` 的类体在定义时就会执行，所以类体里写的 print 会立刻打印。读代码时看到 `def` 不必担心它被执行了，看到 `class` 则要留意类体里的语句。

导入时执行顶层语句，省事，也危险。把网络请求、读配置文件、连接数据库写在顶层，任何模块只要 import 它，就会触发这些动作。测试代码、命令行工具、甚至 IDE 的检查，都可能因此产生意料之外的副作用。

## 入口由启动方式决定 {#entry-point}

Python 不会自动寻找 main.py。文件名是 `main.py` 只是人的约定，解释器不认这个约定。总得有人发出 `python main.py`、`python -m 包名` 或者别的一条命令。

`if __name__ == "__main__":` 也不是"官方入口标记"。它只是在问：这份文件现在是主程序吗？直接运行时，`__name__` 是 `"__main__"`；被导入时，`__name__` 是模块名。一个项目里可以有十几个文件带这个判断，它们都只是"被直接运行时做点什么"。

找入口时，看启动方式，不要看目录顺序。常见的线索有四类：

- README、启动脚本、Dockerfile 里写着的运行命令。
- `pyproject.toml` 里的 `[project.scripts]`，它把一条命令映射到某个函数，例如 `ledger.cli:main`。
- `python -m 包名` 需要包里有一个 `__main__.py`，真正的启动代码在那里。
- 测试代码也可能直接导入函数来运行，此时入口是测试，不是 main.py。

还有一个容易忽略的事实：**阅读源码只能看到可能经过的路径**。函数放在那里，不代表生产环境调用了它。要确认，得看日志、调试器或实际输出。

## 五个容易弄反的地方 {#pitfalls}

**"import 只是把名字引进来，不会执行对方的代码。"** 会执行，而且是顶层代码全部执行，只是同一个模块只执行一次。把 `lib.py` 里的顶层 print 换成网络请求，这个误会立刻变成线上事故。

**"文件里定义了函数，函数就运行过了。"** 没有。`def` 只创建函数对象并绑定名字。上面 lib.py 的第二种跑法里，`add_expense` 一次也没被调用，屏幕不会出现 `add_expense 被调用`。

**"带 `if __name__ == "__main__"` 的文件就是项目入口。"** 不一定。它只描述"被直接运行时做什么"。真正决定入口的是启动命令，而这个判断可能出现在许多辅助文件里。

**"前面几行没问题，后面有语法错误也能先跑一部分。"** 不能。Python 先把整个文件编译好再执行，文件任何位置有语法错误，第一行都不会运行。运行时错误是另一回事：它发生在执行已经开始之后，比如除以零、字典里没有这个键。

**"`__pycache__` 里有 .pyc，说明当前代码跑过了。"** 不能这么推。`.pyc` 是编译缓存，源码改动后会重新编译；直接 `python main.py` 运行主脚本，通常也不会给主脚本留下 .pyc。代码到底跑没跑，看输出和日志，不看缓存目录。

## 启动代码该放在哪 {#startup-code}

小脚本把代码平铺在文件里最省事。它只被 `python script.py` 运行，不会被别人 import，这样写完全够用。

一旦这个文件会被测试、被别的模块导入，顶层副作用就要收起来。常见做法是只留一个薄薄的入口：

```python
def main():
    print("真正的工作从这里开始")

if __name__ == "__main__":
    main()
```

这样导入时只拿到函数，不会触发工作；测试可以单独调用函数；入口也只有一处。代价是多了一层调用，读代码时要多跳一步。

懒加载是另一种取舍。把 `import` 放进函数里，第一次调用才加载模块，启动更快，但错误也被推迟到第一次使用，而且首次调用会变慢。哪种更好，取决于你更怕启动慢，还是更怕运行到一半才报错。

复现问题时，先固定四样东西：解释器版本、依赖版本、启动命令、输入数据。执行结果依赖环境，只改代码往往掩盖了真正的不一致。需要确认某条路径是否真的走过，加日志比反复猜快。

## 三道跑一遍就能答的题 {#self-check}

先盖住答案自己跑一遍，再对照。

**第 1 题**：运行 `python main.py` 时，lib.py 里的 `if __name__ == "__main__":` 为什么没有执行里面的 print？

> **答案**
>
> 因为 lib.py 是被 `import lib` 加载的，模块的 `__name__` 是 `"lib"`，不是 `"__main__"`，条件为假。
>
> 只有 `python lib.py` 或 `python -m lib` 这种直接启动它的方式，才会把 `__name__` 设成 `"__main__"`。

**第 2 题**：把 lib.py 第一行的 `print("[lib] 顶层代码执行")` 删掉，再运行 `python main.py`，输出是什么？

> **答案**
>
> ```
> [main] 开始
> [main] import 结束
> [main] lib 的名字是 lib
> [lib] add_expense 被调用
> [main] 收尾
> ```
>
> 顶层 print 没了，但 import 仍然会执行 lib.py 的其余顶层语句，`if` 块仍然不成立，函数调用也仍然在第六步发生。

**第 3 题**：`python lib.py` 和 `python -m lib` 的输出完全一样，为什么？

> **答案**
>
> 两种方式都把 lib.py 当作主程序来执行，`__name__` 都是 `"__main__"`。
>
> 差别在于模块的查找方式和包上下文，这个例子里没有体现出来。判断一段代码会不会执行，先看它是被直接运行还是被导入，比看命令形式更可靠。

## 接着读模块与函数 {#related}

- [模块、包与导入](/learn/python-modules)
- [函数、参数与返回值](/learn/python-functions)
- [异常与错误处理](/learn/python-exceptions)

## 参考资料与版本 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
