/** 开发热更新保留运行中的状态及其闭包；状态逻辑改动在手动刷新后加载。 */
export function hotState<T>(hot: { data: Record<string, unknown> } | undefined, key: string, create: () => T): T {
  if (!hot) return create()
  const name = `codeinsight:${key}`
  if (!(name in hot.data)) hot.data[name] = create()
  return hot.data[name] as T
}
