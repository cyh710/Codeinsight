/**
 * 编排执行端点封装（契约 §16.3）。
 * 动作端点返回迁移后的 execution 元数据——调用方据此更新消息卡。
 */
import { jsonRequest } from './client'
import type { ExecutionMetadata } from './types'

export function getExecution(projectId: number, taskId: string): Promise<ExecutionMetadata> {
  return jsonRequest<ExecutionMetadata>(`/projects/${projectId}/executions/${encodeURIComponent(taskId)}`)
}

export function executionAction(
  projectId: number,
  taskId: string,
  action: 'approve' | 'reject' | 'abort' | 'merge',
): Promise<ExecutionMetadata> {
  return jsonRequest<ExecutionMetadata>(
    `/projects/${projectId}/executions/${encodeURIComponent(taskId)}/${action}`,
    { method: 'POST' },
  )
}
