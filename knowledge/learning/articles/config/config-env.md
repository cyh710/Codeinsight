# 环境配置：把部署差异移出代码

## 三个环境，一份代码 {#overview}

学完这一篇，你能把地址、超时和密钥从代码里挪出去，让程序在配置缺失时立刻停下。

本地调试时接口在 `127.0.0.1:8020`，测试环境是 `10.0.3.12:8020`，线上是 `https://api.shop.example`。三个地址，同一份代码。

把地址写死在代码里，发布前就得改一行，改完还得记得改回去。更糟的是测试：跑单元测试时会真的连到那个地址的接口，删一条数据就是真的删了。地址、端口、开关、密钥，这类"换个环境就该换"的东西，都不该长在代码里。

环境变量就是给进程准备的一排外部值。代码读它，同一份代码换一组值就能在另一个环境跑。

## 用环境变量读地址 {#example}

新建 `settings_v1.py`：

```python
import os

api_url = os.environ.get("SHOP_API_URL", "http://127.0.0.1:8020")
timeout = float(os.environ.get("SHOP_TIMEOUT", "10"))
print("api_url =", api_url)
print("timeout =", timeout)
```

直接运行：

```bash
python settings_v1.py
```

你应该看到：

```
api_url = http://127.0.0.1:8020
timeout = 10.0
```

两个变量都没设，所以用了默认值。现在临时给这个进程一组新值。

Linux、macOS 或 Git Bash：

```bash
SHOP_API_URL=https://api.example.com SHOP_TIMEOUT=3 python settings_v1.py
```

PowerShell：

```powershell
$env:SHOP_API_URL = "https://api.example.com"
$env:SHOP_TIMEOUT = "3"
python settings_v1.py
```

两种写法的结果一样：

```
api_url = https://api.example.com
timeout = 3.0
```

拆开看这几行。`os.environ` 是当前进程的环境变量表，键和值都是字符串。`.get("SHOP_API_URL", 默认值)` 在变量不存在时返回默认值，存在时返回字符串。`float(...)` 负责把 `"3"` 变成 `3.0`，后面的代码拿到的才是数字，而不是一个看起来像数字的字符串。

`SHOP_TIMEOUT=3 python ...` 这种前缀写法只对这一次启动生效，退出就没了。PowerShell 里的 `$env:` 赋值会影响当前终端会话，后面启动的进程都会继承；要清掉可以用 `Remove-Item Env:SHOP_TIMEOUT`。

新开的终端不会看到另一个终端里设的变量——**环境是进程自己的**，不是全局配置。

## 缺了就启动失败 {#fail-fast}

有默认值的变量好办。必需的值不一样：缺了就不该假装没事。新建 `settings_v2.py`：

```python
import os


def require(name):
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(f"缺少必需的环境变量：{name}")
    return value


api_url = require("SHOP_API_URL")
timeout = float(os.environ.get("SHOP_TIMEOUT", "10"))
print(f"连接 {api_url}，超时 {timeout:g} 秒")
```

不设 `SHOP_API_URL`，直接跑 `python settings_v2.py`，终端末尾一行是：

```
RuntimeError: 缺少必需的环境变量：SHOP_API_URL
```

完整输出里还有文件路径和行号，进程以非零状态退出。设好再跑：

```bash
SHOP_API_URL=https://api.example.com SHOP_TIMEOUT=3 python settings_v2.py
```

```
连接 https://api.example.com，超时 3 秒
```

**启动即失败**比"服务起来了，第一个请求才炸"好。后者的问题是你得等流量进来才知道，日志里可能只留下一句"连接失败"，连缺的是哪个变量都看不出。

数字也一样。`float("abc")` 会抛 `ValueError`，但报错信息是英文的、不带字段名。生产代码通常包一层：

```python
try:
    timeout = float(os.environ.get("SHOP_TIMEOUT", "10"))
except ValueError:
    raise RuntimeError("SHOP_TIMEOUT 必须是数字，例如 10") from None
```

`from None` 只是别把原始异常链一起打印出来，让报错停在"哪个配置写错了"这一层。

