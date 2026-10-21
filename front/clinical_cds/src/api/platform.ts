export const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5100'
const tokenKey = 'psyconsult.platform.session.v1'
export function accessToken(): string { return sessionStorage.getItem(tokenKey) || '' }
export function setAccessToken(value: string) { value ? sessionStorage.setItem(tokenKey, value) : sessionStorage.removeItem(tokenKey) }
export function headers(): Record<string, string> { return { Authorization: `Bearer ${accessToken()}` } }
export async function request<T = any>(path: string, body?: unknown, method?: string): Promise<T> {
  const startedWith = accessToken()
  const response = await fetch(`${apiBase}/api/platform${path}`, {
    method: method || (body === undefined ? 'GET' : 'POST'),
    headers: { ...headers(), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(20000),
  })
  const payload = await response.json().catch(() => ({}))
  if (startedWith !== accessToken()) throw new Error('账号已切换，本次结果不再显示')
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `请求未完成（${response.status}）`)
  return payload as T
}
export interface Identity { user_id: string; display_name?: string; role: string; workspaces: string[] }
export interface HealthRecord { id: string; kind: string; title: string; created: string; payload: Record<string, any> }
export interface Grant { id: string; owner: string; recipient: string; expires: number; revoked: boolean; active: boolean; case_id?: string }
export interface CaseItem { id: string; alias: string; subject_owner?: string }
export interface CaseDetail extends CaseItem {
  grants: { id: string; records: HealthRecord[] }[]
  notes: { id: string; body: string; shared: boolean; created: string }[]
  consultations: HealthRecord[]
}
