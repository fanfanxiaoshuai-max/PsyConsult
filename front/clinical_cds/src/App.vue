<template>
  <div class="clinical-shell">
    <aside class="workspace-rail">
      <div class="brand-block">
        <div class="brand-mark">
          <el-icon><FirstAidKit /></el-icon>
        </div>
        <div>
          <p class="brand-kicker">Clinical CDS</p>
          <h1>精神科决策支持</h1>
        </div>
      </div>

      <el-button class="new-session-button" type="primary" :icon="CirclePlus" @click="createSession">
        新建诊疗会话
      </el-button>

      <el-button @click="activeView = activeView === 'graph' ? 'chat' : 'graph'">{{ activeView === 'graph' ? '返回诊疗会话' : '知识图谱' }}</el-button>
      <el-button @click="activeView = activeView === 'candidate' ? 'chat' : 'candidate'">{{ activeView === 'candidate' ? '返回诊疗会话' : '知识审核与版本管理' }}</el-button>

      <nav class="session-list" aria-label="诊疗会话">
        <button
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === currentSessionId }"
          type="button"
          @click="selectSession(s.id)"
        >
          <el-icon><ChatDotRound /></el-icon>
          <span>{{ s.name }}</span>
        </button>
      </nav>

      <div class="doctor-card">
        <el-icon><UserFilled /></el-icon>
        <div>
          <span>当前医生</span>
          <strong>{{ userId }}</strong>
        </div>
      </div>
    </aside>

    <KnowledgeGraphPanel v-if="identityReady" v-show="activeView === 'graph'" :active="activeView === 'graph'" :user-id="userId" />
    <CandidateGraphPanel v-if="identityReady && activeView === 'candidate'" :active="true" :user-id="userId" :role="identityRole" />
    <main v-show="activeView === 'chat'" class="case-workbench">
      <header class="case-header">
        <div>
          <p class="eyebrow">ICD-11 · Multi-Agent · 药物审查</p>
          <h2>诊疗会话工作台</h2>
        </div>
        <div class="service-pill" :class="{ active: isThinking }">
          <span class="status-dot"></span>
          {{ isThinking ? '推理中' : '待输入' }}
        </div>
      </header>

      <section class="notice-bar" aria-label="临床使用提示">
        <el-icon><WarningFilled /></el-icon>
        <span>仅供临床参考，诊断和处方须由执业医师结合病史、查体和检查结果确认。</span>
      </section>
      <el-alert v-if="identityError" :title="identityError" type="error" :closable="false" />

      <section ref="msgContainer" class="messages-panel" aria-live="polite">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-copy">
            <p class="eyebrow">快速开始</p>
            <h3>输入症状、诊断问题或用药方案。</h3>
            <p>系统会按症状抽取、鉴别诊断、治疗建议和药物审查的流程组织回复。</p>
          </div>

          <div class="scenario-grid">
            <button
              v-for="scenario in scenarios"
              :key="scenario.title"
              class="scenario-card"
              type="button"
              @click="sendQuery(scenario.query)"
            >
              <span class="scenario-icon">
                <el-icon><component :is="scenario.icon" /></el-icon>
              </span>
              <span class="scenario-title">{{ scenario.title }}</span>
              <span class="scenario-text">{{ scenario.summary }}</span>
            </button>
          </div>
        </div>

        <article
          v-for="(msg, idx) in messages"
          :key="idx"
          class="message-row"
          :class="msg.role === 'user' ? 'user-row' : 'assistant-row'"
        >
          <div class="message-meta">
            <span>{{ msg.role === 'user' ? '医生输入' : 'CDS 输出' }}</span><span v-if="msg.role === 'assistant' && msg.knowledgeVersion" class="knowledge-version" :title="msg.knowledgeChecksum">知识版本：{{ msg.knowledgeName || msg.knowledgeVersion }} · {{ msg.knowledgeVersion }}{{ msg.cacheHit ? ' · 缓存命中' : '' }}</span>
          </div>
          <div class="message-bubble" :class="msg.role === 'user' ? 'user-bubble' : 'assistant-bubble'">
            <div v-if="msg.role === 'assistant' && msg.status" class="stage-status" aria-live="polite">
              <el-icon v-if="isThinking && idx === messages.length - 1" class="is-loading"><Loading /></el-icon>
              <span>阶段：{{ msg.status }}</span>
            </div>
            <div v-if="msg.content" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
            <el-button v-if="msg.failed" text :disabled="isThinking" @click="retryMessage(idx)">重新提问</el-button>
          </div>
        </article>

        <div v-if="isThinking" class="thinking-row">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在分析病例并检索知识源</span>
        </div>
      </section>

      <footer class="composer">
        <span v-if="storageError" role="status">{{ storageError }}</span>
        <el-input
          v-model="inputMessage"
          class="case-input"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 6 }"
          resize="none"
          placeholder="请输入患者症状、病程、既往用药、量表结果或需要审查的治疗方案"
          @keydown.enter.exact.prevent="sendQuery()"
        />
        <el-button v-if="isThinking" class="send-button" @click="cancelRequest">停止生成</el-button>
        <el-button v-else
          class="send-button"
          type="primary"
          :icon="Promotion"
          :disabled="!identityReady || !inputMessage.trim() || isThinking"
          @click="sendQuery()"
        >
          发送
        </el-button>
      </footer>
    </main>

    <aside v-show="activeView === 'chat'" class="insight-panel">
      <section class="panel-section">
        <p class="section-label">工作流</p>
        <ol class="pipeline-list">
          <li v-for="stage in pipelineStages" :key="stage.name">
            <span class="pipeline-index">{{ stage.index }}</span>
            <div>
              <strong>{{ stage.name }}</strong>
              <span>{{ stage.detail }}</span>
            </div>
          </li>
        </ol>
      </section>

      <section class="panel-section">
        <p class="section-label">知识源</p>
        <div class="source-list">
          <div v-for="source in knowledgeSources" :key="source.name" class="source-item">
            <el-icon><component :is="source.icon" /></el-icon>
            <div>
              <strong>{{ source.name }}</strong>
              <span>{{ source.detail }}</span>
            </div>
          </div>
        </div>
      </section>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { accessToken } from '@/api/platform'
import { defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { consumeChatStream } from '@/api/chatStream'
import { encodeSessions, newSessionId, restoreSessions, sessionStorageKey, type SessionItem, type ChatMessage } from '@/api/chatSessions'
const KnowledgeGraphPanel = defineAsyncComponent(() => import('@/components/knowledge-graph/KnowledgeGraphPanel.vue'))
const CandidateGraphPanel = defineAsyncComponent(() => import('@/components/knowledge-graph/CandidateGraphPanel.vue'))
const activeView = ref<'chat' | 'graph' | 'candidate'>(window.location.hash === '#candidate' ? 'candidate' : 'chat')
watch(activeView, view => { window.history.replaceState(null, '', window.location.pathname + window.location.search + (view === 'candidate' ? '#candidate' : '')) })
import {
  ChatDotRound,
  CirclePlus,
  Connection,
  DataAnalysis,
  DocumentChecked,
  FirstAidKit,
  Loading,
  Promotion,
  UserFilled,
  WarningFilled,
} from '@element-plus/icons-vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

const props = defineProps<{ draft?: string; caseId?: string }>()
const userId = ref('doctor_001')
const storageError = ref('')
const identityReady = ref(false)
const identityRole = ref('reader')
const identityError = ref('')
const currentSessionId = ref(newSessionId())
const sessions = ref<SessionItem[]>([{ id: currentSessionId.value, name: '新诊疗会话' }])
const messagesBySession = ref<Record<string, ChatMessage[]>>({
  [currentSessionId.value]: [],
})
const messages = ref<ChatMessage[]>(messagesBySession.value[currentSessionId.value] || [])
watch([sessions, messagesBySession, currentSessionId], () => {
  if (!identityReady.value) return
  try {
    localStorage.setItem(sessionStorageKey(userId.value + (props.caseId ? '.case.' + props.caseId : '')), encodeSessions({ sessions: sessions.value, messagesBySession: messagesBySession.value, currentSessionId: currentSessionId.value }))
    storageError.value = ''
  } catch { storageError.value = '本机保存会话失败，请保留重要内容后再刷新。' }
}, { deep: true })
let activeRequest: AbortController | null = null
onBeforeUnmount(() => activeRequest?.abort())
function cancelRequest() { activeRequest?.abort('user') }
const inputMessage = ref(props.draft || '')
watch(() => props.draft, value => { if (value && !isThinking.value) inputMessage.value = value })
const isThinking = ref(false)
const msgContainer = ref<HTMLElement | null>(null)
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000'
const apiAuthToken = accessToken()
const identityPromise = (async () => {
  try {
    const response = await fetch(`${apiBaseUrl}/api/identity`, { headers: apiAuthToken ? { Authorization: `Bearer ${apiAuthToken}` } : {}, signal: AbortSignal.timeout(10_000) })
    if (!response.ok) throw new Error('identity unavailable')
    const identity = await response.json()
    userId.value = identity.user_id
    identityRole.value = identity.role
    try {
      const restored = restoreSessions(localStorage.getItem(sessionStorageKey(userId.value + (props.caseId ? '.case.' + props.caseId : ''))))
      if (restored) {
        sessions.value = restored.sessions
        messagesBySession.value = restored.messagesBySession
        currentSessionId.value = restored.currentSessionId
        messages.value = restored.messagesBySession[restored.currentSessionId] || []
      }
    } catch { storageError.value = '本机无法保存会话，刷新后可能丢失。' }
    identityReady.value = true
  } catch { identityError.value = '无法确认当前用户，请检查后端连接或访问令牌后刷新页面。' }
})()

const scenarios = [
  {
    title: '抑郁筛查',
    summary: '低落、失眠、兴趣下降',
    icon: DataAnalysis,
    query: '患者近两周情绪低落、失眠、食欲下降，以前喜欢的活动现在也没兴趣了',
  },
  {
    title: '双相鉴别',
    summary: '情绪高涨后转低落',
    icon: DocumentChecked,
    query: '患者情绪忽高忽低，有时话多、精力旺盛，持续一周后转为情绪低落',
  },
  {
    title: '精神病性症状',
    summary: '幻听、被监视感',
    icon: Connection,
    query: '患者声称听到有人在议论自己，坚信被监视，不愿出门见人',
  },
  {
    title: '强迫症状',
    summary: '反复洗手和检查',
    icon: DocumentChecked,
    query: '患者反复洗手、检查门锁，每天花数小时，明知不必要但控制不住',
  },
  {
    title: '焦虑障碍',
    summary: '紧张、心慌、入睡困难',
    icon: DataAnalysis,
    query: '患者持续紧张不安、心慌、入睡困难，总是担心各种事情已半年',
  },
  {
    title: '药物审查',
    summary: '舍曲林与帕罗西汀',
    icon: FirstAidKit,
    query: '患者正在服用舍曲林和帕罗西汀，最近出现恶心、失眠加重',
  },
]

const pipelineStages = [
  { index: '01', name: '症状抽取', detail: '用户原话、证据、量表资料核对' },
  { index: '02', name: '鉴别诊断', detail: 'ICD-11 标准逐条对照' },
  { index: '03', name: '治疗建议', detail: '指南路径和分级方案' },
  { index: '04', name: '药物审查', detail: '相互作用和风险评级' },
]

const knowledgeSources = [
  { name: 'Milvus RAG', detail: '指南和诊断标准片段', icon: DataAnalysis },
  { name: '版本化知识图谱', detail: '当前启用版本的结构化记录', icon: Connection },
  { name: 'Redis 记忆', detail: '当前会话近期上下文', icon: ChatDotRound },
]

function renderMarkdown(text: string) {
  const html = marked.parse(text, { breaks: true, gfm: true }) as string
  return DOMPurify.sanitize(html)
}

function getSessionMessages(sessionId: string): ChatMessage[] {
  if (!messagesBySession.value[sessionId]) {
    messagesBySession.value[sessionId] = []
  }
  return messagesBySession.value[sessionId]
}

function setCurrentSessionMessages(sessionId: string) {
  messages.value = getSessionMessages(sessionId)
}

async function selectSession(sessionId: string) {
  currentSessionId.value = sessionId
  setCurrentSessionMessages(sessionId)
  await scrollMessages()
}

function createSession() {
  const id = newSessionId()
  sessions.value.unshift({ id, name: `诊疗会话 ${sessions.value.length + 1}` })
  messagesBySession.value[id] = []
  currentSessionId.value = id
  setCurrentSessionMessages(id)
}

async function scrollMessages() {
  await nextTick()
  if (msgContainer.value) {
    msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  }
}

function agentLabel(name: string): string {
  const labels: Record<string, string> = {
    orchestrator: '🧭 路由决策',
    differential_diagnosis: '🔬 临床评估与鉴别诊断',
    treatment_recommend: '💊 治疗推荐',
    drug_interaction: '⚠️ 药物审查',
    input_validation: '输入提示',
  }
  return labels[name] || name
}

function statusLabel(parsed: { status?: string; agent?: string; content?: string }): string {
  if (parsed.status === 'agent_node_start' && parsed.agent) {
    return `正在${agentLabel(parsed.agent)}...`
  }
  if (parsed.status === 'agent_tool_call') {
    return parsed.content || '正在查询知识库...'
  }
  if (parsed.status === 'agent_tool_done') {
    return parsed.content || '工具查询完成'
  }
  if (parsed.status === 'agent_node_complete' && parsed.agent) {
    return `${agentLabel(parsed.agent)} 已完成`
  }
  return parsed.content || ''
}

function appendAssistantMessage(sessionId: string, index: number, content: string) {
  const message = getSessionMessages(sessionId)[index]
  if (message && message.role === 'assistant') {
    message.content += content
  }
}

function updateAssistantStatus(sessionId: string, index: number, status: string) {
  const message = getSessionMessages(sessionId)[index]
  if (message && message.role === 'assistant') {
    message.status = status
  }
}

async function sendQuery(preset?: string) {
  await identityPromise
  if (!identityReady.value) return
  const query = preset || inputMessage.value.trim()
  if (!query || isThinking.value) return

  const requestSessionId = currentSessionId.value
  const sessionMessages = getSessionMessages(requestSessionId)
  setCurrentSessionMessages(requestSessionId)

  sessionMessages.push({ role: 'user', content: query })
  inputMessage.value = ''
  isThinking.value = true
  const msgIdx = sessionMessages.length
  sessionMessages.push({ role: 'assistant', content: '', status: '正在连接...' })
  const lastContentAgent = { current: '' }
  const controller = new AbortController()
  activeRequest = controller
  const timeout = window.setTimeout(() => controller.abort('timeout'), 240_000)
  await scrollMessages()

  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-User-Id': userId.value,
    }
    if (apiAuthToken) {
      headers.Authorization = `Bearer ${apiAuthToken}`
    }

    const response = await fetch(`${apiBaseUrl}${props.caseId ? '/api/platform/cases/' + props.caseId + '/chat' : '/api/chat'}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, session_id: requestSessionId }),
      signal: controller.signal,
    })

    if (!response.ok || !response.body) {
      throw new Error(`Request failed with status ${response.status}`)
    }

    await consumeChatStream(response.body, async parsed => {
          const target = getSessionMessages(requestSessionId)[msgIdx]
          if (target) {
            if (parsed.knowledge_version) { target.knowledgeVersion = parsed.knowledge_version; target.knowledgeName = parsed.knowledge_name; target.knowledgeChecksum = parsed.knowledge_checksum }
            if (parsed.cache_hit) target.cacheHit = true
            if (parsed.error || parsed.failed) target.failed = true
          }
          if (parsed.error) {
            appendAssistantMessage(requestSessionId, msgIdx, '\n' + parsed.content)
            updateAssistantStatus(requestSessionId, msgIdx, '分析未完成')
            return
          }
          if (parsed.done) {
            updateAssistantStatus(requestSessionId, msgIdx, target?.failed ? '分析未完成' : '分析完成')
            return
          }

          if (parsed.status) {
            updateAssistantStatus(requestSessionId, msgIdx, statusLabel(parsed))
            if (currentSessionId.value === requestSessionId) {
              await scrollMessages()
            }
            return
          }

          if (parsed.content) {
            let label = ''
            if (parsed.agent && parsed.agent !== 'semantic_cache' && parsed.agent !== lastContentAgent.current) {
              lastContentAgent.current = parsed.agent
              if (!parsed.content.trimStart().startsWith('#')) label = `\n### ${agentLabel(parsed.agent)}\n`
            }
            appendAssistantMessage(requestSessionId, msgIdx, label + parsed.content)
            if (currentSessionId.value === requestSessionId) {
              await scrollMessages()
            }
          }
    })
  } catch {
    const target = getSessionMessages(requestSessionId)[msgIdx]
    if (target) {
      target.failed = true
      target.status = controller.signal.reason === 'user' ? '已停止生成' : controller.signal.reason === 'timeout' ? '请求超时，可重新提问' : '连接中断，分析未完成'
      if (!target.content) target.content = controller.signal.aborted ? '本次回答未完成。' : '请求失败，请检查后端连接后重新提问。'
    }
  } finally {
    window.clearTimeout(timeout)
    activeRequest = null
    isThinking.value = false
    if (currentSessionId.value === requestSessionId) {
      await scrollMessages()
    }
  }
}

