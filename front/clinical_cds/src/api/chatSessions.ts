export interface SessionItem { id: string; name: string }
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  status?: string
  knowledgeVersion?: string
  knowledgeName?: string
  knowledgeChecksum?: string
  cacheHit?: boolean
  failed?: boolean
}
export interface ChatSessions {
  sessions: SessionItem[]
  currentSessionId: string
  messagesBySession: Record<string, ChatMessage[]>
}
export function sessionStorageKey(userId: string) { return `psyconsult.chat.v1.${userId}` }
export function newSessionId() { return `session_${crypto.randomUUID()}` }

export function restoreSessions(raw: string | null): ChatSessions | null {
  if (!raw) return null
  try {
    const saved = JSON.parse(raw)
    if (saved.version !== 1 || !Array.isArray(saved.sessions) || !saved.sessions.length || saved.sessions.length > 1000) return null
    const messagesBySession: Record<string, ChatMessage[]> = Object.create(null)
    const sessions: SessionItem[] = []
    for (const item of saved.sessions) {
      if (!item || typeof item.id !== 'string' || !/^session_[A-Za-z0-9_-]{1,120}$/.test(item.id) || typeof item.name !== 'string' || item.id in messagesBySession) return null
      sessions.push({ id: item.id, name: item.name.slice(0, 100) })
      const rows = saved.messagesBySession?.[item.id]
      if (!Array.isArray(rows)) return null
      messagesBySession[item.id] = rows.map((row): ChatMessage => {
        if (!row || !['user', 'assistant'].includes(row.role) || typeof row.content !== 'string') throw new Error('Invalid saved message')
        const result: ChatMessage = { role: row.role, content: row.content }
        for (const key of ['status', 'knowledgeVersion', 'knowledgeName', 'knowledgeChecksum'] as const) {
          if (typeof row[key] === 'string') result[key] = row[key]
        }
        result.cacheHit = row.cacheHit === true
        result.failed = row.failed === true
        if (result.role === 'assistant' && !result.failed && result.status && result.status !== '分析完成') {
          result.failed = true
          result.status = '分析未完成，可重新提问'
        }
        return result
      })
    }
    return { sessions, messagesBySession, currentSessionId: saved.currentSessionId in messagesBySession ? saved.currentSessionId : sessions[0]!.id }
  } catch { return null }
}
export function encodeSessions(state: ChatSessions) { return JSON.stringify({ version: 1, ...state }) }
