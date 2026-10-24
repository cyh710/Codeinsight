# Redis 缓存：复用可以重建的结果

## 先建立直觉 {#overview}

缓存把较昂贵的结果暂时保存起来，让后续相同或相关请求更快得到答案。Redis 是可用于实现缓存的键值系统，但它也能承担队列、计数等职责。因此导入 Redis 或建立连接，不足以证明项目实现了缓存。

## 原理与执行过程 {#mechanism}

典型流程是先计算缓存键、读取缓存，未命中时访问原数据或执行计算，再写入结果并设置过期。缓存键必须包含影响结果的必要因素，例如模型版本、权限范围或语言。缓存的内容应当可以根据权威数据重建，失效与更新策略决定用户会看到多旧的数据。

## 跟着例子理解 {#example}

```python
def load_title(cache, key, compute):
    cached = cache.get(key)
    if cached is not None:
        return cached
    value = compute()
    cache.set(key, value, ex=60)
    return value
```

## 一步一步读懂 {#walkthrough}

先读取 key；用 is not None 区分未命中与合法空值。未命中时才调用 compute，并把结果保存 60 秒。这里把客户端作为参数传入，方便测试；实际 Redis 可能返回字节，还要明确序列化和编码。多个请求同时未命中时仍可能重复计算，本例没有解决缓存击穿。

## 常见误解 {#pitfalls}

缓存不是权威数据库的自动替代。忘记把用户权限放进键可能造成跨用户数据混用。缓存故障时直接报错还是降级到原始计算，需要按服务容量设计。一个 set 调用也可能只是在保存状态，不能直接标成缓存命中机制。

## 工程中的取舍 {#tradeoffs}

缓存降低延迟与计算成本，但增加过期、失效和容量管理。短 TTL 更新快但命中率可能低，长 TTL 更易过时。局部内存缓存部署简单，多进程间却不共享；Redis 增加共享能力与额外基础设施。

## 接着探索 {#related}

- [延迟初始化与缓存工厂](/learn/singleton-lazy)
- [索引与查询代价](/learn/sql-indexes)

## 来源与版本 {#sources}

- [Redis Python client documentation](https://redis.readthedocs.io/en/stable/examples.html)；作者：Redis contributors；MIT。版本：导入日网页快照; sha256:f40fbfab62a3d0323ff1bdd4f86b135cc83876ad59bfc39716ba87140319035c。
