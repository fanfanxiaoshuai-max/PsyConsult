export interface ChatEvent {
  content?: string
  agent?: string
  status?: string
  error?: string
  failed?: boolean
  done?: boolean
  cache_hit?: boolean
  knowledge_version?: string
  knowledge_name?: string
  knowledge_checksum?: string
}

/** Read complete SSE events, including split UTF-8 and a final event without a newline. */
export async function consumeChatStream(body: ReadableStream<Uint8Array>, onEvent: (event: ChatEvent) => void | Promise<void>) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let data: string[] = []
  let complete = false
  async function dispatch() {
    if (!data.length) return
    const value = data.join('\n')
    data = []
    if (value === '[DONE]') { await onEvent({ done: true }); complete = true; return }
    const event: ChatEvent = JSON.parse(value)
    if (!event || typeof event !== 'object' || Array.isArray(event)) throw new Error('无效的响应格式')
    await onEvent(event)
    if (event.done) complete = true
  }
  async function line(value: string) {
    value = value.replace(/\r$/, '')
    if (!value) await dispatch()
    else if (value.startsWith('data:')) data.push(value.slice(5).replace(/^ /, ''))
  }
  try {
    while (!complete) {
      const chunk = await reader.read()
      buffer += chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true })
      let end: number
      while (!complete && (end = buffer.indexOf('\n')) !== -1) {
        await line(buffer.slice(0, end))
        buffer = buffer.slice(end + 1)
      }
      if (chunk.done) {
        if (!complete) { await line(buffer); await dispatch() }
        if (!complete) throw new Error('回答连接已中断')
        break
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
