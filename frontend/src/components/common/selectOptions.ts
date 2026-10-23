import { Children, isValidElement, type ReactNode } from 'react'

export interface SelectOption {
  value: string
  label: string
  disabled: boolean
}

/**
 * 把 `<option>` children 解析成纯数据（ADR 0017）。
 * 独立成文件是为了让 Select.tsx 只导出组件（react-refresh 约束），
 * 也让纯逻辑可以直接做单元测试。
 */
export function parseOptionChildren(children: ReactNode): SelectOption[] {
  const items: SelectOption[] = []
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return
    const props = (child.props ?? {}) as {
      value?: string | number
      disabled?: boolean
      children?: ReactNode
    }
    const label = optionText(props.children)
    items.push({ value: String(props.value ?? label), label, disabled: Boolean(props.disabled) })
  })
  return items
}

function optionText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(optionText).join('')
  if (isValidElement(node)) return optionText((node.props as { children?: ReactNode }).children)
  return ''
}
