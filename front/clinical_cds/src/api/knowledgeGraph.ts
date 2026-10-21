import { accessToken } from '@/api/platform'
import type { Entity, Neighborhood, Source, Stats } from '@/types/knowledgeGraph'
const base = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000'
async function request<T>(path: string, userId: string): Promise<T> {
  const response = await fetch(`${base}/api/knowledge-graph${path}`, { headers: {
    Authorization: `Bearer ${accessToken()}`, 'X-User-Id': userId,
  } })
  if (!response.ok) throw new Error(response.status === 401 ? '访问令牌无效，请检查本地配置。' : response.status === 503 ? '知识版本或图谱服务暂时不可用，请检查当前版本和本地服务。' : `请求失败（${response.status}）`)
  return response.json() as Promise<T>
}
export const graphApi = {
  search: (q: string, user: string) => request<{items: Entity[]; total: number; truncated: boolean}>(`/search?q=${encodeURIComponent(q)}`, user),
  detail: (id: string, user: string) => request<{entity: Entity; sources: Source[]}>(`/entities/${encodeURIComponent(id)}`, user),
  neighbors: (id: string, relation: string, user: string, includeUnreviewed=false) => request<Neighborhood>(`/entities/${encodeURIComponent(id)}/neighbors?limit=60&include_unreviewed=${includeUnreviewed}${relation ? '&relation_type=' + encodeURIComponent(relation) : ''}`, user),
  stats: (user: string) => request<Stats>('/stats', user),
}