function retryMessage(index: number) {
  const question = messages.value.slice(0, index).reverse().find(message => message.role === 'user')
  if (question) void sendQuery(question.content)
}
</script>

<style scoped>
.clinical-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
  background:
    radial-gradient(circle at top left, oklch(0.94 0.025 195), transparent 34rem),
    linear-gradient(135deg, oklch(0.985 0.006 210), oklch(0.955 0.012 85));
  color: oklch(0.24 0.025 245);
}

.workspace-rail,
.insight-panel {
  min-height: 100vh;
  background: oklch(0.96 0.008 230 / 0.82);
  border-color: oklch(0.84 0.018 235);
  backdrop-filter: blur(10px);
}

.workspace-rail {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 24px 18px;
  border-right: 1px solid oklch(0.84 0.018 235);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: oklch(0.29 0.075 215);
  background: oklch(0.88 0.045 195);
  box-shadow: 0 10px 24px oklch(0.48 0.05 215 / 0.12);
}

.brand-kicker,
.eyebrow,
.section-label {
  color: oklch(0.48 0.035 240);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.brand-block h1,
.case-header h2,
.empty-copy h3 {
  margin: 0;
  color: oklch(0.2 0.035 245);
  font-weight: 750;
  letter-spacing: 0;
}

.brand-block h1 {
  font-size: 18px;
}

.new-session-button {
  width: 100%;
  min-height: 42px;
  border: 0;
  border-radius: 10px;
  background: oklch(0.43 0.09 225);
  box-shadow: 0 14px 24px oklch(0.38 0.08 225 / 0.2);
}

.session-list {
  display: grid;
  gap: 8px;
  min-height: 0;
  overflow: auto;
}

.session-item {
  width: 100%;
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: oklch(0.34 0.028 245);
  cursor: pointer;
  text-align: left;
  transition:
    background-color 180ms ease-out,
    border-color 180ms ease-out,
    color 180ms ease-out;
}

.session-item:hover,
.session-item.active {
  border-color: oklch(0.78 0.035 215);
  background: oklch(0.985 0.006 215);
  color: oklch(0.25 0.07 225);
}

.doctor-card {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid oklch(0.83 0.018 235);
  border-radius: 12px;
  background: oklch(0.985 0.006 220);
}

.doctor-card span,
.source-item span,
.pipeline-list span {
  display: block;
  color: oklch(0.48 0.025 245);
  font-size: 12px;
}

.doctor-card strong {
  font-size: 14px;
}

.case-workbench {
  min-width: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  gap: 14px;
  padding: 22px;
}

.case-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.case-header h2 {
  font-size: 26px;
}

.service-pill {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid oklch(0.82 0.02 225);
  border-radius: 999px;
  background: oklch(0.985 0.006 215);
  color: oklch(0.36 0.035 235);
  font-size: 13px;
  font-weight: 700;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: oklch(0.68 0.12 145);
}

.service-pill.active .status-dot {
  background: oklch(0.72 0.14 70);
}

.notice-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid oklch(0.84 0.04 80);
  border-radius: 12px;
  background: oklch(0.96 0.035 86);
  color: oklch(0.35 0.05 75);
  font-size: 13px;
}

