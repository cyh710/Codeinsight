# 文件、路径与资源生命周期

## 小林的账本跑到了别的目录 {#overview}

文件操作只要盯住三件事：路径找对、编码对上、用完关掉。读完这一篇，你能用 Path 和 with 把这三件事各跑一遍。

小林在 `ledger_demo` 目录里放了一个 `show.py` 和一个 `expenses.txt`。双击脚本或在目录里运行，账本读得好好的。换成从上一级目录执行，脚本却说找不到文件。

更麻烦的是写文件的时候。如果程序用写模式打开一个相对路径，它不会报错，而是在启动目录里新建一个空文件。下次再运行，读到的就是那个空账本。

这一篇按三件事拆开：路径到底以哪里为基准、文本怎么写进去、写完什么时候才算交给别人。

## 把路径交给 Path {#pathlib}

最直接的路径写法是字符串拼接。它的毛病是分隔符要自己挑：写死反斜杠的代码到 macOS 或 Linux 上找不到文件，写死斜杠的代码又和 Windows 上其他路径混得别扭。

`pathlib.Path` 把路径当成对象，用 `/` 运算符拼：

```python
from pathlib import Path

base = Path("data")
ledger = base / "expenses.txt"
print(ledger.as_posix())
print(ledger.parent.as_posix())
print(ledger.name)
```

```
data/expenses.txt
data
expenses.txt
```

`Path("data")` 只描述"名为 data 的目录"，此刻并没有检查它是否存在。`base / "expenses.txt"` 按当前系统的规则拼接，Windows 内部用反斜杠，macOS 和 Linux 用斜杠。`as_posix()` 统一用斜杠输出，适合写日志和文档。`.parent` 是上一级目录，`.name` 是文件名。

路径对象不代表文件存在，也不代表你有权读它。存在性要另外问：`ledger.exists()` 返回布尔值，`ledger.is_file()` 还会检查它是不是普通文件。拼接、存在性、权限是三件事，Path 只负责第一件。

## 相对路径认的是启动目录 {#working-directory}

建一个这样的目录：

```text
ledger_demo/
├─ show.py
└─ expenses.txt
```

`expenses.txt` 里写两行：

```text
午饭 18
咖啡 22
```

`show.py` 用相对路径读它：

```python
from pathlib import Path

path = Path("expenses.txt")
print(path.read_text(encoding="utf-8").strip())
```

在 `ledger_demo` 里面运行：

```bash
cd ledger_demo
python show.py
```

```
午饭 18
咖啡 22
```

回到上一级，用脚本路径运行同一个文件：

```bash
cd ..
python ledger_demo/show.py
```

输出末尾是：

```
FileNotFoundError: [Errno 2] No such file or directory: 'expenses.txt'
```

`python ledger_demo/show.py` 只是把要执行的脚本指过去，没有切换当前工作目录。Python 进程的 cwd 仍然是上一级目录，`Path("expenses.txt")` 就在上一级里找，自然找不到。

把路径改成以脚本所在目录为基准：

```python
from pathlib import Path

path = Path(__file__).resolve().parent / "expenses.txt"
print(path.read_text(encoding="utf-8").strip())
```

现在从上一级运行 `python ledger_demo/show.py`，输出又是：

```
午饭 18
咖啡 22
```

`__file__` 是当前脚本的路径，`.resolve()` 把它换成绝对路径，`.parent` 取出脚本所在目录。用这个目录再做 `/` 拼接，结果就不受启动位置影响。

`__file__` 只在脚本里可靠。交互式解释器和 `python -c` 没有这个变量，那时要用 `Path.cwd()` 或显式传入路径。

还有一种情况要分开：账本是用户数据，不该永远跟着代码走。用户可能从桌面启动、从服务里启动，或者根本没有写代码目录的权限。代码自带的资源用 `__file__`，用户数据用主目录、环境变量或命令行参数指定位置。

## 文本模式：缓冲、编码、换行 {#text-mode}

`open` 返回的不是磁盘本身，而是一个带缓冲区的文件对象。`write` 先把字符放进缓冲区，什么时候真正交给操作系统，由缓冲策略决定。

