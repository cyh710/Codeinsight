# 抽象基类与协议：约定可以替换的能力

## 换一个存储要改多少行 {#overview}

读完这一篇，你能让上层代码只认一份接口，换存储时不再改调用方。

小林的留言工具一开始把数据放在内存里，重启就丢。后来要落盘，他把内存存储换成文件存储，结果调用处、测试、类型标注全要跟着改。再后来测试又想把文件换回内存，改动再来一遍。

问题不在于“用哪个存储”，而在于上层函数直接认了某一个具体类。它知道内部字段叫 `notes`，知道数据怎么放，换一个实现就散架。

接口要做的事是：上层只调用 `save` 和 `load_all`，具体是内存、文件还是数据库，由外面决定。名字对上只是第一步，行为也得对上。

## 先写死内存存储 {#hardcoded}

新建 `hardcoded.py`，先看没有接口时最容易写出的版本：

```python
class MemoryStore:
    def __init__(self):
        self.notes = []

    def save(self, text):
        self.notes.append(text)


class FileStore:
    def __init__(self, path):
        self.path = path

    def save(self, text):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def latest_note(store: MemoryStore):
    return store.notes[-1] if store.notes else None


memory = MemoryStore()
memory.save("买牛奶")
print("内存：", latest_note(memory))

open("notes.txt", "w", encoding="utf-8").close()
file_store = FileStore("notes.txt")
file_store.save("交房租")
try:
    latest_note(file_store)
except AttributeError as exc:
    print("文件：", exc)
```

运行 `python hardcoded.py`：

```
内存： 买牛奶
文件： 'FileStore' object has no attribute 'notes'
```

`FileStore` 明明也有 `save`，为什么一换就炸？因为 `latest_note` 不只用 `save`，它还伸手进了 `store.notes`。这是内部字段，不是两个存储共同承诺的能力。

类型标注 `store: MemoryStore` 也没有拦住调用。Python 运行时不会因为标注不匹配就拒绝执行，它照样把 `FileStore` 传进去，直到访问 `.notes` 才抛出 `AttributeError`。

这段代码的耦合点写得很具体：`latest_note` 依赖 `MemoryStore` 的内部结构。换存储时，你得改函数体，而不只是换一行构造。

## 把共同能力抽成 ABC {#abc-interface}

`abc` 模块提供的抽象基类，可以把“必须实现哪些方法”写进类型里：

```python
from abc import ABC, abstractmethod


class NoteStore(ABC):
    @abstractmethod
    def save(self, text: str) -> None:
        ...

    @abstractmethod
    def load_all(self) -> list[str]:
        ...


class HalfStore(NoteStore):
    def save(self, text: str) -> None:
        print("保存", text)


try:
    HalfStore()
except TypeError:
    print("HalfStore 少实现一个抽象方法，实例化就被拒绝")


class MemoryStore(NoteStore):
    def __init__(self) -> None:
        self._notes: list[str] = []

    def save(self, text: str) -> None:
        self._notes.append(text)

    def load_all(self) -> list[str]:
        return list(self._notes)


print("完整实现的类可以实例化：", type(MemoryStore()).__name__)
```

输出：

```
HalfStore 少实现一个抽象方法，实例化就被拒绝
完整实现的类可以实例化： MemoryStore
```

`HalfStore` 的类定义本身不报错。Python 允许你声明一个不完整的子类，报错发生在 `HalfStore()` 这一刻：`TypeError`，因为 `load_all` 还是抽象的。

这个时机很关键。不用等到程序跑了一半、调用 `load_all` 才发现没实现，构造对象时就被挡住。

`MemoryStore` 两个方法都实现了，才能实例化。`_notes` 变成了内部细节，外部只通过 `save` 和 `load_all` 打交道。

ABC 还能放共享代码。比如两个实现都要做空文本检查，可以把检查写在基类的普通方法里，抽象方法只留真正需要替换的部分。共享代码越多，继承越有用；只是声明方法名，协议往往更轻。

## 不继承也能满足协议 {#protocol}

`typing.Protocol` 走另一条路：不要求显式继承，只看对象有没有需要的方法。新建 `notes.py`：

