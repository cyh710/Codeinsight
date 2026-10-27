import { useEffect, useState } from 'react'
import { api, isMockMode } from '../../api/dataSource'

/** 后端不会随 Vite 热更新；提示重启，不中断正在进行的回答。 */
export default function BackendVersionNotice() {
  const [outdated, setOutdated] = useState(false)
  useEffect(() => {
    if (isMockMode) return
    let alive = true
    const check = () => api.getHealth().then(info => {
      if (alive) setOutdated(Boolean(info.restart_required || !info.runtime_revision))
    }).catch(() => { /* 连接错误由既有请求反馈，不在这里叠加另一条网络告警。 */ })
    void check()
    const timer = setInterval(() => void check(), 15000)
    return () => { alive = false; clearInterval(timer) }
  }, [])
  return outdated ? <p role="status" className="shrink-0 bg-amber-50 px-4 py-2 text-xs leading-5 text-amber-800">后端需要重启以加载当前代码。请在原启动窗口按 Ctrl+C 后重新启动；当前对话与草稿会保留。</p> : null
}