```python
from pathlib import Path

f = open("note.txt", "w", encoding="utf-8")
f.write("午饭 18\n")
print("另一个句柄读到：", repr(Path("note.txt").read_text(encoding="utf-8")))
f.close()
print("关闭后读到：", repr(Path("note.txt").read_text(encoding="utf-8")))
```

```
另一个句柄读到： ''
关闭后读到： '午饭 18\n'
```

第一次读的时候，`write` 的内容还在 Python 的缓冲区里，另一个句柄看到的是空文件。`close()` 会先把缓冲区刷出去，再释放句柄。这就是"程序里写了"和"别人能读到"之间的差别。

`flush()` 只刷缓冲区，不释放句柄；`close()` 会刷缓冲区，也会释放。CPython 在文件对象被回收时通常会顺手关闭，但你不能决定它什么时候被回收，所以不要靠这个。

用 `with` 把关闭动作绑定到代码块的退出：

```python
from pathlib import Path

with open("note.txt", "w", encoding="utf-8") as f:
    f.write("午饭 18\n")

print(repr(Path("note.txt").read_text(encoding="utf-8")))
```

```
'午饭 18\n'
```

即使代码块里抛出异常，`with` 也会关闭文件。文件对象、锁、数据库连接都靠这个模式配对进入和退出。

小文件可以用 `Path` 提供的两个快捷方法，它们内部会打开、读写、关闭：

```python
from pathlib import Path

Path("note.txt").write_text("咖啡 22\n", encoding="utf-8")
print(repr(Path("note.txt").read_text(encoding="utf-8")))
```

```
'咖啡 22\n'
```

`write_text` 默认覆盖原内容，不是追加。需要追加时用 `open(..., "a", encoding="utf-8")`。

`encoding="utf-8"` 管的是字节和字符怎么互相转换。不传编码时，Python 3.13 用系统默认编码；中文 Windows 上常见的是 `cp936`，macOS 和 Linux 上通常是 UTF-8。同一个文件换台机器读，可能就解不出来。

下面这个文件是用 GBK 编码写进去的：

```python
from pathlib import Path

Path("gbk.txt").write_bytes("午饭 18".encode("gbk"))
print(Path("gbk.txt").read_text(encoding="utf-8"))
```

输出末尾是：

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xce in position 0: invalid continuation byte
```

按 GBK 读就正常了：

```python
from pathlib import Path

print(Path("gbk.txt").read_text(encoding="gbk"))
```

```
午饭 18
```

`UnicodeDecodeError` 说的是"这些字节不是合法的 UTF-8"，不是"文件坏了"。写文件时明确写 `encoding="utf-8"`，读的时候也用同一个编码，别依赖机器默认值。可以用 `locale.getpreferredencoding(False)` 看你当前的默认编码，它不保证是 UTF-8。

换行符也会被文本模式改写。不传 `newline` 时，写出去的 `\n` 会换成当前系统的换行符，Windows 上是 `\r\n`，可以用 `read_bytes()` 看到 `b'a\r\nb\r\n'`。要固定成 LF，就显式指定：

```python
from pathlib import Path

Path("lf.txt").write_text("a\nb\n", encoding="utf-8", newline="\n")
print(Path("lf.txt").read_bytes())
```

```
b'a\nb\n'
```

读的时候，文本模式默认把 `\r\n` 和 `\r` 都归一成 `\n`，所以 `splitlines()` 不会因为平台不同多出空行。JSON、CSV、配置和要进版本库的文本，写入时最好固定 `newline="\n"`。

## 用 glob 扫一个目录 {#glob}

假设 `data` 目录长这样：

```text
data/
├─ 2026-09.txt     午饭 18 / 咖啡 22
├─ 2026-10.txt     打车 26
└─ 2025/
   └─ 12.txt       午饭 30
```

`glob` 按通配符找直接子项，`rglob` 连子目录一起找：

```python
from pathlib import Path

data = Path("data")
total = 0
for path in sorted(data.glob("*.txt")):
    for line in path.read_text(encoding="utf-8").splitlines():
        total += int(line.split()[-1])
    print(path.name)