```python
from typing import Protocol


class NoteStore(Protocol):
    def save(self, text: str) -> None: ...
    def load_all(self) -> list[str]: ...


class MemoryStore:
    def __init__(self) -> None:
        self._notes: list[str] = []

    def save(self, text: str) -> None:
        self._notes.append(text)

    def load_all(self) -> list[str]:
        return list(self._notes)


class FileStore:
    def __init__(self, path: str) -> None:
        self.path = path

    def save(self, text: str) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def load_all(self) -> list[str]:
        try:
            with open(self.path, encoding="utf-8") as f:
                return [line.rstrip("\n") for line in f]
        except FileNotFoundError:
            return []


def add_note(store: NoteStore, text: str) -> None:
    store.save(text)


def latest_note(store: NoteStore) -> str | None:
    notes = store.load_all()
    return notes[-1] if notes else None


memory = MemoryStore()
add_note(memory, "买牛奶")
add_note(memory, "交房租")
print("内存存储最新：", latest_note(memory))

open("notes.txt", "w", encoding="utf-8").close()
file_store = FileStore("notes.txt")
add_note(file_store, "买牛奶")
add_note(file_store, "交房租")
print("文件存储最新：", latest_note(file_store))
```

运行 `python notes.py`：

```
内存存储最新： 交房租
文件存储最新： 交房租
```

`MemoryStore` 和 `FileStore` 都没有写 `class X(NoteStore)`。它们只是碰巧都有 `save` 和 `load_all`，于是满足 `NoteStore` 这个结构约定。

`add_note` 和 `latest_note` 只调用协议里的方法。换存储时改的是 `MemoryStore()` 还是 `FileStore("notes.txt")` 这一处构造，函数不用动。

`save` 和 `load_all` 后面是 `...`，不是 `pass`。它们在协议里只描述签名，不提供实现；协议类本身也不能实例化。

静态类型检查器会读取 `store: NoteStore` 这样的标注，检查传入对象的方法和参数。Python 解释器运行时不看这些标注，所以 `notes.py` 能跑，不代表类型检查一定通过；反过来，类型检查通过，也不代表运行时行为一定符合约定。

## runtime_checkable 只看方法名 {#runtime-checkable}

默认的 `Protocol` 不能拿来做 `isinstance` 检查，会抛 `TypeError`。加上 `@runtime_checkable` 可以检查，但检查很浅：

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class Store(Protocol):
    def save(self, text: str) -> None: ...
    def load_all(self) -> list[str]: ...


class WrongStore:
    def save(self) -> None:
        pass

    def load_all(self) -> list[str]:
        return []


obj = WrongStore()
print("通过 isinstance：", isinstance(obj, Store))
try:
    obj.save("这条会报错")
except TypeError:
    print("调用时才炸：save 不接受 text")
```

输出：

```
通过 isinstance： True
调用时才炸：save 不接受 text
```

`WrongStore.save` 少了一个参数，`isinstance` 仍然返回 `True`。运行时检查只确认对象身上有没有叫 `save` 和 `load_all` 的属性，不看参数个数、类型、返回值，更不看方法内部做了什么。

真正调用 `obj.save("这条会报错")` 时，Python 才发现 `save` 只接受 `self`，于是抛 `TypeError`。

所以 `runtime_checkable` 适合做粗筛：这个对象是不是大概像那么回事。它不能替代测试，也不能替代静态类型检查。

## 同名方法，含义可能相反 {#semantics}

两个类都实现了 `save` 和 `load_all`，类型标注都写 `list[str]`，替换后仍然可能出错：

```python
class MemoryStore:
    def __init__(self) -> None:
        self._notes: list[str] = []

    def save(self, text: str) -> None:
        self._notes.append(text)

    def load_all(self) -> list[str]:
        return list(self._notes)


class NewestFirstStore:
    def __init__(self) -> None:
        self._notes: list[str] = []

    def save(self, text: str) -> None:
        self._notes.insert(0, text)

    def load_all(self) -> list[str]:
        return list(self._notes)


def latest_note(store) -> str | None:
    notes = store.load_all()
    return notes[-1] if notes else None


for store in (MemoryStore(), NewestFirstStore()):
    store.save("买牛奶")
    store.save("交房租")
    print(type(store).__name__, "->", latest_note(store))
