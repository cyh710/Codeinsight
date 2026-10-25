# 异常与错误处理

## 小林找不到账本了 {#overview}

文件不存在、输入不是数字，这类失败不该让程序甩出一屏报错就退出。读完这一篇，你能判断错误该在哪一层被接住。

小林把 `read_ledger.py` 和 `账本.txt` 放在同一个文件夹，运行起来一切正常。有一天他从终端里换了个目录执行这个脚本，屏幕立刻红了。

```python
from pathlib import Path

text = Path("账本.txt").read_text(encoding="utf-8")
print(text)
```

```bash
python read_ledger.py
```

输出末尾是这一行：

```
FileNotFoundError: [Errno 2] No such file or directory: '账本.txt'
```

`FileNotFoundError` 是异常类型，冒号后面是这一次的具体消息。上面还有几行调用栈，从下往上读：最下面一行说明"什么失败了"，往上每一行说明"谁调用了谁"。

Python 遇到没人接的异常时，会打印调用栈并以非零状态退出。程序没算错数，它是在说：这一步走不下去了。

## 把报错接住：try 与 except {#try-except}

小林先让缺账本变成可以接受的情况：按 0 元算，并明确打印一句提示。

```python
from pathlib import Path


def read_amount(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
        return int(text.strip())
    except FileNotFoundError:
        print("账本还没建，先按 0 算")
        return 0
    except ValueError:
        print("账本内容不是整数")
        return -1


print(read_amount("账本.txt"))
```

第一次运行时 `账本.txt` 不存在，你应该看到：

```
账本还没建，先按 0 算
0
```

把 `18` 写进 `账本.txt`，再运行，输出变成 `18`。把内容改成 `十八`，再运行：

```
账本内容不是整数
-1
```

拆开看这个函数的执行。

第一步，`try` 里的两行按顺序执行：先读文件，再把文本转成整数。这两步都可能失败，而且失败类型不同。

第二步，`read_text` 失败时抛出 `FileNotFoundError`，`int` 失败时抛出 `ValueError`。异常一出现，`try` 里剩下的代码立刻停止，Python 从上往下找第一个匹配的 `except`。

第三步，匹配看的是异常的类型，不是消息文字。`FileNotFoundError` 接住"文件不在"，`ValueError` 接住"转不成整数"。接住之后，函数按你写的 `return` 交回一个值，程序继续跑。

`except` 的匹配顺序有讲究。`FileNotFoundError` 是 `OSError` 的子类，`OSError` 又是 `Exception` 的子类。看这段：

```python
def explain(exc):
    try:
        raise exc
    except FileNotFoundError:
        return "找不到文件"
    except OSError:
        return "其他操作系统错误"
    except Exception:
        return "其他异常"


print(explain(FileNotFoundError("x")))
print(explain(PermissionError("x")))
print(explain(ValueError("x")))
```

```
找不到文件
其他操作系统错误
其他异常
```

`raise exc` 把传进来的异常原样抛出去，这里只是为了观察匹配。`PermissionError` 不是 `FileNotFoundError`，但它是 `OSError` 的子类，所以落进第二支。`ValueError` 跟文件系统无关，落到 `Exception`。

把前两个 `except` 调换位置，第一行输出就会变成"其他操作系统错误"。代码照样跑，结果却是错的——**宽的类型放在窄的类型前面，会截走本该由窄类型处理的异常**。

要接住同一类处理的多个异常，可以写成 `except (FileNotFoundError, PermissionError):`。需要看消息时写 `except OSError as exc:`，`str(exc)` 是消息，`type(exc).__name__` 是类型名。

## except Exception 为什么容易掩盖问题 {#over-except}

这段代码错了一个键名，结果却变成了一个看起来正常的 0：

```python
def total(expenses):
    try:
        return sum(item["amount"] for item in expenses)
    except Exception:
        return 0


print(total([{"amount": 12}, {"amt": 35}]))
```

```
0
```

账本里明明有一笔 12，第二个字典的键却拼错了。`item["amount"]` 抛出 `KeyError`；`except Exception` 把它接住，整个计算变成 0。

界面会显示"本月 0 元"，看起来像正常结果。真正的错误被藏了起来，你要等到对账时才发现少了一笔。

**`except Exception` 的语义是"这些失败我都能处理"。写它之前先回答：你能处理 `KeyError`、`TypeError`、`AttributeError` 吗？** 键名拼错、变量类型用错属于程序缺陷，它应该在最接近出错的地方炸出来。

比它更宽的是裸 `except`：

```python
try:
    raise KeyboardInterrupt
except:            # 没有写类型 = 接住 BaseException
    print("Ctrl+C 被吞掉了")
```

```
Ctrl+C 被吞掉了
```

