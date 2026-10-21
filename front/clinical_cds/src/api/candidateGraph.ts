export interface CandidateEntity { id: string; name: string; label: string }
export interface CandidateEvidence { source_id: string; source_title?: string; region: string; edition?: string; locator: unknown; scope_conditions?: string; sha256: string }
export interface CandidateRecord { id: string; title: string; subject_name: string; related_name?: string | null; kind: string; predicate: string; context: Record<string, unknown>; evidence: CandidateEvidence[]; audit_item_ids: string[] }
export interface CandidateSource { id: string; title: string; url: string; region: string; edition?: string }
export interface CandidateDetail { entity: CandidateEntity; records: CandidateRecord[]; sources: CandidateSource[]; review_item_ids: string[]; review_counts: { insufficient: number; withdrawn: number }; browser_graph: { nodes: import('@/types/knowledgeGraph').Entity[]; edges: import('@/types/knowledgeGraph').Relation[] } }
export interface ReviewRow { item_id: string; summary: string; original_status: string; status_label: string; reason: string; original: unknown; candidate_change: unknown; evidence: unknown[]; supplemental_review?: unknown; prior_supplement?: unknown; additional_sources: {id:string;title:string;url:string;scope:string}[]; questions: string[]; project_review: { status: string; label: string; eligible: boolean; note: string; actor: string } }
const base = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000'
async function request(path: string, user: string, body?: unknown) {
  let response: Response
  try { response = await fetch(`${base}/api/knowledge-workbench${path}`, { method: body ? 'POST' : 'GET', body: body ? JSON.stringify(body) : undefined, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${import.meta.env.VITE_API_AUTH_TOKEN || ''}`, 'X-User-Id': user } }) }
  catch { throw new Error('无法连接本地服务，请确认后端已启动，稍后重新加载。') }
  if (!response.ok && response.status === 409) { const data = await response.json(); throw new Error(data.detail) }
  if (!response.ok) throw new Error(response.status === 401 ? '访问令牌无效，请检查本地配置。' : response.status === 403 ? '当前用户没有执行此操作的权限。' : response.status === 503 ? '知识资料校验失败或服务未就绪，请检查本地数据后重试。' : `请求失败（${response.status}）`)
  return response
}
export const candidateApi = {
  status: async (u: string): Promise<WorkbenchStatus> => (await request('/status', u)).json(),
  change: async (action: string, body: unknown, u: string): Promise<WorkbenchStatus> => (await request('/' + action, u, body)).json(),
  search: async (q: string, u: string, view = 'working'): Promise<{ items: CandidateEntity[]; total: number; truncated: boolean }> => (await request(`/search?q=${encodeURIComponent(q)}&view=${view}`, u)).json(),
  detail: async (id: string, u: string, view = 'working'): Promise<CandidateDetail> => (await request(`/entities/${encodeURIComponent(id)}?view=${view}`, u)).json(),
  reviews: async (q: string, status: string, page: number, u: string): Promise<{ items: ReviewRow[]; total: number }> => (await request(`/reviews?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}&offset=${(page - 1) * 20}&limit=20`, u)).json(),
  packet: async (u: string) => (await request('/export', u)).blob(),
}

export interface ProjectRelease { id: string; name: string; created_at: string; actor: string; note: string; source_sha256: string; entity_count: number; record_count: number }
export interface WorkbenchStatus { chat_version: string; revision: number; working_sha256: string; total: number; counts: Record<string, number>; active: string | null; releases: ProjectRelease[]; events: {action: string; actor: string; at: string; target: string | null}[] }