```

输出：

```
MemoryStore -> 交房租
NewestFirstStore -> 买牛奶
```

两次输入完全一样，`latest_note` 也一样，结果却相反。因为 `MemoryStore` 的 `load_all` 按“旧到新”返回，`NewestFirstStore` 按“新到旧”返回。方法名和类型都没问题，**顺序的含义**变了。

接口约定要写清这类事，而不是只写方法名：

| 问题 | 两个实现可能给出不同答案 |
|---|---|
| `load_all` 的顺序 | 旧到新、新到旧、按主键、未定义 |
| 空结果 | 返回空列表、返回 `None`、抛异常 |
| 文件或记录不存在 | 当成空、抛 `FileNotFoundError` |
| 返回值是否共享内部数据 | 副本、还是内部列表本身 |
| 什么时候算保存成功 | 写进内存、写进缓冲区、还是落盘 |
| 多线程同时调用 | 安全、需要加锁、直接损坏 |
| 谁负责关闭资源 | 调用方、实现自己、进程退出时 |

`list[str]` 只说了“里面是字符串”，没说顺序、没说空值怎么表示、没说错误行为。这些得写进文档，或者用测试固定下来。换实现时，跑同一组不变量测试，才有资格说“可替换”。

## 四种“看起来能替换”的假象 {#pitfalls}

**“继承了 ABC，两个实现就能互换。”** 继承只保证方法被实现，不保证语义一致。顺序、错误、空结果、线程安全都可能不同，`MemoryStore` 和 `NewestFirstStore` 就是反例。

**“Protocol 会在运行时检查参数和返回值。”** 默认不检查；加了 `@runtime_checkable` 也只检查属性名。`WrongStore.save` 少一个参数照样通过 `isinstance`，真正调用才报错。

**“接口方法越多，约定越完整。”** 方法越多，每个实现要背的行为越多，替换成本越高。窄接口只包含上层真正需要的能力，比如“保存一条”和“读出全部”，别把删除、搜索、分页、统计全塞进来。

**“类型注解就是契约。”** 注解能帮静态检查器发现一部分不匹配，不能阻止运行时传错对象，也不能表达顺序、幂等、资源归属。注解是契约的一部分，不是全部。

## 抽象的成本从哪来 {#tradeoffs}

抽象不是免费的。多一层接口就多一层跳转，读代码时要从调用点跳到协议，再跳到实现；每加一个方法，所有实现和测试替身都要跟着改。只有一个实现时，这层结构常常只是负担。

值得抽的情形通常有具体信号：现在就有两个实现（内存用于测试、文件用于生产）；边界外面是会换的东西（存储、模型服务、解析器）；调用点很多，需要统一约束；你想用假实现替换外部依赖来跑测试。

不值得的情形也很具体：只有一个实现，近期也没有第二个；脚本只有几十行；每个函数都要建一个类层次，读一个流程要跳七个文件。这时一个普通函数参数就够了，不必为了“面向接口”提前造抽象。

接口要窄，语义要写下来。一个 `NoteStore` 只有 `save` 和 `load_all`，比一个包含十几个方法的 `Repository` 容易实现，也容易测。把顺序、空值、异常、线程安全、资源归属写进 docstring，再用测试固定住，替换才有依据。

读别人的代码时，看到一个接口，先找它的实现有几个、每个实现的行为差在哪里。只有一个实现、也没有测试替身时，这层抽象可能只是包装；有多个实现时，差异点就是最容易出事的地方。

## 练习 {#self-check}

**第 1 题**：一个子类继承了 `ABCMeta` 的基类，但漏实现一个 `@abstractmethod`。错误发生在定义类的时候，还是实例化的时候？

> **答案**
>
> 实例化的时候。类定义可以正常通过，`SubClass()` 才抛 `TypeError`，提示还有抽象方法没实现。这个设计让你能先声明不完整的子类，但不让不完整的对象被创建。

**第 2 题**：`@runtime_checkable` 的 `isinstance(obj, Store)` 返回 `True`，能不能说明 `obj` 真的符合 `Store`？

> **答案**
>
> 不能。它只检查 `save`、`load_all` 这些属性是否存在。参数签名、返回类型、顺序、异常行为都不在检查范围内。上面的 `WrongStore` 就是通过检查、调用时报错的例子。真正的验证要靠静态类型检查和不变量测试。

**第 3 题**：两个存储都实现了 `load_all() -> list[str]`，一个按旧到新返回，一个按新到旧返回。上层函数 `latest_note` 取列表末尾那一项。怎么让替换不出错？

> **答案**
>
> 要么把顺序写进接口约定，要求两个实现都按同一种顺序返回，并用测试固定；要么让上层不猜顺序，改用显式接口，比如返回带时间戳的记录再排序。只靠方法名和 `list[str]` 的注解不够：两种实现都能通过类型检查，却给出不同结果。

## 继续阅读 {#related}

- [依赖注入：把需要的能力交进来](/learn/dependency-injection)
- [类型注解：把接口约定写出来](/learn/python-annotations)
- [类、实例与继承](/learn/python-classes)
- [ORM：用对象操作数据库](/learn/orm)

## 参考资料 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
