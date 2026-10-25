# 装饰器：在定义时包装行为

## 函数被换掉了 {#overview}

学完这一篇，你能写出装饰器，知道 @ 在什么时候执行，为什么必须加 functools.wraps，也能看懂框架里的路由注册。

小林给三个函数都加了同样的打印：进来时打参数，出去时打结果。写到第四个函数，他发现自己又在复制粘贴。

他想要一个函数：接收另一个函数，返回一个"带打印功能"的新函数。原来的函数一行不改，只要在定义时套一下。

这个"套一下"就是装饰器。它不在原函数里插代码，而是在定义时**用一个新对象把原函数换掉**。名字还叫 `add`，但调用时执行的已经不是原来那个 `add` 了。

## 最朴素的 log_calls 把函数换掉了 {#example}

新建 `log_demo.py`：

```python
def log_calls(fn):
    def wrapper(*args, **kwargs):
        print("调用", fn.__name__, args)
        result = fn(*args, **kwargs)
        print("返回", result)
        return result
    return wrapper


@log_calls
def add(a, b):
    return a + b


print("add 现在是:", add.__name__)
print(add(2, 3))
```

```bash
python log_demo.py
```

你应该看到：

```
add 现在是: wrapper
调用 add (2, 3)
返回 5
5
```

逐行看发生了什么事。

第一步，Python 先执行 `def add(...)`，造出原来的加法函数对象。此时还没有任何打印。

第二步，`@log_calls` 把刚才那个函数对象交给 `log_calls`。`log_calls` 定义了内层 `wrapper`，返回它。`wrapper` 里引用了外层的 `fn`，所以即使 `log_calls` 已经返回，`fn` 也不会消失——这就是闭包。

第三步，装饰器的返回值重新绑定给名字 `add`。等价写法是：

```python
def add(a, b):
    return a + b

add = log_calls(add)
```

所以此刻 `add` 已经指向 `wrapper`，原来的加法函数只被 `wrapper` 的闭包拿着。

第四步，`add(2, 3)` 实际调用 `wrapper(2, 3)`。`wrapper` 打印 `fn.__name__`（原函数名，仍然是 `add`）和参数，调用原函数，打印结果，再把结果返回给调用方。

这也解释了第一行输出：`add.__name__` 现在是 `"wrapper"`，因为名字 `add` 指向的函数对象叫 `wrapper`。原函数的名字没变，只是外面套了一层。

`wrapper` 接收 `*args, **kwargs` 再原样转交，有两个原因：

- 不接受这两个，装饰器只能用于固定参数个数的函数；`add(a, b)` 能用，改成 `add(a, b, c)` 就报错。
- 不 `return` 原函数的结果，调用方拿到的就是 `None`。比如把 `return result` 删掉，末尾那行输出会从 `5` 变成 `None`。

`*args, **kwargs` 转发参数，`return` 转发返回值，这两件事是包装函数的基本义务。少一样，装饰器就会改变原函数的行为。

## 不加 wraps 会丢掉什么 {#wraps}

上面的 `add.__name__` 变成了 `wrapper`，`__doc__` 也没了。对一个只跑一次的脚本无所谓；对框架和调试工具，这是实打实的问题。

```python
import functools
import inspect


def plain(fn):
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper


def wrapped(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper


@plain
def add(a, b):
    """把两个数加起来。"""
    return a + b


@wrapped
def plus(a, b):
    """把两个数加起来。"""
    return a + b


print(add.__name__, add.__doc__)
print(plus.__name__, plus.__doc__)
print(inspect.signature(add))
print(inspect.signature(plus))
```

你应该看到：

```
wrapper None
plus 把两个数加起来。
(*args, **kwargs)
(a, b)
```

`functools.wraps(fn)` 把原函数的 `__name__`、`__doc__`、`__module__`、`__qualname__`、`__annotations__` 复制到 wrapper 上，还设置 `__wrapped__` 指向原函数。`inspect.signature` 默认会沿着 `__wrapped__` 找到原函数，所以它看到的是 `(a, b)`，不是 wrapper 的 `(*args, **kwargs)`。

这不是"好看一点"的问题。FastAPI 这类框架靠函数签名判断参数、类型和依赖；Flask 在注册路由时用函数名做 endpoint；日志和 APM 用 `__name__` 区分调用。没有 `wraps`，它们看到的是一个叫 `wrapper`、签名为 `(*args, **kwargs)` 的陌生函数。

**`wraps` 只改元数据，不改行为。** 它不会让 wrapper 真的变成原函数，也不会检查参数。参数校验、异常、返回值仍然由 wrapper 的代码决定。如果你在 wrapper 里改了语义，`wraps` 只是在帮它"伪装"成原函数；这种伪装要诚实，不能拿来掩盖不兼容的改动。

另外，`@functools.wraps(fn)` 写在 wrapper 定义上方，不是在装饰器外层。它作用于 wrapper，把原函数的信息抄过来。

## 带参数的装饰器要多一层 {#params}

