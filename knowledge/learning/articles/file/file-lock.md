# 文件锁：协调对共享文件的访问

## 两个进程往同一个文件里写 {#overview}

学完这一篇，你能看出并发写文件为什么会交错，会用 filelock 把一段写操作串起来，也知道它管不到哪些情况。

小林写了一个定时脚本，每五分钟把当天账目追加到 `shared.log`。有次他手滑同时跑了两个实例，打开文件看到：

```
A 记录1 第一行
B 记录1 第一行
A 记录1 第二行
A 记录1 第三行
B 记录1 第二行
...
```

本来该连在一起的三行一条记录，被另一个进程插了进来。程序没报错，文件也没坏，但下游按三行一条解析，从此全错位。

两个进程各自打开同一个文件，谁先写、谁后写由操作系统调度决定。你的代码里没有任何东西规定"一个进程写完一整条，另一个才能开始"。

## 三种锁，管的范围不一样 {#granularity}

同时发生的位置不同，能用的锁也不同。

| 谁和谁同时 | 用什么 | 管不到 |
|---|---|---|
| 同一进程里的多个线程 | `threading.Lock` | 其他进程 |
| 同一台机器的多个进程 | `fcntl.flock`（Linux/macOS）、`msvcrt.locking` 或 `LockFileEx`（Windows） | 其他机器、不遵守同一个锁路径的写者 |
| 多台机器 | 数据库行锁、Redis 租约锁 | 网络分区、租约过期 |

`threading.Lock` 只在当前 Python 进程内有效。你再开一个终端跑 `python script.py`，新进程有它自己的锁对象，和第一个进程的锁毫无关系；两个进程照样能同时进入"临界区"。

跨进程要靠操作系统。POSIX 上是 `fcntl.flock`；Windows 上没有 `fcntl`，可以用 `msvcrt.locking` 锁文件的一段字节，`filelock` 这类库在新版本里用的是 `LockFileEx`，效果同类。它们都把"锁"挂在一个文件上，所以锁路径本身就成了协议的一部分。

跨机器时，文件锁基本帮不上忙。两台机器各自打开"同一个路径"，在 NFS 或 SMB 上看起来像同一个文件，但锁的语义取决于服务器和挂载参数，不能默认和本地盘一样。真要跨机器协调，用数据库事务或带租约的分布式锁。

## 先看一次不加锁的追加 {#race-demo}

新建 `race.py`：

```python
import multiprocessing as mp
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG = BASE / "shared.log"


def write_records(tag):
    with open(LOG, "a", encoding="utf-8") as f:
        for i in range(1, 6):
            for part in ("第一行", "第二行", "第三行"):
                f.write(f"{tag} 记录{i} {part}\n")
                f.flush()
                time.sleep(0.01)


if __name__ == "__main__":
    LOG.unlink(missing_ok=True)
    p1 = mp.Process(target=write_records, args=("A",))
    p2 = mp.Process(target=write_records, args=("B",))
    p1.start()
    p2.start()
    p1.join()
    p2.join()
    print(LOG.read_text(encoding="utf-8"))
```

运行：

```bash
python race.py
```

你会看到类似：

```
A 记录1 第一行
A 记录1 第二行
B 记录1 第一行
A 记录1 第三行
B 记录1 第二行
A 记录2 第一行
...
```

每次顺序都不一样，但规律一样：**A 的三行记录会被 B 切断**。`flush()` 让每一行立刻落到文件，`sleep(0.01)` 故意把进程切换的窗口放大；删掉这两行，交错仍然可能发生，只是更难看见。

`if __name__ == "__main__":` 不能省。Windows 用 spawn 启动子进程，子进程会重新导入这个文件；没有这层判断，子进程会继续创建子进程，直接报错或失控。`LOG` 用脚本所在目录的绝对路径，不依赖你从哪个目录运行。

## 加一把跨进程的锁 {#example}

装库：

```bash
pip install filelock
```

把 `race.py` 改成 `locked.py`，只动 `write_records`，再补一行锁文件检查：

```python
import multiprocessing as mp
import time
from pathlib import Path

from filelock import FileLock

BASE = Path(__file__).resolve().parent
LOG = BASE / "shared.log"
LOCK = BASE / "shared.log.lock"


def write_records(tag):
    with FileLock(LOCK, timeout=5):
        with open(LOG, "a", encoding="utf-8") as f:
            for i in range(1, 6):
                for part in ("第一行", "第二行", "第三行"):
                    f.write(f"{tag} 记录{i} {part}\n")
                f.flush()
                time.sleep(0.01)


if __name__ == "__main__":
    LOG.unlink(missing_ok=True)
    p1 = mp.Process(target=write_records, args=("A",))
    p2 = mp.Process(target=write_records, args=("B",))
    p1.start()
    p2.start()
    p1.join()
    p2.join()
    print(LOG.read_text(encoding="utf-8"))
    print("锁文件还在吗:", LOCK.exists())
```