print("合计", total)
print("含子目录：", len(list(data.rglob("*.txt"))))
```

```
2026-09.txt
2026-10.txt
合计 66
含子目录： 3
```

`glob("*.txt")` 只返回 `data` 这一层的 `.txt` 文件，`2025/12.txt` 不在里面，所以合计是 18 + 22 + 26 = 66。`rglob` 会往下走，数到三个文件。

返回顺序不保证，所以先用 `sorted` 排一下；否则同一段代码在不同文件系统上打印顺序可能不同。`glob` 也会匹配名字以 `.txt` 结尾的目录，需要只处理文件时加 `if path.is_file()`。

目录不存在时，`glob` 返回空结果而不是报错。如果"目录必须存在"是业务要求，先检查 `data.is_dir()`，或者让后面读取失败、交给异常处理。

## exists、编码、close 与路径穿越 {#pitfalls}

**"先判断 `exists()` 再打开，就不会出错。"** 检查和打开是两步，文件可能在这两步之间被删除、改名或换掉。这种时间差叫 TOCTOU，判断得再早也挡不住。

正确做法是直接操作，失败时接住对应的异常：

```python
from pathlib import Path

path = Path("expenses.txt")
try:
    text = path.read_text(encoding="utf-8")
except FileNotFoundError:
    print("账本还没建")
else:
    print(text.strip())
```

`exists()` 仍然适合"显示一个可选的提示"这类不影响正确性的判断，但不要把它当成打开成功的保证。

**"Python 默认编码就是 UTF-8。"** Python 3.13 的 `open` 不传编码时用系统区域设置，中文 Windows 上常常是 `cp936`：

```python
import locale
print(locale.getpreferredencoding(False))   # 中文 Windows 上常见 cp936
```

你机器上的输出可能是别的值，重点是它不保证是 UTF-8。跨机器交换的文件，显式写 `encoding="utf-8"`。

**"`close()` 之后数据就一定落到磁盘了。"** `close()` 把数据从 Python 的缓冲区交给操作系统，不代表硬盘已经写完。系统崩溃或突然断电时，还在操作系统缓存里的数据可能丢。需要更强保证时，可以 `flush()` 后调用 `os.fsync(f.fileno())`：

```python
import os

with open("note.txt", "w", encoding="utf-8") as f:
    f.write("午饭 18\n")
    f.flush()
    os.fsync(f.fileno())
```

`fsync` 能减少"已经返回成功但数据还在内存里"的风险，但不同文件系统、磁盘和硬件的保证并不完全一样。真正重要的账目、订单和状态，交给数据库的事务，比自己拼文件可靠。

**"用了 `Path`，拼接用户输入就安全了。"** `Path` 只负责拼和规范化，不负责授权。用户传 `../../secrets.txt`，它能一路跳出你想要的目录：

```python
from pathlib import Path

base = Path("data").resolve()
target = (base / "../../secrets.txt").resolve()
print(target.is_relative_to(base))
```

```
False
```

先 `resolve()`，再用 `is_relative_to(base)` 检查最终位置是否还在允许目录里。只接受文件名时，`Path(user_input).name` 会丢掉目录部分。符号链接也要算进最终解析后的路径，不能只看输入字符串。

## 文件小就直接读，大了要换写法 {#tradeoffs}

`read_text()` 会把整个文件读进内存。几十 KB 的配置、几千行的账本，这样最省事；几百 MB 的日志或导出文件，就会把内存吃满。

| 情况 | 更合适的写法 |
| --- | --- |
| 小配置、小账本，一次读写 | `read_text` / `write_text` |
| 持续增长的日志 | `open(..., "a")` 追加，按需刷新 |
| 大文件，只逐行处理 | `with open(...)` 迭代，不调用 `read()` |
| 多个进程同时改同一个文件 | 文件锁，或者换数据库 |
| 读者不能看到写到一半的文件 | 同目录临时文件，再 `replace` |

逐行读的写法不需要把文件装进列表。在刚才的 `ledger_demo` 目录里运行：

```python
with open("expenses.txt", encoding="utf-8") as f:
    for line in f:
        if line.startswith("午饭"):
            print(line.strip())