`@log_calls` 直接收函数。想要 `@log_with("[账本]")` 这种带配置的形式，就得在中间再塞一层：

```python
import functools


def log_with(prefix):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            print(prefix, "调用", fn.__name__)
            return fn(*args, **kwargs)
        return wrapper
    return decorate


@log_with("[账本]")
def add(a, b):
    return a + b


print(add(2, 3))
```

输出：

```
[账本] 调用 add
5
```

三层各自负责什么：

| 层 | 收什么 | 什么时候执行 | 返回什么 |
|---|---|---|---|
| `log_with(prefix)` | 装饰器的参数 | 读到 `@log_with("[账本]")` 时 | 一个装饰器 `decorate` |
| `decorate(fn)` | 被装饰的函数 | 紧接着，作用到 `add` 上 | 包装函数 `wrapper` |
| `wrapper(a, b)` | 调用时传的参数 | 每次调用 `add` 时 | 原函数的结果 |

`@log_with("[账本]")` 先求值括号里的调用，得到 `decorate`；再用 `decorate` 去装饰 `add`。等价写法：

```python
add = log_with("[账本]")(add)
```

常见的错误是少写一层 `return`。`decorate` 忘了 `return wrapper`，`add` 就变成 `None`；`log_with` 忘了 `return decorate`，`@log_with("[账本]")` 求值得到 `None`，再拿它套 `add` 会报 `TypeError: 'NoneType' object is not callable`。还有个更隐蔽的：`@log_with` 没写括号，Python 把被装饰的函数当成了 `prefix`，返回的 `decorate` 成了新的 `add`，装饰行为整个错位，错误往往拖到调用阶段才出现。

## 把函数注册进字典 {#registry}

装饰器不一定返回 wrapper。它只要接收函数、返回一个对象就行；返回原函数也是一种合法选择。

```python
ROUTES = {}


def route(path):
    def register(fn):
        ROUTES[path] = fn
        return fn
    return register


@route("/total")
def total():
    return "总价 42 元"


@route("/hello")
def hello():
    return "你好"


print(sorted(ROUTES))
print(ROUTES["/total"]())
```

输出：

```
['/hello', '/total']
总价 42 元
```

这里没有任何包装。`register` 做的事是：把 `path` 和函数对象存进 `ROUTES`，然后把函数原样返回。`@route("/total")` 的净效果是：

1. 把 `total` 注册到 `ROUTES["/total"]`。
2. 让名字 `total` 仍然指向原来的函数，没有被替换。

真正的调用发生在后面：`ROUTES["/total"]()` 从字典里取出函数再调用。框架处理请求时，也是拿 URL 去路由表里查函数。

这就是 Web 框架路由的雏形。Flask 的 `@app.route("/total")`、FastAPI 的 `@app.get("/total")` 都在做同一类事：把"路径 → 函数"记到一张表里，等请求来了再查表。`@` 在这里的用途不是"增强函数行为"，而是**在定义时产生一次注册副作用**。

注册型装饰器有两个坑：

- **忘了 `return fn`。** 名字会变成 `None`，注册表里可能还有函数（因为存的是 `fn`），但后面直接调用 `total()` 就崩了。
- **同名路径覆盖。** `ROUTES` 是普通字典，同一个 path 注册两次，后一个悄悄覆盖前一个。框架通常会检测并报错，自己写就要注意。

还有一点：注册发生在模块被导入时。模块没被导入，路由就不存在；这既是框架"自动发现"的原理，也是"为什么改了文件要重启"的原因。

## 两个装饰器谁先包 {#order}

再加一个装饰器，顺序就变得重要了：

```python
import functools


def first(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        print("first: 进入")
        result = fn(*args, **kwargs)
        print("first: 离开")
        return result
    return wrapper


def second(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        print("second: 进入")
        result = fn(*args, **kwargs)
        print("second: 离开")
        return result
    return wrapper


@first
@second
def add(a, b):
    print("add: 计算")
    return a + b


print(add(1, 2))
```

输出：

```
first: 进入
second: 进入
add: 计算
second: 离开
first: 离开
3
```

规则可以写成两句话：

- **包装从下往上。** 靠近 `def` 的 `@second` 先把 `add` 包住，然后 `@first` 再把 `second` 的返回值包住。等价于 `add = first(second(add))`。
- **调用从上往下。** 最外层的 `first` 先进入，也最晚离开；像剥洋葱，外层先见到请求，内层先见到原函数。

所以"最上面的装饰器先执行"这句话只对调用阶段成立，对包装阶段恰好相反。两个阶段混着说，很容易把顺序搞反。

顺序不只是打印好看不好看。假设你有缓存和登录校验：

```python
@cache
@require_login
def profile(user_id):
    ...
```

`cache` 在外层。缓存命中时，`require_login` 根本不会执行——未登录的请求也可能拿到缓存里的用户资料。反过来写：

```python
@require_login
@cache
def profile(user_id):
    ...
```

登录校验先跑，通过后才查缓存。哪个是对的，取决于缓存里存的是什么、key 里有没有用户身份；但**顺序改变行为**这件事是确定的。

