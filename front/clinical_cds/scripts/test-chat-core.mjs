import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

async function load(name) {
  const input = await readFile(new URL(`../src/api/${name}.ts`, import.meta.url), 'utf8')
  const code = ts.transpileModule(input, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const { consumeChatStream } = await load('chatStream')
const { encodeSessions, restoreSessions, sessionStorageKey } = await load('chatSessions')
function stream(parts) {
  return new ReadableStream({ start(controller) { for (const p of parts) controller.enqueue(p); controller.close() } })
}
const bytes = text => new TextEncoder().encode(text)

test('SSE handles split UTF-8 and terminal frame without newline', async () => {
  const data = bytes('data: {"content":"心慌"}\r\n\r\ndata:{"done":true}')
  const rows = []
  await consumeChatStream(stream([...data].map(x => new Uint8Array([x]))), e => rows.push(e))
  assert.deepEqual(rows, [{ content: '心慌' }, { done: true }])
})
test('truncated EOF is failure and partial answer remains available', async () => {
  const rows = []
  await assert.rejects(consumeChatStream(stream([bytes('data: {"content":"partial"}\n\n')]), e => rows.push(e)), /中断/)
  assert.equal(rows[0].content, 'partial')
})
test('DONE sentinel completes and notifies the view', async () => {
  const rows = []
  await consumeChatStream(stream([bytes('data: [DONE]\n\n')]), e => rows.push(e))
  assert.deepEqual(rows, [{ done: true }])
})
test('malformed event fails instead of silently completing', async () => {
  await assert.rejects(consumeChatStream(stream([bytes('data: invalid\n\ndata: {"done":true}\n\n')]), () => {}))
})
test('backend failed terminal event stays failed', async () => {
  const rows = []
  await consumeChatStream(stream([bytes('data:{"error":"inference_failed"}\n\ndata:{"done":true,"failed":true}\n\n')]), e => rows.push(e))
  assert.equal(rows.at(-1).failed, true)
})
test('reader errors propagate, cancellation releases pending reader', async () => {
  await assert.rejects(consumeChatStream(new ReadableStream({ start(c) { c.error(new Error('network')) } }), () => {}), /network/)
  const controller = new AbortController()
  const body = new ReadableStream({ start(c) { controller.signal.addEventListener('abort', () => c.error(new DOMException('Aborted', 'AbortError'))) } })
  const pending = consumeChatStream(body, () => {})
  controller.abort()
  await assert.rejects(pending, { name: 'AbortError' })
})
test('refresh restores selected case, content and knowledge version', () => {
  const state = { sessions: [{ id: 'session_a', name: '病例A' }, { id: 'session_b', name: '病例B' }], currentSessionId: 'session_b', messagesBySession: { session_a: [], session_b: [{ role: 'assistant', content: 'answer', status: '分析完成', knowledgeVersion: 'project-abc' }] } }
  const restored = restoreSessions(encodeSessions(state))
  assert.equal(restored.currentSessionId, 'session_b')
  assert.equal(restored.messagesBySession.session_b[0].knowledgeVersion, 'project-abc')
  assert.notEqual(sessionStorageKey('A'), sessionStorageKey('B'))
})
test('refresh flags interrupted generation and rejects corrupt storage', () => {
  const state = { sessions: [{ id: 'session_a', name: '病例A' }], currentSessionId: 'session_a', messagesBySession: { session_a: [{ role: 'assistant', content: 'partial', status: '正在分析' }] } }
  assert.equal(restoreSessions(encodeSessions(state)).messagesBySession.session_a[0].failed, true)
  assert.equal(restoreSessions('invalid-json'), null)
  state.sessions[0].id = '__proto__'
  assert.equal(restoreSessions(encodeSessions(state)), null)
})
test('refresh preserves an explicitly stopped answer', () => {
  const state = { sessions: [{ id: 'session_a', name: '病例A' }], currentSessionId: 'session_a', messagesBySession: { session_a: [{ role: 'assistant', content: 'partial', status: '已停止生成', failed: true }] } }
  assert.equal(restoreSessions(encodeSessions(state)).messagesBySession.session_a[0].status, '已停止生成')
})