```bash
python locked.py
```

你会看到类似：

```
A 记录1 第一行
A 记录1 第二行
A 记录1 第三行
A 记录2 第一行
...
A 记录5 第三行
B 记录1 第一行
B 记录1 第二行
B 记录1 第三行
B 记录2 第一行
...
B 记录5 第三行
锁文件还在吗: False
```

在 Windows 上末尾那行是 `False`；在 Linux 或 macOS 上通常是 `True`。这是平台差异，不是程序写错。A 和 B 谁先写也不固定，可能是 B 在前；只要同一条记录的三行不再被切开，锁就起作用了。

`time.sleep(0.01)` 留在锁里只是为了让这段输出看起来完整。真实代码不要在持锁时睡，也不要在持锁时发网络请求或等用户输入——你睡着的时候，别的进程全在排队。

## 锁住的那几行在做什么 {#walkthrough}

第一步，`FileLock(LOCK, timeout=5)` 只是创建一个锁对象，还没有去抢。锁文件 `shared.log.lock` 和要写的数据文件 `shared.log` 是两个文件。

第二步，进入 `with` 时，`FileLock` 向操作系统申请 `LOCK` 上的排他锁。另一个进程已经持有的话，它在 5 秒内反复尝试；超时就抛出 `filelock.Timeout`。

第三步，拿到锁之后才执行打开、写、刷新、关闭。两个进程用的是同一个 `LOCK` 路径，所以一个在里面时，另一个进不来。

第四步，离开 `with`（正常结束或异常）时释放锁。操作系统在进程退出时也会收回它持有的锁；进程被强杀不会留下一个永久生效的锁，但锁文件可能还在磁盘上。

锁到底锁了什么？POSIX 的 `flock` 是**协商锁**：内核记录谁持有了这个锁，但它不会阻止一个不查锁的进程直接 `open("shared.log", "a")` 然后写。Windows 的字节范围锁由系统强制执行，可它锁的是 `shared.log.lock` 里的那段字节，不是 `shared.log` 的内容；别人不拿这把锁，照样能写数据文件。

所以文件锁保护的是**所有参与者都遵守同一套协议**时的顺序。协议包括：锁哪个路径、先拿锁再打开数据文件、拿不到锁怎么办。少一条，保护就漏。

**超时和死锁**要单独说。默认情况下 `filelock` 的 `timeout=-1`，意思是等到天荒地老。批量任务里通常要设一个上限：

```python
from filelock import FileLock, Timeout

try:
    with FileLock("report.lock", timeout=2):
        pass   # 真正的工作放这里
except Timeout:
    print("两秒内没拿到锁，这次先跳过")
```

超时只是给等待设上限，不是死锁检测器。两个进程各拿一把锁、再等对方的锁，就会停住。进程 1 按 a → b 的顺序拿：

```python
with FileLock("a.lock"):
    with FileLock("b.lock"):
        ...
```

进程 2 反过来，按 b → a：

```python
with FileLock("b.lock"):
    with FileLock("a.lock"):
        ...
```

如果两边都不设超时，它们会永远等下去。设了超时，至少不会永久卡住，但可能出现两个进程反复超时、反复重试的活锁。可靠的做法是**所有进程按同一个全局顺序拿锁**（先 a 再 b，谁都不许反过来），或者干脆只用一把锁把整段工作包住。

## 锁文件还在，不代表锁还在 {#misconceptions}

**"看到 `.lock` 文件，就说明有人正在写。"** 不一定。POSIX 上的 filelock 释放锁后会把锁文件留在磁盘上；Windows 版本会尝试删掉它。上面 `locked.py` 的输出就是 Windows 的结果：锁已经释放，文件也没了。反过来说，文件在也不等于锁被持有——它可能只是上次运行留下的。判断有没有人持锁，只能尝试拿一次（设很短的超时），不能 `exists()` 一下就算数。往锁文件里写 PID 也一样，进程崩溃后 PID 会变成陈旧信息。

