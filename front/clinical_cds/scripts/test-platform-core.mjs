import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const values = new Map()
globalThis.sessionStorage = { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) }
const source = (await readFile(new URL('../src/api/platform.ts', import.meta.url), 'utf8')).replace('import.meta.env.VITE_API_BASE_URL', 'undefined')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const api = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('platform token is scoped to the current browser session and can be cleared', () => {
  api.setAccessToken('synthetic-session'); assert.equal(api.accessToken(), 'synthetic-session')
  api.setAccessToken(''); assert.equal(api.accessToken(), '')
})
test('platform requests use the current credential and preserve backend errors', async () => {
  api.setAccessToken('synthetic-current')
  globalThis.fetch = async (_url, init) => {
    assert.equal(init.headers.Authorization, 'Bearer synthetic-current')
    return new Response(JSON.stringify({ detail: '没有该资料的访问权限' }), { status: 403 })
  }
  await assert.rejects(api.request('/records'), /访问权限/)
})
test('a delayed response from a previous identity cannot reach the new identity', async () => {
  api.setAccessToken('synthetic-alice')
  let release
  globalThis.fetch = () => new Promise(resolve => { release = resolve })
  const pending = api.request('/records')
  api.setAccessToken('synthetic-bravo')
  release(new Response(JSON.stringify({ items: ['alice-private-record'] }), { status: 200 }))
  await assert.rejects(pending, /账号已切换/)
})