裸 `except` 等价于 `except BaseException`，连 `KeyboardInterrupt` 和 `SystemExit` 都接。用户按 Ctrl+C 想停下，程序却继续转。日常代码里没有理由这么写。

顶层边界是例外：一个命令行入口或 HTTP 请求处理器可以捕获 `Exception`，把完整调用栈写进日志，再返回错误码或 500。它不是在吞，它把失败记录下来了，并且明确告诉外面"这次没成功"。

## raise from：把原因留在链上 {#raise-from}

`int("三")` 的原始消息是 `invalid literal for int() with base 10: '三'`。直接把它交给用户，用户看不出是哪个字段错了；悄悄换成一句"数量不对"又会丢掉排查线索。可以换一个更贴近业务的错误，同时把原因挂上：

```python
def parse_count(text):
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"数量不是整数：{text!r}") from exc


try:
    parse_count("三")
except ValueError as exc:
    print(type(exc).__name__, exc)
    print("原因：", type(exc.__cause__).__name__, exc.__cause__)
```

```
ValueError 数量不是整数：'三'
原因： ValueError invalid literal for int() with base 10: '三'
```

`raise` 新建了一个更适合上层的错误，`from exc` 把原始异常挂在 `__cause__` 上。打印完整调用栈时，两段会连在一起，第二段前面写着 "The above exception was the direct cause of the following exception"。

不写 `from`，原始异常仍然在 `__context__` 里，调用栈会显示 "During handling of the above exception, another exception occurred"。区别在于：`from` 明确说"我是故意换一个错误类型"，`__context__` 只是记录"处理上一个异常时又出错了"。

需要保留诊断信息，就写 `from exc`。只想给用户一句干净的话，同时不暴露内部细节，可以写 `raise ValueError("账本读不了") from None`；这会把原始异常链隐藏掉，日志里也看不到原因，所以要谨慎。

在 `except` 块里写一个光秃秃的 `raise`，会把当前异常原样重抛，类型和消息都不变。适合"记一笔日志，然后交给上层决定"的场景。

## finally 与 else 各管一段 {#finally-else}

`else` 和 `finally` 经常被写在一起，但它们负责的时机完全不同：

```python
def divide(a, b):
    try:
        result = a / b
    except ZeroDivisionError:
        print("除数是 0")
        return None
    else:
        print("算出来了")
        return result
    finally:
        print("这一步总会执行")


print(divide(10, 2))
print(divide(10, 0))
```

```
算出来了
这一步总会执行
5.0
除数是 0
这一步总会执行
None
```

`else` 只在 `try` **没有**异常时执行。把"只有成功才应该做"的代码放这里，它就不会被下面的 `except` 误伤——如果这些代码本身出错，你希望错误往外走，而不是被当作除零错误处理。

`finally` 不管前面是成功、接住了异常，还是异常继续往上抛，都会执行。它适合放清理动作：关文件、放锁、删临时文件。文件操作通常用 `with` 更省事，`with` 本质上就是帮你把退出动作配对好。

`finally` 里不要写 `return`：

```python
def read_or_default():
    try:
        raise FileNotFoundError("账本不在")
    finally:
        return 0


print(read_or_default())
```

```
0
```

原本的 `FileNotFoundError` 被 `finally` 里的 `return 0` 覆盖，异常消失了。`break` 和 `continue` 写在 `finally` 里也有类似效果。

## 捕获之后：处理还是重抛 {#handle-or-reraise}

判断标准只有一句话：**接住之后，你能不能做一件具体的事？**

能做下面任意一件，就接：

1. 你能恢复，并且恢复结果对调用方是诚实的。比如账本不存在时按 0 算，同时把"文件缺失"这个事实告诉调用方或写进日志。
2. 你能补上上下文再抛。底层函数知道路径，上层知道业务，转换时用 `raise ... from exc` 把两层信息连起来。
3. 你在程序边界上。命令行入口、HTTP 处理器、后台任务的 worker 需要把异常变成退出码、状态码或一条用户能读的消息，同时记日志。

一件都做不到，就让它往外走。上层至少还能看到真实的调用栈。

```python
from pathlib import Path


class LedgerMissing(Exception):
    pass


def load_lines(path):
    try:
        return Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise LedgerMissing(f"账本不存在：{path}") from exc


def show_total():
    try:
        lines = load_lines("账本.txt")
    except LedgerMissing as exc:
        print(f"提示：{exc}，先记一笔再来")
        return
    print(f"读到 {len(lines)} 行")


show_total()
```

```
提示：账本不存在：账本.txt，先记一笔再来
```

`load_lines` 不知道该给用户看什么，也不该决定程序要不要退出，所以它只做一件事：把 `FileNotFoundError` 换成更贴近业务的 `LedgerMissing`，原因留在 `__cause__` 上。`show_total` 在边界上，知道缺账本时该显示提示、然后安全返回，于是由它接住。