.messages-panel {
  min-height: 0;
  overflow: auto;
  padding: 22px;
  border: 1px solid oklch(0.84 0.018 235);
  border-radius: 16px;
  background: oklch(0.992 0.004 220 / 0.92);
  box-shadow: 0 20px 60px oklch(0.36 0.04 240 / 0.1);
}

.empty-state {
  display: grid;
  gap: 24px;
}

.empty-copy {
  max-width: 58ch;
}

.empty-copy h3 {
  margin-top: 8px;
  font-size: 28px;
  line-height: 1.15;
}

.empty-copy p:last-child {
  margin-top: 10px;
  color: oklch(0.45 0.028 245);
}

.scenario-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.scenario-card {
  min-height: 128px;
  display: grid;
  grid-template-rows: auto auto 1fr;
  gap: 8px;
  padding: 16px;
  border: 1px solid oklch(0.84 0.02 230);
  border-radius: 12px;
  background: oklch(0.976 0.008 215);
  color: oklch(0.28 0.032 245);
  cursor: pointer;
  text-align: left;
  transition:
    transform 180ms ease-out,
    border-color 180ms ease-out,
    box-shadow 180ms ease-out;
}

.scenario-card:hover {
  transform: translateY(-2px);
  border-color: oklch(0.7 0.05 215);
  box-shadow: 0 16px 28px oklch(0.38 0.05 235 / 0.12);
}

