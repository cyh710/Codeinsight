/**
 * 端点封装（契约 §3/§4）。字段形状全部来自冻结的 `types.ts`，
 * 这里只做 URL 拼接与查询串序列化——不加字段、不改名。
 */
import { jsonRequest } from './client'
import type {
  ChangesResponse,
  CreateProjectRequest,
  CreateProjectResponse,
  FileEntry,
  FolderSelectionResponse,
  Flow,
  HealthResponse,
  ListResponse,
  ProjectDetail,
  ProjectOverview,
  ProjectSummary,
  RelationListResponse,
  RelocateProjectRequest,
  SymbolDetail,
  SymbolListItem,
  SymbolQuery,
} from './types'

export function getHealth(): Promise<HealthResponse> {
  return jsonRequest<HealthResponse>('/health')
}

export function listProjects(): Promise<ProjectSummary[]> {
  // 契约 §0.4：GET /projects 返回裸数组，不分页。
  return jsonRequest<ProjectSummary[]>('/projects')
}

export function createProject(req: CreateProjectRequest): Promise<CreateProjectResponse> {
  return jsonRequest<CreateProjectResponse>('/projects', { method: 'POST', body: JSON.stringify(req) })
}

export function relocateProject(id: number, req: RelocateProjectRequest): Promise<CreateProjectResponse> {
  return jsonRequest<CreateProjectResponse>(`/projects/${id}/relocate`, { method: 'POST', body: JSON.stringify(req) })
}

/** 打开本机系统选择框；沿用原导入接口提交选中的完整路径。 */
export function selectProjectFolder(): Promise<FolderSelectionResponse> {
  return jsonRequest<FolderSelectionResponse>('/local/select-folder', { method: 'POST' })
}

export function getProject(id: number): Promise<ProjectDetail> {
  return jsonRequest<ProjectDetail>(`/projects/${id}`)
}

export function getProjectOverview(id: number): Promise<ProjectOverview> {
  return jsonRequest<ProjectOverview>(`/projects/${id}/overview`)
}

export function getProjectFiles(id: number): Promise<FileEntry[]> {
  // 文件树一次拉全（契约 §0.4 例外：裸数组）。
  return jsonRequest<FileEntry[]>(`/projects/${id}/files`)
}

export function listProjectSymbols(id: number, query: SymbolQuery = {}): Promise<ListResponse<SymbolListItem>> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.kind) params.set('kind', query.kind)
  if (query.path) params.set('path', query.path)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset !== undefined) params.set('offset', String(query.offset))
  const qs = params.size ? `?${params}` : ''
  return jsonRequest<ListResponse<SymbolListItem>>(`/projects/${id}/symbols${qs}`)
}

// qualname 用点号分层，进路径必须整体 URL 编码（契约 §0.5）。
export function getSymbol(id: number, qualname: string): Promise<SymbolDetail> {
  return jsonRequest<SymbolDetail>(`/projects/${id}/symbols/${encodeURIComponent(qualname)}`)
}

export function getSymbolCallers(id: number, qualname: string): Promise<RelationListResponse> {
  return jsonRequest<RelationListResponse>(`/projects/${id}/symbols/${encodeURIComponent(qualname)}/callers`)
}

export function getSymbolCallees(id: number, qualname: string): Promise<RelationListResponse> {
  return jsonRequest<RelationListResponse>(`/projects/${id}/symbols/${encodeURIComponent(qualname)}/callees`)
}

export function listFlows(id: number): Promise<ListResponse<Flow>> {
  return jsonRequest<ListResponse<Flow>>(`/projects/${id}/flows`)
}

export function getChanges(id: number, since?: string): Promise<ChangesResponse> {
  const qs = since ? `?since=${encodeURIComponent(since)}` : ''
  return jsonRequest<ChangesResponse>(`/projects/${id}/changes${qs}`)
}
