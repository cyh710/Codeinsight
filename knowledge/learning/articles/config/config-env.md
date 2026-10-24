# 环境配置：把部署差异移出代码

## 先建立直觉 {#overview}

配置描述程序在不同环境下使用什么地址、路径和选项。环境变量允许同一份代码在本地、测试和部署环境使用不同值。配置不是随处读取字符串的借口，应集中定义类型、默认值和必需项。

## 原理与执行过程 {#mechanism}

进程启动时获得环境，配置层读取并校验，再把明确值交给业务模块。环境变量原始值通常是字符串，因此数字、布尔和路径需要解析。密钥应避免写入版本库、日志或索引。默认值应能说明适用条件，不能把测试默认地址误当生产地址。

## 跟着例子理解 {#example}

```python
import os
timeout = float(os.environ.get("APP_TIMEOUT", "10"))
api_url = os.environ.get("APP_API_URL", "http://127.0.0.1:8020")
print(timeout)
```

## 一步一步读懂 {#walkthrough}

读取 APP_TIMEOUT，缺失时采用 10，再转换为数字。若内容不是数字，这段代码会明确失败，真实配置层应给出字段级错误。api_url 使用本地默认地址，仅适合相应运行方式。程序启动后修改另一个终端的环境，不会自动更新既有进程。

## 常见误解 {#pitfalls}

字符串 'false' 在普通 Python 真值判断中仍为真。配置变化不一定自动重载。把完整 settings 打进日志可能泄露密钥。被分析仓库的 .env 不应因为索引方便就被扫描进入知识或代码库。

## 工程中的取舍 {#tradeoffs}

集中配置便于审计和测试，但过多开关会形成难以覆盖的组合。能从其他配置可靠推导的值不必重复维护。敏感配置、公开默认值和用户业务数据需要分开管理。

## 接着探索 {#related}

- [结构化日志：记录可以关联的事件](/learn/structured-logging)
- [类型注解：把接口约定写出来](/learn/python-annotations)

## 来源与版本 {#sources}

- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
- [FastAPI：依赖注入与安全](https://fastapi.tiangolo.com/tutorial/dependencies/)；作者：Sebastián Ramírez and contributors；MIT。版本：导入日网页快照; sha256:ae1f492784c1ccdc3f7f85f358c3f217f710fc4993ea3759561509601a131d04。
