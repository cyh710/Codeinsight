# 类、对象与继承

## 两张购物车互不相干 {#overview}

学完这一篇，你能写出一个带状态的类，分清实例属性和类属性，并用继承和 super() 复用已有行为。

小林在做一个团购页面。他原本用一个全局列表 `items` 记商品，两个人同时打开页面时，小李看见了自己根本没加的书。

问题不在列表，在于**两个购物车被当成了同一个**。他真正需要的是：每辆车有自己的商品清单，但操作方式一样——都能加商品、算总价。

类就是用来写这份“每辆车都长这样”的说明。

## 写出第一个 Cart {#first-cart}

新建 `cart.py`：

```python
class Cart:
    tax_rate = 0.1

    def __init__(self, owner):
        self.owner = owner
        self.items = []

    def add(self, name, price):
        self.items.append((name, price))

    def total(self):
        return sum(price for _, price in self.items)

    def payable(self):
        return round(self.total() * (1 + self.tax_rate), 2)


first = Cart("小林")
second = Cart("小李")

first.add("书", 45)

print(first.owner, first.items)
print(second.owner, second.items)
print(first.payable())
```

运行 `python cart.py`，你会看到：

```
小林 [('书', 45)]
小李 []
49.5
```

先看两辆车的状态：

| 变量 | owner | items |
|---|---|---|
| `first` | 小林 | `[('书', 45)]` |
| `second` | 小李 | `[]` |

`first.add` 只改了 `first` 的清单，`second` 还是空的。这两张购物车是两次独立创建的对象。

逐段拆开：

**`class Cart:` 只是定义。** Python 执行到这里，把 `Cart` 这个名字绑定到一个类对象上：它知道“购物车有 add、total、payable 这些方法”，但此刻还没有任何一辆车。

**`Cart("小林")` 才创建对象。** 调用类会做两件事：先造出一个新对象，再把这个新对象和 `"小林"` 一起交给 `__init__`。`self` 接到的就是那个新对象。

**`self.owner = owner` 是在对象身上挂属性。** 这行执行完，`first` 这个对象有了 `owner`，值是“小林”。`self.items = []` 则给它挂上一个空列表。

**关键是 `self.items = []` 每次创建都执行。** 第一辆车拿到一个列表，第二辆车拿到另一个列表。它们不是同一个。

**方法内部的 `self` 指向调用它的那辆车。** `first.add("书", 45)` 里，`self` 是 `first`，所以 `self.items.append(...)` 往第一辆车的清单里加。`second` 完全没参与。

`total` 里的 `_` 是一个临时名字，表示“这个位置我不关心”，这里只是不想给商品名再起一个变量。`sum(...)` 把每项的价格加起来。`payable` 再乘上税率并保留两位小数。

## self 是谁，初始化什么时候跑 {#self-and-init}

先在另一个文件里做个小实验：

```python
class Box:
    def put(self, thing):
        self.thing = thing


b = Box()
b.put("书")
print(b.thing)

Box.put(b, "本子")
print(b.thing)
```

输出：

```
书
本子
```

定义里写的是 `def put(self, thing)`。调用 `b.put("书")` 时，Python 自动把 `b` 塞给第一个参数 `self`，把 `"书"` 给 `thing`。所以 `self` 就是“这次调用针对的那个对象”。

`Box.put(b, "本子")` 和 `b.put("本子")` 是一回事。第二种写法只是语法糖：通过实例访问方法时，实例会自动补到第一个参数。

`self` 不是 Python 的关键字，也不是什么隐藏对象。你完全可以把它叫 `box`：

```python
class Box:
    def put(box, thing):
        box.thing = thing
```

能跑，但别人读起来会愣一下。`self` 是所有人默认的名字，别改。

再看 `__init__` 什么时候执行：

```python
class Cart:
    made = 0

    def __init__(self, owner):
        self.owner = owner
        self.items = []
        Cart.made += 1
        print(f"初始化 {owner} 的购物车，第 {Cart.made} 辆")


a = Cart("小林")
b = Cart("小李")
print("一共", Cart.made, "辆")
```

输出：

```
初始化 小林 的购物车，第 1 辆
初始化 小李 的购物车，第 2 辆
一共 2 辆
```

每写一次 `Cart(...)`，`__init__` 就跑一次。对象在 `__init__` 之前已经存在了，`__init__` 负责的是**初始化属性**，不是把对象从无变有。

`Cart.made += 1` 改的是类上的计数，所以两张车共用同一个数字。如果写成 `self.made += 1`，第一辆车会先读到类上的 0，然后在自己身上挂一个 `made = 1`；类上的 `made` 还是 0，第二辆车又从 0 开始，计数就错了。