.scenario-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: oklch(0.32 0.08 220);
  background: oklch(0.9 0.035 210);
}

.scenario-title {
  font-weight: 750;
}

.scenario-text {
  color: oklch(0.48 0.025 245);
  font-size: 13px;
}

.message-row {
  display: grid;
  gap: 6px;
  margin-bottom: 18px;
}

.message-meta {
  color: oklch(0.52 0.025 245);
  font-size: 12px;
  font-weight: 700;
}

.user-row {
  justify-items: end;
}

.assistant-row {
  justify-items: start;
}

.message-bubble {
  max-width: min(760px, 86%);
  padding: 14px 16px;
  border-radius: 14px;
  line-height: 1.65;
}

.user-bubble {
  color: oklch(0.98 0.006 220);
  background: oklch(0.38 0.08 225);
}

.assistant-bubble {
  border: 1px solid oklch(0.84 0.018 235);
  background: oklch(0.98 0.006 215);
  color: oklch(0.25 0.028 245);
}

.stage-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  margin-bottom: 10px;
  padding: 6px 10px;
  border: 1px solid oklch(0.78 0.035 205);
  border-radius: 999px;
  background: oklch(0.95 0.025 205);
  color: oklch(0.34 0.06 220);
  font-size: 13px;
  font-weight: 700;
}