## .env 只留给本地 {#dotenv}

每开一个终端都手打一串环境变量太麻烦。本地项目常用一个 `.env` 文件：

```
SHOP_API_URL=http://127.0.0.1:8020
SHOP_TIMEOUT=10
SHOP_API_KEY=
```

三行分别是地址、超时和一个留给本地的密钥占位。读它需要 `pip install python-dotenv`，代码里加两行：

```python
from dotenv import load_dotenv

load_dotenv()   # 只把文件里的值补进当前进程，已有环境变量优先
```

`load_dotenv()` 默认不覆盖已经存在的环境变量，所以命令行里临时设的值仍然优先。这正合适：`.env` 提供本地的默认，命令行负责一次性覆盖。

**`.env` 绝不能提交。** 里面迟早会出现真实的数据库密码或 API key。提交过一次，就算下一个 commit 删掉，它还在历史里；克隆仓库的人、CI 的缓存、代码扫描工具都拿得到。

在 `.gitignore` 里写：

```
.env
.env.*
!.env.example
```

`!.env.example` 是例外：这个文件要提交。它写给"刚克隆仓库的人"看，只放变量名和安全示例值，不放真实密钥：

```
SHOP_API_URL=http://127.0.0.1:8020
SHOP_TIMEOUT=10
SHOP_API_KEY=
```

它告诉别人要填哪几个变量：复制成 `.env` 再改值；`SHOP_API_KEY` 本地可以留空，线上由部署环境注入。

已经有 `.env` 被提交过，加进 `.gitignore` 不会把它从历史里删掉。先把它移出版本库，再**把里面的密钥全部换掉**——历史泄露过的密钥要当成已泄露处理。

线上不要依赖仓库里的 `.env`。部署平台把变量注入进程环境，代码只负责读。这样密钥可以集中轮换，也不用把它跟代码一起打包。

## 集中定义，转成类型 {#typed-settings}

`os.getenv` 散落在十几个文件里，麻烦会慢慢出现：不知道一共有哪些配置，默认值各处不一致，改一个名字要全局搜索。

把配置收进一个类。新建 `settings_typed.py`：

```python
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_url: str
    timeout: float

    @classmethod
    def from_env(cls):
        return cls(
            api_url=os.environ.get("SHOP_API_URL", "http://127.0.0.1:8020"),
            timeout=float(os.environ.get("SHOP_TIMEOUT", "10")),
        )


settings = Settings.from_env()
print(settings)
print(settings.timeout * 2)
```

运行：

```bash
python settings_typed.py
```

你应该看到：

```
Settings(api_url='http://127.0.0.1:8020', timeout=10.0)
20.0
```

`from_env` 是唯一读环境变量的地方。类型转换在这里完成，后面的业务代码拿到的 `settings.timeout` 已经是 `float`，不需要再问"这个值会不会是字符串"。

`frozen=True` 让这个对象创建后不能被改。配置在启动时定下来，运行中有人改了一个字段，行为会变得很难复现。

业务函数该接收 `Settings` 或其中的具体值，而不是自己再 `os.getenv` 一次：

```python
def make_client(settings: Settings):
    return HttpClient(base_url=settings.api_url, timeout=settings.timeout)
```

这样测试传一个 `Settings(api_url="http://test", timeout=1)` 就行，不用动环境变量。

字段多、需要逐字段校验时，可以换成 `pydantic-settings`（`pip install pydantic-settings`）：字段类型写在类上，缺失或格式错误时它一次性列出所有问题，而不是在第一个 `float()` 处停下。小项目用上面的 dataclass 就够了。

## 四件和配置有关的错事 {#pitfalls}

**"字符串 `'false'` 是假值。"** 不是。非空字符串在 Python 里一律为真：

```python
print(bool("false"))     # True
print(bool("0"))         # True
```

所以 `if os.environ.get("DEBUG", "false"):` 永远进得去，哪怕值就是 `"false"`。自己写一个解析函数，只认明确的值：

```python
def as_bool(raw, default=False):
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


print(as_bool("false"), as_bool("0"), as_bool(None))
```