```

```
午饭 18
```

写到一半的风险可以用临时文件加替换解决：

```python
from pathlib import Path

target = Path("note.txt")
tmp = target.with_name("note.txt.tmp")
tmp.write_text("咖啡 22\n", encoding="utf-8")
tmp.replace(target)
print(target.read_text(encoding="utf-8").strip())
```

```
咖啡 22
```

临时文件和目标在同一个目录，`replace` 才是原子的：读者要么看到旧文件，要么看到新文件，不会看到一半旧一半新。跨文件系统移动不保证原子。这个保证也不等于掉电后一定还在，原子替换和持久化是两件事。

`write_text` 会截断原文件。如果本意是追加，用 `open(..., "a")`；如果多个进程一起追加，行可能交错，需要文件锁或改用数据库。

判断标准很直接：文件小、写入少、只有一个写者，`Path` 的两个快捷方法足够；文件可能很大、读者可能随时打开、或者有几个写者，就要考虑逐行、原子替换、锁，甚至换存储。

## 三个文件和路径问题 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：项目结构是 `app/main.py` 和 `app/data/expenses.txt`。在项目根目录执行 `python app/main.py`，`main.py` 里的 `Path("data/expenses.txt")` 找不到文件。为什么？怎么改？

> **答案**
>
> 相对路径以进程的当前工作目录为基准。你在项目根目录启动，cwd 就是根目录，`data/expenses.txt` 指向根目录下的 `data`，而不是 `app/data`。
>
> 如果这个文件是随代码发布的资源，改成以脚本目录为基准：
>
> ```python
> from pathlib import Path
>
> path = Path(__file__).resolve().parent / "data" / "expenses.txt"
> ```
>
> 如果它是用户数据，应该由配置或命令行参数给出位置，不要固定绑在代码目录上。

**第 2 题**：这段代码为什么可能打印出空字符串？

```python
from pathlib import Path

f = open("note.txt", "w", encoding="utf-8")
f.write("午饭 18\n")
print(repr(Path("note.txt").read_text(encoding="utf-8")))
f.close()
```

> **答案**
>
> `write` 写进了 Python 的文件缓冲区，还没交给操作系统；另一个句柄此时读到的仍是空文件。后面 `close()` 才把缓冲区刷出去。
>
> 把写入放进 `with`，离开代码块时自动关闭：
>
> ```python
> from pathlib import Path
>
> with open("note.txt", "w", encoding="utf-8") as f:
>     f.write("午饭 18\n")
>
> print(repr(Path("note.txt").read_text(encoding="utf-8")))
> ```

**第 3 题**：写一个函数，把 `data` 下所有 `.txt` 每行末尾的数字加起来。目录不存在时你打算怎么办？给出代码和理由。

> **答案**
>
> 如果调用方需要知道"没读到"和"读到 0"的区别，就让异常抛出去；这里选择抛 `FileNotFoundError`，由上层决定提示还是退出。
>
> ```python
> from pathlib import Path
>
>
> def total_amount(data_dir):
>     data = Path(data_dir)
>     if not data.is_dir():
>         raise FileNotFoundError(f"没有目录：{data}")
>     total = 0
>     for path in sorted(data.glob("*.txt")):
>         for line in path.read_text(encoding="utf-8").splitlines():
>             total += int(line.split()[-1])
>     return total
>
>
> print(total_amount("data"))
> ```
>
> ```
> 66
> ```
>
> 如果这个目录本来就是可选的，返回 0 也可以，但要在函数说明里写清"目录不存在按 0 处理"，并且不要在返回值里假装读到了数据。

## 继续读什么 {#related}

- [异常与错误处理](/learn/python-exceptions)
- [上下文管理器：把进入与退出配对](/learn/context-manager)
- [文件锁：协调对共享文件的访问](/learn/file-lock)
- [配置与环境变量：别把路径写死](/learn/config-env)

## 参考与版本 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