**"加了锁，其他程序就必须排队。"** 只有遵守同一套协议的程序才会排队。另一个脚本直接写 `shared.log`，不知道也不理会 `shared.log.lock`，POSIX 的协商锁不会拦它。两个程序用的锁路径不一样（`shared.log.lock` 和 `report.lock`），也等于两把互不相干的锁。把 `locked.py` 里的 `with FileLock(...)` 删掉再跑，内容立刻回到交错状态——锁不会自动附在文件上。

**"锁能保证写进去的内容完整。"** 锁只安排谁先谁后，不保证一次写操作原子完成。写到一半进程崩溃、磁盘满、编码出错，文件里都可能留下半条记录。读方要看到"完整的旧内容"或"完整的新内容"，通常先写临时文件，再用 `os.replace()` 替换目标文件；在同一个文件系统内，这个名字切换比原地写安全得多，读方通常不会看到半截内容。需要掉电也不丢，还要在替换前 `flush()` + `fsync()`。

**"网络盘上的锁和本地盘一样可靠。"** 不一定。NFS、SMB 的锁由服务器实现，缓存和挂载参数都会影响结果；某些环境根本不支持 `flock`，库可能退化成"锁文件存在就算加锁"的软锁，进程崩溃后留下一个永远删不掉的锁文件，把后来者全挡住。涉及网络盘时，先在你实际使用的文件系统上验证，别只在开发机的本地盘上试。

## 该用文件锁，还是换一种协调方式 {#tradeoffs}

文件锁适合这样的场景：同一台机器上的几个本地进程要往同一个日志追加、重建同一个缓存索引、确保某个批处理只有一个实例在跑。它便宜、不用额外服务，出问题也容易查。

这些情况应该换工具：

- **数据库里的一致性**用事务。文件锁管不了多行更新，也回滚不了失败的一半。
- **多台机器之间**用数据库行锁、Redis 租约锁或队列。文件锁跨不了机器。
- **写得很频繁**时，串行化本身会成为瓶颈。让一个进程专门写，其他进程把消息发进队列，通常比抢锁更快，也更容易做批量写。
- **需要原子发布**时，锁配合临时文件 + `os.replace()`，而不是直接改目标文件。

真要上锁，守住几条：锁路径用稳定的绝对路径，所有参与者写死同一个；临界区尽量短，把计算和网络请求放到拿锁之前；一定要设超时，并给超时一个明确的处理（跳过、稍后重试、报警）；锁保护的是数据文件，就把锁文件放在它旁边，别让相对路径跟着工作目录漂。

## 练习：锁的范围与顺序 {#self-check}

**第 1 题**：`race.py` 里为什么必须有 `if __name__ == "__main__":`？删掉会怎样？

> **答案**
>
> Windows 用 spawn 启动子进程，子进程会重新导入主模块。没有这个判断，子进程导入时又会执行创建进程的代码，继续生出子进程，最终报错或失控。
>
> 把创建进程和写文件的调用都放在这个判断下面，子进程只定义函数，不会重复启动。

**第 2 题**：两个进程用 `FileLock("report.lock")` 保护 `report.txt`，第三个进程直接 `open("report.txt", "a")` 写入。第三个进程会被挡住吗？

> **答案**
>
> 不会。文件锁是协商的，第三个进程没有申请 `report.lock`，操作系统不会替它检查。
>
> 要挡住它，第三个进程也必须使用同一个锁路径，并且在打开数据文件之前拿锁。锁路径不一致时，即使都用了 `filelock`，也保护不到一起。

**第 3 题**：进程 1 先锁 `a.lock` 再锁 `b.lock`，进程 2 反过来。两边都不设超时，会怎样？怎么改？

> **答案**
>
> 典型的死锁：进程 1 持有 a 等 b，进程 2 持有 b 等 a，两边都不释放，永远等下去。
>
> 改法有三种：所有进程统一按 `a.lock` → `b.lock` 的顺序拿；把两把锁合并成一把；或者给每次等待设超时并放弃重试。超时能避免永久卡死，但如果两边都超时后立刻重试，仍可能反复撞车。

## 继续阅读：文件、事务与上下文 {#related}

- [文件、路径与资源生命周期](/learn/python-files)
- [上下文管理器：把进入与退出配对](/learn/context-manager)
- [数据库事务：一致完成状态转换](/learn/db-transaction)
- [线程池：受控执行阻塞工作](/learn/thread-pool)

## 参考资料与版本 {#sources}

- [filelock tutorial](https://py-filelock.readthedocs.io/en/latest/)；作者：filelock contributors；Unlicense。版本：导入日网页快照; sha256:d35da14ac06904caaf1f1252d8281a3170ff79919e609ffe79cf3c228c12d541。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
