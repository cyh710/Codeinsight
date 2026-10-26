/**
 * 项目状态 → 左栏呈现（纯映射，直接单测）。
 * ready 不显示任何提示——静默即健康，别用徽标刷存在感。
 */
export interface StatusView {
  label: string
  tone: 'info' | 'danger' | 'warning' | 'none'
  title: string
}

export function projectStatusView(status: string): StatusView {
  switch (status) {
    case 'indexing':
      return { label: '索引中…', tone: 'info', title: '正在建索引，完成后自动刷新' }
    case 'failed':
      return {
        label: '索引失败',
        tone: 'danger',
        title: '本次索引未完成，请检查项目目录和提交版本后重试。',
      }
    case 'stale':
      return {
        label: '索引已过期',
        tone: 'warning',
        title: '代码已前移到新 commit，当前索引停在旧版本；重新导入可刷新',
      }
    default:
      return { label: '', tone: 'none', title: '' }
  }
}