再比如重试和日志。日志在外层，记录的是"包含三次重试的总耗时"；日志在内层，每次尝试各记一条。两者都能用，但含义不同。读别人的代码时，先看装饰器的上下顺序，再判断实际执行路径。

包装层数多了，控制流会被藏起来。三层装饰器叠上去，读一个调用点要同时在脑子里展开三层 wrapper；权限、事务这种必须一眼看清的边界，不适合埋在最里面。能用一个显式函数调用说清的事，不必非套 `@`；中间件和组合函数也能达到同样效果。判断标准很直接：读调用点的人，能不能不逐个跳进装饰器就说出实际执行顺序。

## 装饰发生在定义时 {#definition-time}

装饰器最容易搞混的一点：它不是在每次调用时运行。看这段：

```python
import functools


def trace(fn):
    print("装饰", fn.__name__)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        print("调用", fn.__name__)
        return fn(*args, **kwargs)

    return wrapper


@trace
def add(a, b):
    return a + b


print("定义结束")
add(1, 2)
```

输出：

```
装饰 add
定义结束
调用 add
```

"装饰 add" 打印在 "定义结束" 之前，因为 `@trace` 在模块执行到 `def add` 之后就立刻运行了。后面的 `add(1, 2)` 只触发 wrapper 里的 "调用 add"，不会再跑一遍 `trace` 的函数体。

这个时间差有几个实际后果：

- **装饰器里的错误会让导入失败。** 装饰器在读配置、连数据库、解析参数时抛出异常，程序在启动阶段就崩，不会等到第一个请求。这通常比运行时才发现好，但报错栈会指向模块导入，而不是某个接口。
- **注册表在导入时建好。** 路由、命令、插件列表都是这样收集的。模块没导入就没有条目；改完文件不重启，旧表还在。
- **装饰器只在定义时执行一次。** 循环里、请求处理函数里调用 `decorate(fn)` 是另一回事——那时你是在手动调用它。`@` 语法本身只在 `def` 或 `class` 定义处生效。
- **类也能被装饰。** `@decorator` 放在 `class` 上方时，接收的是类对象，返回值会替换类名。写法和函数一样，但包装类要考虑实例化、继承和 `isinstance`，比包装函数更容易出问题。

**"装饰器每次调用都会执行一遍。"** 不会。执行一遍的是 wrapper。装饰器函数本身在定义时跑完就退场了，它留下的 wrapper 才是每次调用时运行的东西。

静态检查工具也帮不上全部忙。它看得到 `@cache`、`@require_login` 这些名字，却不知道 wrapper 里实际做了什么；类型检查通过，不代表运行时权限检查真的执行了。读代码时，装饰器名字只是入口，行为要展开到它的实现。

## 练习：包装、注册与计数 {#self-check}

**第 1 题**：为什么 `log_demo.py` 里 `add.__name__` 是 `"wrapper"`？怎么让它变回 `"add"`？

> **答案**
>
> 因为 `@log_calls` 让名字 `add` 指向了 `wrapper` 函数对象，而 `wrapper.__name__` 默认就是 `"wrapper"`。
>
> 在 wrapper 定义上方加 `@functools.wraps(fn)`，就会把原函数的 `__name__`、`__doc__`、签名信息带过来。注意它只改元数据，实际调用的仍然是 wrapper。

**第 2 题**：`@first` 在 `@second` 上面，`add(1, 2)` 的进入和离开顺序是什么？等价的手写赋值是什么？

> **答案**
>
> 进入顺序是 first → second → 原函数；离开顺序反过来，原函数 → second → first。
>
> 等价写法是 `add = first(second(add))`。`second` 先包住原函数，`first` 再包住 `second` 返回的 wrapper。

**第 3 题**：写一个装饰器，统计函数被调用了多少次，并把次数挂在函数上，用 `add.calls` 读取。

> **答案**
>
> ```python
> import functools
>
> def counted(fn):
>     @functools.wraps(fn)
>     def wrapper(*args, **kwargs):
>         wrapper.calls += 1
>         return fn(*args, **kwargs)
>     wrapper.calls = 0
>     return wrapper
>
> @counted
> def add(a, b):
>     return a + b
>
> print(add(1, 2), add.calls)
> print(add(3, 4), add.calls)
> ```
>
> 输出：
>
> ```
> 3 1
> 7 2
> ```
>
> `calls` 挂在 wrapper 上，不是原函数上。`wrapper.calls = 0` 在装饰时设好初始值；之后每次调用，wrapper 先加 1 再转交。`functools.wraps` 复制的是原函数的元数据和原函数已有的 `__dict__`，这里原函数没有 `calls` 属性，所以不会覆盖你设的初始值。

## 继续阅读：函数与依赖注入 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [上下文管理器：把进入与退出配对](/learn/context-manager)
- [依赖注入：把依赖从外部传进来](/learn/dependency-injection)
- [单例与延迟初始化：对象只创建一次](/learn/singleton-lazy)

## 参考来源 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