如果 `load_lines` 里写成 `except Exception: return []`，调用方拿到空列表，就会显示"读到 0 行"，缺文件和空文件分不出来。这是把"处理"做成了"掩盖"。

重试也是"恢复"的一种，但只对**可能自己好起来**的失败有意义：网络超时、文件被别的进程短暂锁住、数据库连接断开。`int("三")` 重试一百次还是失败，参数错误重试也一样。重试要有次数上限和间隔，否则会把一个明确的失败拖成卡死。

## 空结果、泄密和盲目重试 {#pitfalls}

**"捕获后返回空列表，就等于处理了。"** 空列表可能表示"本来就没有数据"，也可能表示"读取失败"。调用方无法区分，只能把两种情况都显示成 0。要让失败可见：

```python
from pathlib import Path


def load_lines(path):
    try:
        return Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None


lines = load_lines("账本.txt")
if lines is None:
    print("账本不存在，先记一笔")
else:
    print(f"本月 {len(lines)} 笔")
```

```
账本不存在，先记一笔
```

返回 `None` 至少把"失败"和"空"分开了。更好的做法通常是像上一节那样抛一个业务异常，让调用方明确选择怎么处理。

**"错误消息越详细越好，密钥和完整请求都打上。"** 错误消息会进日志、错误页面、监控系统，还会被转给同事。把密钥打进去等于主动泄露：

```python
def charge(api_key):
    try:
        raise TimeoutError("连接超时")
    except TimeoutError as exc:
        print(f"扣款失败 key={api_key}: {exc}")


charge("sk-live-123456")
```

```
扣款失败 key=sk-live-123456: 连接超时
```

保留"哪一步、什么路径、什么参数名"，删掉密钥、令牌、完整请求体和用户隐私。需要定位时用请求 ID 去日志里查，不要把敏感值复制到每一条消息里。

**"失败就多试几次，总能成功。"** 同一个输入、同一个状态，重试的结果通常一样：

```python
for attempt in range(3):
    try:
        print(int("三"))
    except ValueError:
        print("再试一次")
```

```
再试一次
再试一次
再试一次
```

这段代码没有打印任何数字，三轮都失败。重试前先问：失败是不是暂时的？如果是参数错、权限不足、文件格式坏，重试只是浪费时间，还会掩盖第一次就存在的 bug。

## 三个异常判断题 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这段会打印哪几行？

```python
try:
    1 / 0
except ZeroDivisionError:
    print("A")
else:
    print("B")
finally:
    print("C")
```

> **答案**
>
> `A` 和 `C`。
>
> `1 / 0` 抛出 `ZeroDivisionError`，进入 `except` 打印 A。`else` 只在 `try` 没有异常时执行，所以 B 不会出现。`finally` 无论成功还是失败都会执行，打印 C。

**第 2 题**：这个函数有什么问题？

```python
def parse_count(text):
    try:
        return int(text)
    except Exception:
        return None
```

> **答案**
>
> 它把 `int` 可能抛出的 `ValueError`，和函数体里可能出现的拼写错误、类型错误一起接住了。调用方只看到 `None`，分不清"输入不合法"还是"代码有 bug"。
>
> 应该只接 `ValueError`，并保留原因：
>
> ```python
> def parse_count(text):
>     try:
>         return int(text)
>     except ValueError as exc:
>         raise ValueError(f"数量不是整数：{text!r}") from exc
> ```

**第 3 题**：把 `load_lines` 改成"文件不存在时抛 `LedgerMissing`，其他 `OSError` 原样往外抛"，再在 `show_total` 里接住它、打印一句提示。

> **答案**
>
> ```python
> from pathlib import Path
>
>
> class LedgerMissing(Exception):
>     pass
>
>
> def load_lines(path):
>     try:
>         return Path(path).read_text(encoding="utf-8").splitlines()
>     except FileNotFoundError as exc:
>         raise LedgerMissing(f"账本不存在：{path}") from exc
>
>
> def show_total():
>     try:
>         lines = load_lines("账本.txt")
>     except LedgerMissing as exc:
>         print(f"提示：{exc}")
>         return
>     print(f"读到 {len(lines)} 行")
> ```
>
> `PermissionError` 不是 `FileNotFoundError`，不会被第一个分支接住，会继续往上走。是否需要处理它，由调用链上能处理它的那一层决定。

## 相关的下一篇 {#related}

- [文件、路径与资源生命周期](/learn/python-files)
- [函数、参数与返回值](/learn/python-functions)
- [上下文管理器：把进入与退出配对](/learn/context-manager)
- [重试与幂等：失败后怎样安全再来一次](/learn/retry-idempotency)

## 参考资料 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
