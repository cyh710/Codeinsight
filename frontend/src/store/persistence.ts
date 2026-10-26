/** 记录写入完成后才报告成功；失败对用户可见，不把内存缓存说成已保存。 */
import { createStore } from 'zustand'
import { hotState } from './hotState'

export const persistenceStore = hotState(import.meta.hot, 'persistence', () => createStore<{ error: string; pending: number }>(() => ({ error: '', pending: 0 })))
const connection = hotState(import.meta.hot, 'indexeddb', () => ({ database: undefined as Promise<IDBDatabase> | undefined }))
function db() {
  return connection.database ??= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('codeinsight-workbench', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('workspaces')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('工作区存储被其他页面阻塞，请关闭旧页面后刷新。'))
  })
}
export async function readLocal<T>(key: string): Promise<T | undefined> {
  if (typeof indexedDB === 'undefined') return
  try {
    const database = await db()
    return await new Promise<T | undefined>((resolve, reject) => {
      const request = database.transaction('workspaces').objectStore('workspaces').get(key)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
  } catch (error) { persistenceStore.setState({ error: `无法读取本地工作区：${String(error)}` }) }
}
export async function writeLocal(key: string, value: unknown) {
  if (typeof indexedDB === 'undefined') return
  persistenceStore.setState((s) => ({ pending: s.pending + 1 }))
  try {
    const database = await db()
    await new Promise<void>((resolve, reject) => {
      const tx = database.transaction('workspaces', 'readwrite')
      tx.objectStore('workspaces').put(value, key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error)
    })
  } catch (error) { persistenceStore.setState({ error: `本地保存失败，当前内容仍可使用：${String(error)}` }) }
  finally { persistenceStore.setState((s) => ({ pending: Math.max(0, s.pending - 1) })) }
}

/** 只清理被显式移除项目的草稿和材料，布局及其他项目不受影响。 */
export async function removeProjectLocal(projectId: number) {
  if (typeof indexedDB === 'undefined') return
  persistenceStore.setState(s => ({ pending: s.pending + 1 }))
  try {
    const database = await db()
    await new Promise<void>((resolve, reject) => {
      const tx = database.transaction('workspaces', 'readwrite')
      const cursor = tx.objectStore('workspaces').openCursor()
      cursor.onsuccess = () => {
        const item = cursor.result
        if (!item) return
        if (['workspace', 'draft', 'pending'].some(prefix => String(item.key).startsWith(`${prefix}:${projectId}:`))) item.delete()
        item.continue()
      }
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error)
    })
  } catch (error) { persistenceStore.setState({ error: `项目已移除，但本地缓存清理失败：${String(error)}` }) }
  finally { persistenceStore.setState(s => ({ pending: Math.max(0, s.pending - 1) })) }
}