.stage-status span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.markdown-body :deep(p) {
  margin: 0 0 10px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid oklch(0.82 0.018 235);
  padding: 8px;
  vertical-align: top;
}

.markdown-body :deep(th) {
  background: oklch(0.93 0.012 220);
  font-weight: 750;
}

.thinking-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid oklch(0.82 0.02 225);
  border-radius: 999px;
  background: oklch(0.97 0.01 215);
  color: oklch(0.42 0.035 240);
  font-size: 13px;
}

.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: end;
  padding: 14px;
  border: 1px solid oklch(0.84 0.018 235);
  border-radius: 16px;
  background: oklch(0.985 0.006 215);
  box-shadow: 0 14px 40px oklch(0.36 0.04 240 / 0.08);
}

.case-input :deep(.el-textarea__inner) {
  min-height: 74px;
  border: 0;
  box-shadow: none;
  background: oklch(0.96 0.008 215);
  color: oklch(0.24 0.025 245);
}

.send-button {
  min-width: 104px;
  min-height: 46px;
  border: 0;
  border-radius: 12px;
  background: oklch(0.43 0.09 225);
}

.insight-panel {
  display: grid;
  align-content: start;
  gap: 18px;
  padding: 24px 18px;
  border-left: 1px solid oklch(0.84 0.018 235);
}

.panel-section {
  display: grid;
  gap: 12px;
}

.pipeline-list {
  display: grid;
  gap: 10px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.pipeline-list li,
.source-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border: 1px solid oklch(0.84 0.018 235);
  border-radius: 12px;
  background: oklch(0.985 0.006 220);
}

.pipeline-index {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 9px;
  background: oklch(0.9 0.025 215);
  color: oklch(0.32 0.07 225);
  font-size: 12px;
  font-weight: 800;
}

.pipeline-list strong,
.source-item strong {
  display: block;
  color: oklch(0.27 0.03 245);
  font-size: 14px;
}

.source-list {
  display: grid;
  gap: 10px;
}

.source-item > .el-icon {
  margin-top: 2px;
  color: oklch(0.38 0.08 225);
}

@media (max-width: 1180px) {
  .clinical-shell {
    grid-template-columns: 260px minmax(0, 1fr);
  }

  .insight-panel {
    display: none;
  }
}

@media (max-width: 820px) {
  .clinical-shell {
    grid-template-columns: 1fr;
  }

  .workspace-rail {
    min-height: auto;
    border-right: 0;
    border-bottom: 1px solid oklch(0.84 0.018 235);
  }

  .session-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .case-workbench {
    padding: 14px;
  }

  .case-header,
  .composer {
    grid-template-columns: 1fr;
  }

  .case-header {
    align-items: flex-start;
  }

  .scenario-grid {
    grid-template-columns: 1fr;
  }

  .message-bubble {
    max-width: 100%;
  }
}
</style>

<style scoped>
.knowledge-version{font-size:11px;overflow-wrap:anywhere;color:#578078}.message-meta{flex-wrap:wrap;gap:8px}
</style>