`__init__` 里没设的属性，后面访问会直接报错。如果 `__init__` 忘了 `self.items = []`，`add` 里的 `self.items.append` 就会撞上 `AttributeError`。

## 类属性属于所有人 {#class-attributes}

`Cart` 里的 `tax_rate = 0.1` 写在类体中，不在 `__init__` 里。它是**类属性**：

```python
class Cart:
    tax_rate = 0.1


a = Cart()
b = Cart()

Cart.tax_rate = 0.2
print(a.tax_rate, b.tax_rate)

a.tax_rate = 0.5
print(a.tax_rate, b.tax_rate)
print(a.__dict__)
print(b.__dict__)
```

输出：

```
0.2 0.2
0.5 0.2
{'tax_rate': 0.5}
{}
```

`Cart.tax_rate = 0.2` 改的是类上的那一份，所有实例都看得见，所以两个都打印 0.2。

`a.tax_rate = 0.5` 不一样。它没有改类，而是在 `a` 自己身上新建了一个 `tax_rate`。`a.__dict__` 里多了这一项，`b.__dict__` 还是空的。之后访问 `a.tax_rate` 先用实例自己的，访问 `b.tax_rate` 才继续往上找类。

属性查找的顺序可以记成：先看实例自己的 `__dict__`，找不到再看类。

共享一个不能变的值没问题。共享一个**可变**的值就要出事了：

```python
class BadCart:
    items = []


first = BadCart()
second = BadCart()
first.items.append("书")

print(second.items)
print(first.items is second.items)
```

输出：

```
['书']
True
```

类体里的 `items = []` 只在定义类时执行一次。两个实例都没有自己的 `items`，查找时都落到类的同一个列表上。`first.items.append` 改的就是这个共享列表，`second` 自然看见了。

正确的位置是 `__init__`：

```python
class Cart:
    def __init__(self, owner):
        self.owner = owner
        self.items = []      # 每辆车一个
```

判断标准很简单：**这个值需要每个对象各有一份吗？** 需要，就写进 `__init__` 用 `self.xxx = ...`；如果它是一份所有实例都该共用的常量，才放类体。

## 继承、覆盖与 super() {#inheritance-and-super}

会员购物车也是购物车，只是总价打九折。把共用的部分继承下来：

```python
class Cart:
    def __init__(self, owner):
        self.owner = owner
        self.items = []

    def add(self, name, price):
        self.items.append((name, price))

    def total(self):
        return sum(price for _, price in self.items)


class MemberCart(Cart):
    def __init__(self, owner):
        super().__init__(owner)
        self.discount = 0.1

    def total(self):
        base = super().total()
        return round(base * (1 - self.discount), 2)


normal = Cart("小林")
member = MemberCart("阿敏")

normal.add("书", 45)
member.add("书", 45)

print(normal.total())
print(member.total())
print(member.owner, member.items)
print(isinstance(member, Cart))
```

输出：

```
45
40.5
阿敏 [('书', 45)]
True
```

`class MemberCart(Cart)` 表示会员车继承普通车。`MemberCart` 自己没有写 `add`，但 `member.add(...)` 能跑，因为 Python 在子类找不到方法时会去父类找。

`MemberCart` 写了 `__init__`，就**覆盖**了父类的同名方法。它需要父类先把 `owner` 和 `items` 建好，于是第一行调用 `super().__init__(owner)`。

`super()` 的意思是“从这个类的下一站开始找”。在 `MemberCart` 里，下一站就是 `Cart`。所以 `super().__init__(owner)` 执行的是 `Cart.__init__`，但 `self` 仍然是这个会员车对象。

`total` 也一样被覆盖了。`base = super().total()` 先拿到父类算出的 45，再乘 0.9 得到 40.5。如果不写这一句，子类只返回自己的结果，父类那段求和逻辑根本不会执行。

`isinstance(member, Cart)` 是 `True`：会员车是购物车的一种。

继承关系成立的前提是“是一个”。`MemberCart` 是一个 `Cart`，所以继承说得通。如果两个东西只是都用到了同一段代码，但没有这种从属关系，硬套继承通常会把结构弄拧。

## 三个容易想反的地方 {#pitfalls}

**“`self` 是 Python 的关键字，名字不能换。”** 能换。它只是方法的第一个参数，Python 按位置把实例传进去，不检查名字：

```python
class Box:
    def put(box, thing):
        box.thing = thing


b = Box()
b.put("书")
print(b.thing)
```

输出：

```
书
```

能跑，但请还是用 `self`。大家默认这个约定，换成别的名字只会让读代码的人多停一秒。

**“`__init__` 负责创建对象。”** 不是。对象先被创建出来，`__init__` 才拿到它做初始化。它也不该返回别的东西：

