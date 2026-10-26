"""模拟容器身份，不模拟浏览器、React 或 Vite。"""


def create_state() -> dict:
    """每次返回独立容器，便于观察重建与复用的差别。"""
    return {"projects": []}


def demo() -> tuple[bool, list, bool, list]:
    """返回新建/复用两种对象身份与数据，完全在内存中运行。"""
    first = create_state()
    first["projects"].append("项目 A")
    second = create_state()
    preserved = {"state": first}
    third = preserved["state"]
    return first is second, second["projects"], first is third, third["projects"]


if __name__ == "__main__":
    print(demo())  # (False, [], True, ['项目 A'])