输出：

```
False False False
```

**"改了环境变量，正在跑的服务会跟着变。"** 不会。进程启动时继承一份环境，之后的读取都在自己的内存里。要让新值生效，得重启进程。有些框架提供热重载，那是它额外做的，不是环境变量的行为。

**"把整个 settings 打进日志方便排查。"** 里面可能有 `api_key`、数据库密码。日志会被收集、转发、长期保存，能看到日志的人通常比能看到数据库的人多。要记录就只挑安全字段，比如 `api_url` 和 `timeout`；密钥连前缀都不要打。

**"有默认值总比没有强。"** 默认值只适合本地。生产缺了数据库地址，默认到 `127.0.0.1` 不会报错，而是连到本机一个不存在的库，或者更糟——连到本机另一个服务。区分两类配置：本地可用的公开默认（端口、超时），和缺失必须失败的必需项（数据库地址、密钥）。

## 密钥、默认值和开关数量 {#tradeoffs}

密钥不进代码、不进日志、不进错误信息。它在本地可以放 `.env`，在线上由部署环境或密钥管理服务注入。轮换密钥时只改注入的值，不改代码。

默认值要能说明适用条件。超时默认 10 秒，写在字段旁边加一句注释就够了；数据库地址默认 `127.0.0.1`，只在本地开发成立，线上必须显式给值。把这两种混在一起，是配置事故的常见来源。

开关不是越多越好。每加一个布尔开关，可能的运行组合就翻一倍，测试覆盖不过来。能从已有配置推出来的值就别单独设：有了 `ENV=production`，就不需要再单独加一个 `USE_HTTPS`。确实要开关，就写清它控制哪一段行为、默认值是什么、什么时候可以删。

公开默认值、敏感配置、用户业务数据，这三类要分开管。前两类属于部署配置，第三类属于数据库；把用户数据塞进环境变量，改一次要重启整个服务。

## 练习 {#self-check}

**第 1 题**：`DEBUG = os.environ.get("DEBUG", "false")`，然后 `if DEBUG:`。为什么这个判断总是成立？怎么改？

> **答案**
>
> 环境变量读出来是字符串。`"false"` 非空，`bool("false")` 是 `True`，所以判断永远成立。
>
> 用明确的解析函数：
>
> ```python
> def as_bool(raw, default=False):
>     if raw is None:
>         return default
>     return raw.strip().lower() in {"1", "true", "yes", "on"}
>
> debug = as_bool(os.environ.get("DEBUG"))
> ```
>
> 不认识的写法落回 `False`，比"只要写了就为真"安全。

**第 2 题**：`.env` 已经加进 `.gitignore` 了，为什么还要换掉里面的密钥？

> **答案**
>
> 如果它曾经被提交过，`.gitignore` 只影响以后的提交，历史里那份还在。别人克隆仓库、查看旧 commit、或者从 CI 缓存里都能拿到。
>
> 正确顺序是：把文件移出版本库，轮换所有曾经出现在里面的密钥，再检查历史里有没有其他配置文件泄露。

**第 3 题**：为什么配置应该在启动时读一次，而不是在每个模块里随手 `os.getenv`？

> **答案**
>
> 随手读有两个问题：一是同一个变量在不同模块里可能用了不同的默认值，出了问题不知道以哪处为准；二是校验分散，缺了值可能在处理某个请求时才炸。
>
> 启动时集中读取、转换、校验，失败就退出。之后传 `Settings` 对象，测试也能直接构造，不用改进程环境。

## 继续阅读 {#related}

- [结构化日志：记录可以关联的事件](/learn/structured-logging)
- [类型注解：把接口约定写出来](/learn/python-annotations)
- [依赖注入：把需要的能力交进来](/learn/dependency-injection)

## 参考资料 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
- [FastAPI：依赖注入与安全](https://fastapi.tiangolo.com/tutorial/dependencies/)；作者：Sebastián Ramírez and contributors；MIT。版本：导入日网页快照; sha256:ae1f492784c1ccdc3f7f85f358c3f217f710fc4993ea3759561509601a131d04。