```python
class Oops:
    def __init__(self):
        return 1


Oops()
```

最后一行是：

```
TypeError: __init__() should return None, not 'int'
```

初始化方法返回非 `None` 的值，Python 会直接报错。

**“继承就是把父类代码复制了一份。”** 没有复制。子类方法查找时会去父类拿，父类改了，子类也跟着变：

```python
class Parent:
    def hello(self):
        return "父类的话"


class Child(Parent):
    pass


print(Child.hello is Parent.hello)
Parent.hello = lambda self: "父类改了口"
print(Child().hello())
```

输出：

```
True
父类改了口
```

`Child.hello` 和 `Parent.hello` 是同一个函数对象。`Child` 自己没有 `hello`，每次调用都得回父类找。

这也是继承的代价：改父类的方法，所有子类都会受影响。继承层次越深，改一处要检查的地方越多。

## 什么时候一个函数就够了 {#tradeoffs}

如果只是把一组商品算个总价，不需要类：

```python
def cart_total(items):
    return sum(price for _, price in items)


print(cart_total([("书", 45), ("笔", 3)]))
```

输出：

```
48
```

一个函数，进什么出什么，不保存状态，调用方也不用先创建对象。

类适合另一种情况：**状态要在多次调用之间留下来**。购物车加一次商品、再算一次总价、再改数量，这些操作都围绕同一份清单，把清单和行为放在一起才省事。

继承也要付代价。假设以后还有会员折扣、礼品包装、优惠券、免税，每一种都写个子类，组合起来会变成 `MemberGiftWrapCart`、`MemberCouponCart` 这样一串。更稳的做法通常是让 `Cart` 持有一个“算价规则”对象或函数，需要哪种就传哪种进去，而不是为每种组合建一个类。

读别人的项目时，先找三件事：对象在哪里创建、它活多久、哪些属性会被改。找到这三样，类比看类名有用。

## 练习 {#self-check}

先盖住答案自己写一遍，再对照。

**第 1 题**：下面这段代码打印什么？怎么改才能让两张车各有各的清单？

```python
class Cart:
    items = []

    def __init__(self, owner):
        self.owner = owner


a = Cart("小林")
b = Cart("小李")
a.items.append("书")
print(b.items)
```

> **答案**
>
> 打印 `['书']`。
>
> `items = []` 写在类体里，是类属性，两张车共用同一个列表。把 `self.items = []` 放进 `__init__`：
>
> ```python
> class Cart:
>     def __init__(self, owner):
>         self.owner = owner
>         self.items = []
> ```
>
> 这样每次创建都会执行一次 `[]`，得到两个不同的列表。

**第 2 题**：`MemberCart` 的 `__init__` 里如果不写 `super().__init__(owner)`，会发生什么？

> **答案**
>
> `self.owner` 和 `self.items` 都不会被建立。后面调用 `member.add("书", 45)` 时，`add` 里要执行 `self.items.append(...)`，但对象上没有 `items`，会抛 `AttributeError`。
>
> 子类覆盖了 `__init__`，父类的初始化就不会自动执行，必须自己显式调用 `super().__init__(...)`。

**第 3 题**：`Child` 没有定义 `hello`，为什么 `Child().hello()` 能跑？如果 `Child` 也定义了 `hello`，怎么在子类里再用父类那一份？

> **答案**
>
> Python 在实例所属的类里找不到方法，会沿着继承关系去父类找。`Child` 没有 `hello`，就用到 `Parent.hello`。
>
> 如果子类也写了 `hello`，子类的会覆盖父类的。想在子类里执行父类那一份，用 `super().hello()`：
>
> ```python
> class Child(Parent):
>     def hello(self):
>         return super().hello() + "，还有子类的话"
> ```

## 继续阅读 {#related}

- [函数、参数与返回值](/learn/python-functions)
- [模块、包与导入](/learn/python-modules)
- [抽象基类与协议：约定可以替换的能力](/learn/abstract-base)
- [依赖注入：把需要的能力交进来](/learn/dependency-injection)

## 参考资料 {#sources}

- [A Byte of Python](https://python.swaroopch.com/)；作者：Swaroop C H；CC-BY-SA-4.0。版本：Python 3；网页快照; sha256:b851ae8ae56d0afbccb107f51511f2eb42d094a11191db8aec1909f36c658c11。
- [Python 3.13 教程与标准库](https://docs.python.org/3.13/tutorial/)；作者：Python Software Foundation；PSF-2.0。版本：Python 3.13; sha256:b1aac4fbe473c2f52e1740cf0695feb217d0c43986e2a8b635de1f08bad5e555。
