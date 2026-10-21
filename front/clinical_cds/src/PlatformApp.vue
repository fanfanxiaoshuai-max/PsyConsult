<template>
  <div class="platform-shell" :class="{ 'login-page': !identity }">
    <header class="platform-header">
      <a class="platform-brand" href="#" @click.prevent="workspace = 'personal'"><span class="brand-mark" aria-hidden="true"><img src="/images/psyconsult-logo.png" alt="" /></span><span><strong>PsyConsult</strong><small>心理健康与专业协作平台</small></span></a>
      <span v-if="!identity" class="portal-caption">统一工作平台<span>本地试用</span></span>
      <nav v-if="identity" aria-label="使用入口">
        <button :class="{ chosen: workspace === 'personal' }" @click="chooseWorkspace('personal')">个人健康空间</button>
        <button v-if="isProfessional" :class="{ chosen: workspace === 'professional' }" @click="chooseWorkspace('professional')">专业工作台</button>
        <button v-if="isProfessional" :class="{ chosen: workspace === 'knowledge' }" @click="chooseWorkspace('knowledge')">知识管理中心</button>
      </nav>
      <div v-if="identity" class="account"><span>{{ identity.display_name || identity.user_id }} · {{ roleName }}</span><el-button text @click="signOut">退出</el-button></div>
    </header>

    <main v-if="!identity" class="login-layout">
      <div class="access-frame">
        <section class="platform-cover" aria-labelledby="platform-title">
          <p class="cover-wordmark">PsyConsult</p>
          <h1 id="platform-title">心理健康<br>与临床协作</h1>
          <p class="cover-summary">面向个人与专业人员的辅助工作平台</p>
          <div class="cover-art" aria-hidden="true"><div class="cover-emblem"><img src="/images/mental-health-symbol.png" alt="" /></div><img class="cover-background" src="/images/brain-network-background.png" alt="" /></div>
          <div class="cover-capabilities"><span><el-icon aria-hidden="true"><ChatDotRound /></el-icon>科普与自评</span><span><el-icon aria-hidden="true"><Document /></el-icon>资料与报告</span><span><el-icon aria-hidden="true"><User /></el-icon>专业协作</span></div>
        </section>

        <section class="access-panel" aria-labelledby="access-title">
          <nav class="access-tabs" aria-label="登录方式">
            <button :class="{ active: loginMode !== 'token' }" :aria-pressed="loginMode !== 'token'" @click="loginMode = 'login'; error = ''"><el-icon aria-hidden="true"><User /></el-icon>个人登录</button>
            <button :class="{ active: loginMode === 'token' }" :aria-pressed="loginMode === 'token'" @click="loginMode = 'token'; error = ''"><el-icon aria-hidden="true"><Briefcase /></el-icon>专业入口</button>
          </nav>
          <div class="access-heading"><h2 id="access-title">{{ loginMode === 'register' ? '创建个人账号' : loginMode === 'token' ? '登录专业工作台' : '登录个人空间' }}</h2><p>{{ loginMode === 'register' ? '用于科普、自评和个人资料管理' : loginMode === 'token' ? '使用现有专业访问令牌' : '请输入你的账号信息' }}</p></div>
          <el-form label-position="top" @submit.prevent="signIn">
            <template v-if="loginMode !== 'token'"><el-form-item label="用户名"><el-input v-model="username" :prefix-icon="User" autocomplete="username" :placeholder="loginMode === 'register' ? '3–64位字母、数字或 . _ -' : '请输入用户名'" /></el-form-item><el-form-item v-if="loginMode === 'register'" label="称呼"><el-input v-model="displayName" maxlength="60" placeholder="请输入称呼" /></el-form-item><el-form-item label="密码"><el-input v-model="password" :prefix-icon="Lock" type="password" show-password :autocomplete="loginMode === 'register' ? 'new-password' : 'current-password'" :placeholder="loginMode === 'register' ? '至少10位' : '请输入密码'" /></el-form-item></template>
            <el-form-item v-else label="访问令牌"><el-input v-model="professionalToken" :prefix-icon="Key" type="password" show-password autocomplete="off" placeholder="请输入专业访问令牌" /></el-form-item>
            <el-alert v-if="error" :title="error" type="error" :closable="false" />
            <el-button class="access-submit" native-type="submit" type="primary" :loading="busy">{{ loginMode === 'register' ? '创建账号并登录' : '登 录' }}<span aria-hidden="true">→</span></el-button>
          </el-form>
          <div class="access-secondary" v-if="loginMode !== 'token'"><span>{{ loginMode === 'register' ? '已有个人账号？' : '还没有个人账号？' }}</span><button @click="loginMode = loginMode === 'register' ? 'login' : 'register'; error = ''">{{ loginMode === 'register' ? '返回登录' : '创建账号' }}</button></div>
          <p v-else class="access-note">个人账号与专业入口分别使用。</p>
        </section>
      </div>
      <footer class="access-footer"><span>PsyConsult · 心理健康辅助平台</span><span>仅作辅助参考，不替代专业诊断与治疗。</span></footer>
    </main>

    <template v-else>
      <div v-if="error" class="global-alert"><el-alert :title="error" type="error" closable @close="error = ''" /></div>
      <main v-if="workspace === 'personal'" class="personal-workspace">
        <section class="space-heading"><div><p class="overline">PERSONAL SPACE</p><h1>个人健康空间</h1><p>记录由你保管，分享由你决定。自动生成的解释与原始资料分别保存。</p></div><el-tag effect="plain">{{ isProfessional ? '个人使用模式' : '个人账号' }}</el-tag></section>
        <el-tabs v-model="personalTab">
          <el-tab-pane label="科普与支持" name="chat">
            <section class="public-chat panel"><div class="chat-guide"><h2>今天想从哪里开始？</h2><el-button text :disabled="chatBusy" @click="newPublicConversation">新对话</el-button><p>可以聊聊压力、睡眠、情绪，或了解心理健康知识。</p><div class="quick-topics"><el-button v-for="topic in topics" :key="topic" round @click="publicInput = topic">{{ topic }}</el-button></div></div>
              <div class="public-messages" aria-live="polite"><article v-for="(message, index) in publicMessages" :key="index" :class="['public-message', message.role]"><small>{{ message.role === 'user' ? '我的表达' : '科普与支持' }}</small><div class="prose" v-html="markdown(message.content)" /></article><p v-if="chatBusy" class="muted">{{ publicStatus }}</p></div>
              <div class="public-composer"><el-input v-model="publicInput" type="textarea" :rows="3" maxlength="4000" show-word-limit placeholder="描述你想了解的问题；不必填写真实姓名。" /><div class="composer-actions"><div><el-checkbox v-model="saveConversation" :disabled="chatBusy">保存到个人记录</el-checkbox><el-button :disabled="chatBusy || recording || transcribing || requestingMic" @click="startVoice">{{ transcribing ? '转写中…' : '语音输入' }}</el-button><el-button v-if="recording" type="warning" @click="stopVoice">结束录音</el-button></div><el-button v-if="chatBusy" @click="cancelPublic">停止生成</el-button><el-button v-else type="primary" :disabled="!publicInput.trim()" @click="sendPublic">发送</el-button></div><p v-if="voiceHint" class="muted">{{ voiceHint }}</p></div>
              <footer class="muted">提供科普与支持，不作诊断或个体处方。科普参考资料为内部试用版本；需要及时帮助时请联系专业服务。</footer>
            </section>
          </el-tab-pane>
          <el-tab-pane label="量表自评" name="assessment"><section class="panel assessment"><div class="section-heading"><div><h2>了解近期的状态</h2><p>请按最近两周的实际情况逐题作答，结果用于筛查。</p></div><el-select v-model="scale" style="width:170px" @change="resetAssessment"><el-option label="PHQ-9 情绪自评" value="PHQ-9" /><el-option label="GAD-7 焦虑自评" value="GAD-7" /></el-select></div>
            <div v-for="(item, index) in questions" :key="scale + index" class="question"><label>{{ index + 1 }}. {{ item }}</label><el-radio-group v-model="answers[index]"><el-radio v-for="(label, value) in frequencyLabels" :key="value" :value="value">{{ label }}</el-radio></el-radio-group></div>
            <el-checkbox v-model="saveAssessment">将本次作答与结果保存到个人记录</el-checkbox><el-button type="primary" :loading="busy" @click="submitAssessment">查看筛查结果</el-button>
            <div v-if="assessmentResult" class="result-card"><h3>{{ scale }}：{{ assessmentResult.total }} 分</h3><p>{{ assessmentResult.severity }}</p><el-alert v-if="assessmentResult.safety_alert" :title="assessmentResult.safety_alert" type="warning" :closable="false" /><p>量表分数不能单独用于诊断，低分也不等于排除所有问题。需要时可将本次结果授权给专业人员。</p></div>
          </section></el-tab-pane>
          <el-tab-pane label="个人记录与报告" name="records"><section class="panel"><div class="section-heading"><div><h2>我的资料</h2><p>原始资料、用户确认文字和自动解释分别保留。</p></div><el-button type="primary" @click="uploadInput?.click()">上传报告</el-button><input ref="uploadInput" hidden type="file" accept=".pdf,.docx,.png,.jpg,.jpeg" @change="uploadReport" /></div>
            <div class="note-editor"><el-input v-model="noteTitle" placeholder="记录标题，如：本周睡眠变化" maxlength="100" /><el-input v-model="personalNote" type="textarea" :rows="3" placeholder="记录你希望保留的原始情况" maxlength="12000" /><el-button :disabled="!personalNote.trim() || !noteTitle.trim()" @click="savePersonalNote">保存记录</el-button></div>
            <div v-if="!healthRecords.length" class="empty">还没有保存的资料。</div><article v-for="record in healthRecords" :key="record.id" class="record-row"><div><el-tag size="small" effect="plain">{{ kindName(record.kind) }}</el-tag><strong>{{ record.title }}</strong><small>{{ date(record.created) }} {{ statusName(record.payload.status) }}</small></div><div><el-button text @click="openRecord(record)">查看与核对</el-button><el-button text @click="archiveRecord(record)">归档隐藏</el-button></div></article>
          </section></el-tab-pane>
          <el-tab-pane label="授权与协作" name="grants"><section class="panel"><h2>选择要分享的资料</h2><p>接收人只能访问本次选中资料的固定快照。以后新增或修改的内容不会自动分享。</p><el-checkbox-group v-model="selectedRecords"><div v-for="record in healthRecords" :key="record.id"><el-checkbox :value="record.id" :disabled="['extracting','analyzing','generating'].includes(record.payload.status)">{{ record.title }} · {{ kindName(record.kind) }}</el-checkbox></div></el-checkbox-group>
            <div class="share-controls"><el-select v-model="recipient" placeholder="选择专业接收人" style="width:240px"><el-option v-for="person in professionals" :key="person.user_id" :label="person.display_name" :value="person.user_id" /></el-select><el-select v-model="grantHours" style="width:140px"><el-option label="24小时" :value="24" /><el-option label="7天" :value="168" /><el-option label="30天" :value="720" /></el-select><el-button type="primary" :disabled="!selectedRecords.length || !recipient" @click="createGrant">预览并授权</el-button></div>
            <el-dialog v-model="sharePreview" title="确认本次授权" width="680px"><p>接收人：{{ recipient }}；有效期：{{ grantHours }} 小时。</p><p>以下内容将提供给接收人，包括记录中的个人陈述、报告文字和已有自动解释。未确认内容会保留其标记。</p><article v-for="record in selectedForShare" :key="record.id" class="preview-record"><strong>{{ record.title }}</strong><pre>{{ recordPreview(record) }}</pre></article><template #footer><el-button @click="sharePreview = false">返回修改</el-button><el-button type="primary" :loading="busy" @click="confirmGrant">确认授权</el-button></template></el-dialog>
            <h3>已有授权</h3><article v-for="grant in myGrants" :key="grant.id" class="record-row"><div><strong>{{ grant.recipient }}</strong><small>到期：{{ date(grant.expires * 1000) }} · {{ grant.active ? '有效' : '已撤销或到期' }}</small></div><el-button v-if="grant.active" @click="revokeGrant(grant.id)">撤销授权</el-button></article>
          </section></el-tab-pane>
          <el-tab-pane label="专业人员反馈" name="feedback"><section class="panel"><h2>已确认并分享给你的说明</h2><p class="muted">这里展示专业人员主动确认并回传的记录。</p><article v-for="item in feedback" :key="item.id" class="feedback-card"><small>{{ item.author }} · {{ date(item.created) }}</small><div class="prose" v-html="markdown(item.body)" /></article><p v-if="!feedback.length" class="empty">暂无反馈。</p></section></el-tab-pane>
        </el-tabs>
      </main>

      <template v-else-if="isProfessional">
        <section class="professional-toolbar"><div><strong>{{ workspace === 'knowledge' ? '知识管理中心' : '专业工作台' }}</strong><span>{{ selectedCase ? '当前病例：' + selectedCase.alias : '临时问答，不关联病例' }}</span></div><div><el-button v-if="workspace === 'professional'" @click="casePanel = !casePanel">{{ casePanel ? '返回临床助手' : '病例与授权资料' }}</el-button><el-button v-if="selectedCase" @click="clearCase">切回临时问答</el-button></div></section>
        <section v-if="casePanel && workspace === 'professional'" class="case-space"><aside class="panel"><h2>病例</h2><div class="inline-form"><el-input v-model="newCaseAlias" placeholder="病例化名或编号" maxlength="100" /><el-button :disabled="!newCaseAlias.trim()" @click="createCase">新建</el-button></div><button v-for="item in caseItems" :key="item.id" class="case-choice" :class="{ chosen: selectedCase?.id === item.id }" @click="selectCase(item)">{{ item.alias }}</button><h3>授权收件箱</h3><article v-for="grant in inbox" :key="grant.id" class="inbox-item"><small>{{ grant.owner }}</small><span>{{ grant.active ? '有效授权' : '已失效' }}</span><el-button v-if="grant.active" text @click="inspectGrant(grant)">查看资料</el-button><el-button v-if="grant.active && !grant.case_id" text @click="acceptGrant(grant)">接收为新病例</el-button></article></aside>
          <section class="panel"><template v-if="caseDetail"><h2>{{ caseDetail.alias }}</h2><p class="muted">授权资料、自动回答和专业人员确认记录分别展示。撤销或到期的授权资料不再提供访问。</p><section v-for="grant in caseDetail.grants" :key="grant.id"><h3>当前有效授权资料</h3><article v-for="record in grant.records" :key="record.id" class="preview-record"><strong>{{ record.title }} · {{ kindName(record.kind) }}</strong><pre>{{ recordPreview(record) }}</pre><el-button v-if="record.kind === 'report'" text @click="downloadReport(record.id, grant.id)">下载原报告</el-button></article></section>
            <h3>整理并确认本次病例信息</h3><el-input v-model="clinicalNote" type="textarea" :rows="6" maxlength="20000" show-word-limit placeholder="核对资料后，在这里记录已确认信息；不要把模型解释直接当作患者事实。" /><el-checkbox v-model="noteConfirmed">我已核对并确认上述记录</el-checkbox><el-checkbox v-model="shareNote" :disabled="!caseDetail.subject_owner">同时回传给资料所有人</el-checkbox><div class="case-actions"><el-button :disabled="!noteConfirmed || !clinicalNote.trim()" @click="saveClinicalNote">保存确认记录</el-button><el-button type="primary" :disabled="!noteConfirmed || !clinicalNote.trim()" @click="bringToClinical">带入临床助手</el-button></div>
            <h3>专业确认记录</h3><article v-for="item in caseDetail.notes" :key="item.id" class="feedback-card"><small>{{ date(item.created) }} · {{ item.shared ? '已回传' : '仅专业工作台' }}</small><div class="prose" v-html="markdown(item.body)" /></article><h3>关联问答记录</h3><article v-for="record in caseDetail.consultations" :key="record.id" class="preview-record"><strong>{{ record.title }} · {{ statusName(record.payload.status) }}</strong><p>{{ record.payload.query }}</p><div class="prose" v-html="markdown(record.payload.answer || '')" /><small>自动生成，尚未经专业确认。</small></article>
          </template><div v-else class="empty">选择或新建病例，也可以先查看授权收件箱。</div></section>
        </section>
        <ClinicalWorkbench v-else :key="identity.user_id + ':' + workspace + ':' + (selectedCase?.id || '')" :draft="clinicalDraft" :case-id="selectedCase?.id" />
      </template>
    </template>

    <el-dialog v-model="recordOpen" :title="selectedRecord?.title || '资料详情'" width="760px"><template v-if="selectedRecord"><template v-if="selectedRecord.kind === 'report'"><p>状态：{{ statusName(selectedRecord.payload.status) }}。请对照原文件核对数字、日期和否定词。</p><el-button @click="downloadReport(selectedRecord.id)">下载原报告</el-button><el-alert v-if="selectedRecord.payload.error" :title="selectedRecord.payload.error" type="error" :closable="false" /><el-input v-if="selectedRecord.payload.extracted_text" v-model="reportText" type="textarea" :rows="12" maxlength="60000" show-word-limit /><el-checkbox v-if="selectedRecord.payload.extracted_text" v-model="reportConfirmed">我已对照原文件核对并修正识别文字</el-checkbox><div class="case-actions"><el-button :disabled="!reportConfirmed || selectedRecord.payload.status === 'analyzing'" @click="confirmReport">保存核对文字</el-button><el-button type="primary" :disabled="!selectedRecord.payload.confirmed || selectedRecord.payload.status === 'analyzing' || reportText !== selectedRecord.payload.confirmed_text" @click="analyzeReport">{{ selectedRecord.payload.analysis ? '查看已有解读' : '生成辅助解读' }}</el-button></div><p class="muted">解读会将已确认文字发送至本机配置的模型服务。保存报告时不会重复生成解读。</p><div v-if="selectedRecord.payload.analysis" class="prose" v-html="markdown(selectedRecord.payload.analysis)" /></template><template v-else><pre>{{ recordPreview(selectedRecord) }}</pre><el-button v-if="selectedRecord.kind === 'chat'" @click="continueConversation(selectedRecord)">继续这段会话</el-button></template></template></el-dialog>
    <el-dialog v-model="grantOpen" title="本次授权的资料快照" width="760px"><article v-for="record in inspectedRecords" :key="record.id" class="preview-record"><strong>{{ record.title }}</strong><pre>{{ recordPreview(record) }}</pre></article></el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { consumeChatStream } from '@/api/chatStream'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import { User, Briefcase, ChatDotRound, Document, Lock, Key } from '@element-plus/icons-vue'
import { accessToken, apiBase, headers, request, setAccessToken, type CaseDetail, type CaseItem, type Grant, type HealthRecord, type Identity } from '@/api/platform'
const ClinicalWorkbench = defineAsyncComponent(() => import('./App.vue'))
const identity = ref<Identity | null>(null), workspace = ref('personal'), personalTab = ref('chat')
const loginMode = ref('login'), username = ref(''), password = ref(''), displayName = ref(''), professionalToken = ref('')
const busy = ref(false), error = ref('')
const isProfessional = computed(() => !!identity.value && identity.value.role !== 'public')
const roleName = computed(() => ({ public: '个人账号', reader: '专业用户', reviewer: '知识审核员', admin: '管理员' })[identity.value?.role || 'public'])
const healthRecords = ref<HealthRecord[]>([]), myGrants = ref<Grant[]>([]), professionals = ref<{ user_id: string; display_name: string }[]>([]), feedback = ref<any[]>([])
const selectedRecords = ref<string[]>([]), recipient = ref(''), grantHours = ref(24), sharePreview = ref(false)
const selectedForShare = computed(() => healthRecords.value.filter(r => selectedRecords.value.includes(r.id)))
const noteTitle = ref(''), personalNote = ref(''), uploadInput = ref<HTMLInputElement>()
const recordOpen = ref(false), selectedRecord = ref<HealthRecord | null>(null), reportText = ref(''), reportConfirmed = ref(false)
const casePanel = ref(false), caseItems = ref<CaseItem[]>([]), selectedCase = ref<CaseItem | null>(null), caseDetail = ref<CaseDetail | null>(null), inbox = ref<Grant[]>([])
const newCaseAlias = ref(''), clinicalNote = ref(''), noteConfirmed = ref(false), shareNote = ref(false), clinicalDraft = ref('')
const grantOpen = ref(false), inspectedRecords = ref<HealthRecord[]>([])
let caseSelection = 0
const publicInput = ref(''), publicMessages = ref<{ role: string; content: string }[]>([]), publicStatus = ref(''), chatBusy = ref(false), saveConversation = ref(false), conversationId = ref<string | null>(null)
let chatController: AbortController | null = null
function cancelPublic() { chatController?.abort() }
function newPublicConversation() { publicMessages.value = []; conversationId.value = null; publicInput.value = '' }
let poll: ReturnType<typeof setInterval> | undefined
const topics = ['最近压力大，怎样照顾自己？', '睡不好时可以从哪里开始调整？', '量表分数能说明什么？']
const frequencyLabels = ['完全没有', '有几天', '一半以上天数', '几乎每天']
const scale = ref('PHQ-9'), answers = ref<(number | undefined)[]>(Array(9).fill(undefined)), saveAssessment = ref(false), assessmentResult = ref<any>(null)
const phq = ['做事时提不起劲或没有兴趣', '感到心情低落、沮丧或绝望', '入睡困难、睡不安稳或睡眠过多', '感觉疲倦或没有活力', '食欲不振或吃得太多', '觉得自己很糟、很失败，或让自己及家人失望', '难以集中注意力，例如阅读或看电视时', '动作或说话变慢，或坐立不安、活动比平常多', '有不如死掉或以某种方式伤害自己的念头']
const gad = ['感到紧张、焦虑或急切', '不能停止或控制担忧', '对各种事情担忧过多', '很难放松下来', '由于不安而无法静坐', '容易烦恼或急躁', '感到害怕，似乎有可怕的事情要发生']
const questions = computed(() => scale.value === 'PHQ-9' ? phq : gad)
function resetAssessment() { answers.value = Array(questions.value.length).fill(undefined); assessmentResult.value = null }
function markdown(text: string) { return DOMPurify.sanitize(marked.parse(text, { async: false }) as string) }
function date(value: string | number) { return new Date(value).toLocaleString('zh-CN') }
function kindName(kind: string) { return ({ note: '个人陈述', report: '报告', assessment: '自评', chat: '科普会话', clinical_chat: '临床辅助问答' })[kind] || kind }
function statusName(status?: string) { return ({ extracting: '文字提取中', extracted: '待人工核对', confirmed: '文字已确认', analyzing: '解读中', analyzed: '已有解读', error: '处理未完成', complete: '已完成', interrupted: '未完成', generating: '生成中' })[status || ''] || '' }
function recordPreview(record: HealthRecord) {
  const p = record.payload
  if (record.kind === 'note') return String(p.text || '')
  if (record.kind === 'assessment') return `${p.scale_type} · ${p.total}分 · ${p.severity}\n逐题作答：${p.answers.join('、')}\n${p.safety_alert || ''}\n仅用于筛查。`
  if (record.kind === 'chat') return (p.messages || []).map((m: any) => `${m.role === 'user' ? '用户原话' : '自动回答'}：${m.content}`).join('\n\n')
  return `人工核对：${p.confirmed ? '已确认识别文字' : '尚未确认'}\n${p.confirmed_text || p.extracted_text || '文字处理尚未完成'}\n\n自动解释（不作为患者事实）：\n${p.analysis || '尚未生成'}`
}
async function act(fn: () => Promise<void>) { error.value = ''; try { await fn() } catch (e) { error.value = e instanceof Error ? e.message : '操作未完成' } }
async function loadPersonal() {
  const token = accessToken()
  const [r, g, p, f] = await Promise.all([request('/records'), request('/grants'), request('/professionals'), request('/feedback')])
  if (token !== accessToken()) return
  healthRecords.value = r.items; myGrants.value = g.items; professionals.value = p.items; feedback.value = f.items
  const selected = selectedRecord.value
  if (selected) {
    const newer = healthRecords.value.find(r => r.id === selected.id)
    if (newer) {
      if (selected.payload.status === 'extracting' && newer.payload.status !== 'extracting') reportText.value = newer.payload.confirmed_text || newer.payload.extracted_text || ''
      selectedRecord.value = newer
    }
  }
}
async function loadProfessional() { if (!isProfessional.value) return; const [c, i] = await Promise.all([request('/cases'), request('/inbox')]); caseItems.value = c.items; inbox.value = i.items }
async function restoreIdentity() { identity.value = await request<Identity>('/identity'); workspace.value = isProfessional.value ? (location.hash === '#candidate' ? 'knowledge' : 'professional') : 'personal'; await loadPersonal(); await loadProfessional() }
async function signIn() { busy.value = true; await act(async () => {
  if (loginMode.value === 'token') setAccessToken(professionalToken.value.trim())
  else {
    if (loginMode.value === 'register') await request('/auth/register', { username: username.value, password: password.value, display_name: displayName.value })
    const session = await request('/auth/login', { username: username.value, password: password.value }); setAccessToken(session.token)
  }
  try { await restoreIdentity() } catch (e) { setAccessToken(''); identity.value = null; throw e }
  password.value = ''; professionalToken.value = ''
}); busy.value = false }
async function signOut() {
  caseSelection++; chatController?.abort(); if (voiceRecorder?.state === 'recording') { discardVoice = true; voiceRecorder.stop() }
  await request('/auth/logout', {}).catch(() => {}); setAccessToken(''); identity.value = null
  healthRecords.value = []; publicMessages.value = []; conversationId.value = null; selectedCase.value = null; caseDetail.value = null; clinicalDraft.value = ''; selectedRecord.value = null; recordOpen.value = false; grantOpen.value = false; inspectedRecords.value = []; selectedRecords.value = []
  personalNote.value = ''; noteTitle.value = ''; reportText.value = ''; reportConfirmed.value = false; clinicalNote.value = ''; noteConfirmed.value = false; shareNote.value = false; publicInput.value = ''; assessmentResult.value = null; resetAssessment(); myGrants.value = []; professionals.value = []; feedback.value = []; caseItems.value = []; inbox.value = []; username.value = ''; password.value = ''; displayName.value = ''; loginMode.value = 'login'; error.value = ''
}
function chooseWorkspace(value: string) { if (chatBusy.value || recording.value || transcribing.value) { ElMessage.info('请先结束当前操作'); return }; workspace.value = value; casePanel.value = false; window.history.replaceState(null, '', location.pathname + (value === 'knowledge' ? '#candidate' : '')); if (value === 'professional') void act(loadProfessional) }
async function savePersonalNote() { await act(async () => { await request('/records', { title: noteTitle.value, text: personalNote.value }); noteTitle.value = ''; personalNote.value = ''; await loadPersonal() }) }
async function archiveRecord(record: HealthRecord) { await act(async () => { await request(`/records/${record.id}/archive`, {}); await loadPersonal() }) }
async function submitAssessment() { if (answers.value.some(a => a === undefined)) { error.value = '请逐题完成作答'; return }; busy.value = true; await act(async () => { assessmentResult.value = await request('/assessments', { scale_type: scale.value, answers: answers.value, save: saveAssessment.value }); await loadPersonal() }); busy.value = false }
async function uploadReport(event: Event) { const input = event.target as HTMLInputElement; const file = input.files?.[0]; input.value = ''; if (!file) return; const startedWith = accessToken(); await act(async () => {
  if (file.size > 20 * 1024 * 1024) throw new Error('文件不能超过20MB')
  const body = new FormData(); body.append('file', file)
  const response = await fetch(`${apiBase}/api/platform/reports`, { method: 'POST', headers: headers(), body, signal: AbortSignal.timeout(30000) }); const payload = await response.json()
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '上传未完成')
  if (startedWith !== accessToken()) return
  await loadPersonal(); openRecord(payload)
}) }
function continueConversation(record: HealthRecord) { if (chatBusy.value) return; publicMessages.value = (record.payload.messages || []).map((m: any) => ({ role: m.role, content: m.content })); conversationId.value = record.id; saveConversation.value = true; personalTab.value = 'chat'; recordOpen.value = false }
function openRecord(record: HealthRecord) { selectedRecord.value = record; reportText.value = record.payload.confirmed_text || record.payload.extracted_text || ''; reportConfirmed.value = false; recordOpen.value = true }
async function confirmReport() { await act(async () => { if (!selectedRecord.value) return; selectedRecord.value = await request(`/reports/${selectedRecord.value.id}/confirm`, { text: reportText.value }); await loadPersonal() }) }
async function analyzeReport() { await act(async () => { if (!selectedRecord.value || selectedRecord.value.payload.analysis) return; selectedRecord.value = await request(`/reports/${selectedRecord.value.id}/analyze`, {}); await loadPersonal() }) }
async function downloadReport(id: string, grantId?: string) { await act(async () => { const response = await fetch(`${apiBase}/api/platform/reports/${id}/download${grantId ? '?grant_id=' + encodeURIComponent(grantId) : ''}`, { headers: headers() }); if (!response.ok) throw new Error('文件不存在或授权已失效'); const url = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href = url; a.download = selectedRecord.value?.title || '报告'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }) }
function createGrant() { sharePreview.value = true }
async function confirmGrant() { busy.value = true; await act(async () => { await request('/grants', { recipient: recipient.value, record_ids: selectedRecords.value, hours: grantHours.value }); sharePreview.value = false; selectedRecords.value = []; await loadPersonal(); ElMessage.success('授权已保存') }); busy.value = false }
async function revokeGrant(id: string) { await act(async () => { await request(`/grants/${id}/revoke`, {}); await loadPersonal() }) }
async function inspectGrant(grant: Grant) { await act(async () => { const value = await request(`/grants/${grant.id}`); inspectedRecords.value = value.records; grantOpen.value = true }) }
async function acceptGrant(grant: Grant) { await act(async () => { const value = await request(`/inbox/${grant.id}/accept`, { alias: '授权病例 ' + grant.owner.slice(-6) }); await loadProfessional(); const item = caseItems.value.find(c => c.id === value.case_id); if (item) await selectCase(item) }) }
async function createCase() { await act(async () => { const value = await request('/cases', { alias: newCaseAlias.value }); newCaseAlias.value = ''; await loadProfessional(); const item = caseItems.value.find(c => c.id === value.id); if (item) await selectCase(item) }) }
async function selectCase(item: CaseItem) { const selection = ++caseSelection; await act(async () => { const detail = await request<CaseDetail>(`/cases/${item.id}`); if (selection !== caseSelection) return; selectedCase.value = item; caseDetail.value = detail; clinicalNote.value = ''; noteConfirmed.value = false; shareNote.value = false; clinicalDraft.value = '' }) }
function clearCase() { caseSelection++; selectedCase.value = null; caseDetail.value = null; clinicalDraft.value = ''; clinicalNote.value = ''; noteConfirmed.value = false }
async function saveClinicalNote() { await act(async () => { if (!selectedCase.value) return; await request(`/cases/${selectedCase.value.id}/notes`, { body: clinicalNote.value, confirmed: true, share_with_owner: shareNote.value }); caseDetail.value = await request<CaseDetail>(`/cases/${selectedCase.value.id}`); await loadPersonal(); ElMessage.success('确认记录已保存') }) }
function bringToClinical() { if (!noteConfirmed.value) return; if (clinicalNote.value.length > 3400) { error.value = '资料超过临床输入长度，请整理至3400字以内后带入；完整记录仍会保留。'; return }; clinicalDraft.value = `以下为专业人员本次核对的病例资料：\n${clinicalNote.value}\n\n本轮需要协助的问题：`; casePanel.value = false }

async function sendPublic() {
  const query = publicInput.value.trim(); if (!query || chatBusy.value) return; const startedWith = accessToken()
  if (!saveConversation.value) conversationId.value = null
  publicInput.value = ''; publicMessages.value.push({ role: 'user', content: query }); const output = { role: 'assistant', content: '' }; publicMessages.value.push(output)
  const index = publicMessages.value.length - 1; chatBusy.value = true; publicStatus.value = '正在接收问题…'; chatController = new AbortController(); const controller = chatController
  await act(async () => {
    const response = await fetch(`${apiBase}/api/platform/chat`, { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({ query, save: saveConversation.value, conversation_id: saveConversation.value ? conversationId.value : null, history: publicMessages.value.slice(0, -2).slice(-12) }), signal: controller.signal })
    if (!response.ok || !response.body) { const p = await response.json().catch(() => ({})); throw new Error(typeof p.detail === 'string' ? p.detail : '问答未能开始') }
    const body = response.body
    const timeout = setTimeout(() => controller.abort(), 130000)
    try {
      await consumeChatStream(body, value => {
        if (controller.signal.aborted) throw new Error('本次回答已停止')
        if (startedWith !== accessToken()) throw new Error('账号已切换，本轮结果不再显示')
        const extra = value as typeof value & { record_id?: string }
        if (extra.record_id) conversationId.value = extra.record_id
        if (value.error || value.failed) throw new Error(value.content || '本轮未完成')
        if (value.agent && value.content && publicMessages.value[index]) publicMessages.value[index]!.content += value.content
        else if (value.content) publicStatus.value = value.content
      })
    } finally { clearTimeout(timeout) }
  })
  chatBusy.value = false; publicStatus.value = ''; if (identity.value && startedWith === accessToken()) await act(loadPersonal)
}

const recording = ref(false), transcribing = ref(false), voiceHint = ref(''), requestingMic = ref(false)
let voiceRecorder: MediaRecorder | null = null, voiceStream: MediaStream | null = null, voiceTimer: ReturnType<typeof setTimeout> | undefined, discardVoice = false
async function startVoice() { if (recording.value || transcribing.value || requestingMic.value) return; requestingMic.value = true; const startedWith = accessToken(); try { await act(async () => {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') throw new Error('当前浏览器不支持录音，请使用文字输入')
  voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true }); if (startedWith !== accessToken()) { voiceStream.getTracks().forEach(t => t.stop()); return }; discardVoice = false
  const mime = ['audio/webm', 'audio/ogg', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported(t)); voiceRecorder = new MediaRecorder(voiceStream, mime ? { mimeType: mime } : undefined); const chunks: BlobPart[] = []
  voiceRecorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
  voiceRecorder.onstop = () => { clearTimeout(voiceTimer); recording.value = false; voiceStream?.getTracks().forEach(t => t.stop()); if (!discardVoice) void transcribe(new Blob(chunks, { type: voiceRecorder?.mimeType || 'audio/webm' })) }
  voiceRecorder.start(); recording.value = true; voiceHint.value = '录音中，最长约5分钟。结束后先核对转写文字，再发送。'; voiceTimer = setTimeout(stopVoice, 290000)
}) } finally { requestingMic.value = false; if (!recording.value) voiceStream?.getTracks().forEach(t => t.stop()) } }
function stopVoice() { if (voiceRecorder?.state === 'recording') voiceRecorder.stop() }
async function transcribe(blob: Blob) { const startedWith = accessToken(); transcribing.value = true; await act(async () => { if (blob.size > 7 * 1024 * 1024) throw new Error('录音过大，请缩短后重试'); const body = new FormData(); body.append('file', blob, 'recording.webm'); const response = await fetch(`${apiBase}/api/transcribe`, { method: 'POST', headers: headers(), body, signal: AbortSignal.timeout(95000) }); const value = await response.json(); if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : '转写失败'); if (startedWith !== accessToken()) return; publicInput.value = [publicInput.value, value.text].filter(Boolean).join('\n'); voiceHint.value = '文字已转写到输入框，请核对药名、数字和否定词后发送。' }); transcribing.value = false }
onMounted(async () => { if (accessToken()) await act(async () => { try { await restoreIdentity() } catch (e) { setAccessToken(''); identity.value = null; throw e } }); poll = setInterval(() => { if (identity.value && healthRecords.value.some(r => ['extracting','analyzing'].includes(r.payload.status))) void act(loadPersonal) }, 2500) })
onBeforeUnmount(() => { clearInterval(poll); chatController?.abort(); discardVoice = true; stopVoice(); voiceStream?.getTracks().forEach(t => t.stop()) })
</script>

<style scoped>
.platform-shell{min-height:100vh;background:oklch(98% .008 240);color:oklch(29% .035 245);font-family:Inter,'Microsoft YaHei',sans-serif}.platform-header{min-height:76px;background:white;border-bottom:1px solid oklch(91% .015 240);display:flex;align-items:center;justify-content:space-between;gap:22px;padding:12px 32px;position:relative;z-index:2}.platform-brand{display:flex;gap:12px;align-items:center;text-decoration:none;color:inherit}.platform-brand strong{display:block;font-size:20px;letter-spacing:.02em}.platform-brand small{font-size:11px;color:oklch(53% .025 245)}.brand-symbol{display:grid;place-items:center;width:42px;height:42px;background:oklch(49% .09 205);border-radius:14px;color:white;font-size:23px}.platform-header nav{display:flex;gap:8px}.platform-header nav button{border:0;background:transparent;padding:11px 16px;border-radius:9px;cursor:pointer;font:inherit;color:oklch(48% .03 245)}.platform-header nav button.chosen{background:oklch(94% .035 205);color:oklch(39% .09 205)}.account{display:flex;align-items:center;gap:8px;font-size:12px;max-width:290px;overflow-wrap:anywhere}.overline{font-size:12px;letter-spacing:.14em;font-weight:600;color:oklch(48% .08 205)}.muted{color:oklch(53% .025 245);font-size:12px;line-height:1.8}.personal-workspace{max-width:1200px;padding:32px;margin:0 auto}.space-heading,.section-heading{display:flex;gap:20px;align-items:center;justify-content:space-between;margin-bottom:22px}.space-heading h1{margin:8px 0;font-size:29px}.space-heading p,.section-heading p{color:oklch(52% .025 245);font-size:14px;line-height:1.7}.panel{background:white;border:1px solid oklch(91% .015 240);border-radius:16px;padding:26px}.panel h2{font-size:20px;margin:0 0 14px}.public-chat{max-width:900px;margin:0 auto}.chat-guide{padding:10px 0 24px;border-bottom:1px solid oklch(94% .012 240)}.chat-guide p{font-size:14px;color:oklch(53% .025 245)}.quick-topics{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}.public-messages{max-height:540px;overflow:auto;padding:14px 0;min-height:140px}.public-message{padding:16px 20px;margin:14px 0;border-radius:12px;background:oklch(98% .007 230)}.public-message.user{background:oklch(95% .025 205);margin-left:12%}.public-message small{color:oklch(48% .07 205);font-size:11px}.composer-actions{display:flex;justify-content:space-between;gap:12px;margin:12px 0}.question{padding:18px 0;border-bottom:1px solid oklch(94% .01 240)}.question label{display:block;margin-bottom:12px;font-size:14px}.assessment>.el-checkbox{margin:20px}.result-card,.feedback-card{background:oklch(97% .018 205);padding:20px;border-radius:12px;margin-top:20px}.note-editor{display:grid;gap:12px;margin:22px 0}.note-editor>.el-button{justify-self:start}.record-row{display:flex;justify-content:space-between;gap:20px;align-items:center;padding:18px 0;border-top:1px solid oklch(94% .01 240)}.record-row strong{margin-left:10px;font-size:14px}.record-row small{display:block;margin-top:8px;color:oklch(53% .025 245);font-size:12px}.share-controls{display:flex;gap:12px;margin:24px 0;flex-wrap:wrap}.empty{padding:50px 20px;text-align:center;color:oklch(57% .02 245)}.preview-record{border:1px solid oklch(91% .02 240);padding:16px;margin:14px 0;border-radius:10px}.preview-record pre,pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.85;font-size:13px;max-height:500px;overflow:auto}.professional-toolbar{display:flex;justify-content:space-between;align-items:center;padding:14px 28px;background:oklch(96% .02 210);border-bottom:1px solid oklch(90% .02 220)}.professional-toolbar span{margin-left:18px;font-size:12px;color:oklch(49% .03 245)}.case-space{display:grid;grid-template-columns:300px minmax(0,1fr);gap:22px;padding:24px;max-width:1450px;margin:auto}.case-choice{display:block;width:100%;text-align:left;border:1px solid oklch(92% .02 220);background:white;padding:13px;border-radius:9px;margin:10px 0;cursor:pointer}.case-choice.chosen{background:oklch(94% .04 205);border-color:oklch(70% .08 205)}.inline-form{display:flex;gap:8px;margin:18px 0}.inbox-item{display:grid;gap:8px;padding:12px 0;border-top:1px solid oklch(93% .01 220);overflow-wrap:anywhere;font-size:12px}.case-actions{display:flex;gap:12px;margin:16px 0}.global-alert{padding:12px 24px}.prose{line-height:1.85;overflow-wrap:anywhere;font-size:14px}.prose :deep(table){border-collapse:collapse;width:100%}.prose :deep(td),.prose :deep(th){border:1px solid oklch(88% .02 240);padding:8px}.prose :deep(a){color:oklch(45% .1 220)}:deep(.el-tabs__item){height:52px}:deep(.el-radio){margin-right:22px}
@media(max-width:1000px){.platform-header{flex-wrap:wrap;padding:14px 20px}.account{max-width:100%}.case-space{grid-template-columns:1fr}.personal-workspace{padding:20px}.professional-toolbar{flex-wrap:wrap;gap:12px}}
@media(max-width:600px){.platform-header nav{width:100%;overflow:auto}.platform-header nav button{white-space:nowrap;padding:9px 11px}.space-heading,.section-heading{align-items:flex-start;flex-wrap:wrap}.panel{padding:18px}.record-row,.composer-actions{flex-wrap:wrap}.question :deep(.el-radio-group){display:grid}.professional-toolbar span{display:block;margin:8px 0}.public-message.user{margin-left:5%}}
/* Entry page: a compact institutional workspace, independent of clinical UI. */
.login-page{background:#f2f6fa;color:#203447;font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif}
.login-page .platform-header{height:82px;min-height:82px;padding:0 max(32px,calc((100vw - 1160px)/2));border-bottom:1px solid #e3e9ee;background:#fff}
.login-page .platform-brand{gap:14px}.brand-mark{height:50px;width:50px;flex-shrink:0}
.login-page .platform-brand strong{font-family:Georgia,"Times New Roman",serif;font-size:32px;font-weight:600;line-height:1.15;letter-spacing:-1.2px;color:#1c3f5c}.login-page .platform-brand small{display:block;margin-top:5px;font-size:11px;color:#71808d;letter-spacing:.04em}
.portal-caption{display:flex;align-items:center;gap:16px;font-size:12px;color:#687a88}.portal-caption>span{border:1px solid #dce5eb;border-radius:4px;padding:4px 8px;font-size:11px;color:#7b8995}
.login-layout{width:min(1160px,calc(100% - 64px));margin:0 auto;padding:64px 0 26px}
.access-frame{display:grid;grid-template-columns:1.06fr 1fr;min-height:584px;background:#fff;border:1px solid #dfe7ed;border-radius:14px;overflow:hidden;box-shadow:0 12px 36px #18394d08}
.platform-cover{position:relative;padding:50px 48px 30px;background:#e9f2fa;color:#244a67;display:flex;flex-direction:column;overflow:hidden}
.cover-wordmark{margin:0 0 48px;font-family:Georgia,"Times New Roman",serif;font-size:54px;font-weight:400;line-height:1.1;letter-spacing:-2.2px;color:#234760}
.platform-cover h1{font-size:33px;line-height:1.55;font-weight:500;letter-spacing:.045em;margin:0 0 16px;color:#294f6c}
.cover-summary{font-size:13px;line-height:1.8;letter-spacing:.025em;color:#526b7e;margin:0}.cover-rule{display:block;width:54px;height:1px;background:#a6bbb2;margin-top:34px;opacity:.65}
.cover-capabilities{display:flex;align-items:center;gap:0;border-top:1px solid #c9dce9;padding-top:22px;margin-top:auto;color:#526b7e;font-size:12px;letter-spacing:.035em}.cover-capabilities span+span:before{content:"";display:inline-block;width:1px;height:10px;background:#a6c7d23d;margin:0 18px}
.access-panel{padding:44px 58px 38px;align-self:center;min-width:0}.access-tabs{display:flex;padding:4px;background:#f1f5f7;border-radius:7px;gap:4px;margin-bottom:34px}.access-tabs button{flex:1;border:0;border-radius:5px;padding:10px 8px;font:inherit;font-size:13px;color:#6a7d8a;background:transparent;cursor:pointer}.access-tabs button.active{background:white;color:#285578;box-shadow:0 1px 5px #14394f12;font-weight:600}
.access-heading h2{font-size:23px;font-weight:600;letter-spacing:.015em;margin:0 0 10px;color:#1b3447}.access-heading p{font-size:12px;line-height:1.7;color:#84909b;margin:0 0 30px}
.access-panel :deep(.el-form-item){margin-bottom:22px}.access-panel :deep(.el-form-item__label){font-size:12px;font-weight:500;color:#526675;padding-bottom:8px;line-height:20px;height:auto}.access-panel :deep(.el-input__wrapper){border-radius:6px;background:#fff;box-shadow:0 0 0 1px #dce4ea inset;padding:0 13px}.access-panel :deep(.el-input__wrapper:hover){box-shadow:0 0 0 1px #9eafb9 inset}.access-panel :deep(.el-input__wrapper.is-focus){box-shadow:0 0 0 1.5px #32647a inset}.access-panel :deep(.el-input__inner){height:44px;font-size:13px;color:#283e4f}.access-panel :deep(.el-input__inner::placeholder){color:#a5b0b9;font-size:12px}
.access-submit.el-button{display:flex;justify-content:space-between;width:100%;height:45px;padding:0 18px;margin-top:9px;border-radius:6px;background:#285578;border-color:#285578;font-size:14px;font-weight:500}.access-submit.el-button:hover{background:#24566c;border-color:#24566c}.access-submit :deep(>span){display:flex;justify-content:space-between;width:100%;align-items:center}.access-submit :deep(>span>span){font-size:18px;opacity:.7}
.access-secondary{display:flex;align-items:center;justify-content:center;gap:7px;margin-top:24px;font-size:12px;color:#8a969f}.access-secondary button{padding:3px 0;border:0;background:transparent;font:inherit;font-size:12px;color:#2a6077;cursor:pointer}.access-note{text-align:center;color:#8a969f;font-size:12px;line-height:1.8;margin:24px 0 0}
.access-footer{display:flex;justify-content:space-between;gap:20px;padding-top:24px;color:#8c99a3;font-size:11px;line-height:1.7}.access-tabs button:focus-visible,.access-secondary button:focus-visible{outline:2px solid #3c829b;outline-offset:3px}
@media(min-width:1500px){.login-layout{padding-top:88px}}
@media(max-width:1000px){.access-frame{grid-template-columns:1fr 1fr}.platform-cover{padding:40px 30px 28px}.access-panel{padding:36px 30px}.platform-cover h1{font-size:31px}.cover-wordmark{font-size:38px}.cover-capabilities span+span:before{margin:0 11px}.login-layout{padding-top:40px}}
@media(max-width:700px){.login-page .platform-header{height:70px;min-height:70px;padding:0 22px}.portal-caption{display:none}.login-layout{width:calc(100% - 32px);padding-top:24px}.access-frame{grid-template-columns:1fr;min-height:0;border-radius:10px}.platform-cover{padding:25px 28px 24px}.cover-wordmark{font-size:36px;margin-bottom:18px;letter-spacing:-1.3px}.login-page .brand-mark{width:44px;height:44px}.login-page .platform-brand strong{font-size:28px}.platform-cover h1{font-size:25px;line-height:1.5;margin-bottom:10px}.platform-cover h1 br{display:none}.cover-summary{font-size:11px}.cover-rule{display:none}.cover-capabilities{font-size:10px;padding-top:15px;margin-top:18px}.cover-capabilities span+span:before{margin:0 13px}.access-panel{padding:26px 28px 30px}.access-tabs{margin-bottom:26px}.access-heading h2{font-size:21px}.access-heading p{margin-bottom:24px}.access-footer{flex-direction:column;gap:4px;padding:18px 4px;text-align:center;font-size:10px}}



.cover-capabilities>span{display:inline-flex;gap:7px;align-items:center;white-space:nowrap}
.cover-capabilities .el-icon{font-size:16px;color:#7895ab}
.cover-capabilities span+span:before{margin:0 12px 0 5px;background:#bed0df}
.access-tabs button{display:flex;align-items:center;justify-content:center;gap:8px}.access-tabs .el-icon{font-size:16px}
.access-panel :deep(.el-input__prefix){color:#8199ab;margin-right:4px}
@media(max-width:1000px){.cover-capabilities{font-size:11px}.cover-capabilities>span{gap:5px}.cover-capabilities span+span:before{margin:0 7px 0 3px}}
@media(max-width:700px){.cover-capabilities{font-size:10px}.cover-capabilities .el-icon{font-size:14px}.cover-capabilities span+span:before{margin:0 9px 0 3px}}

.platform-cover{isolation:isolate}

.platform-cover>:not(.cover-background){position:relative;z-index:1}
@media(max-width:1000px){}
@media(max-width:700px){}

/* The illustration blends into the cover: no white tile, disc, border or shadow. */


@media(max-width:1000px){}
@media(max-width:700px){}

/* One quiet illustration band, with separate grid cells rather than floating marks. */
.cover-art{display:grid;grid-template-columns:38% 62%;align-items:center;gap:0;height:160px;margin:20px 0 16px;mix-blend-mode:multiply;pointer-events:none;user-select:none}
.cover-art .cover-emblem{position:static;width:100%;height:145px;opacity:.14}
.cover-art .cover-emblem img{display:block;width:100%;height:100%;object-fit:cover;filter:grayscale(1)}
.cover-art .cover-background{position:static;display:block;width:100%;height:160px;object-fit:cover;filter:grayscale(1);opacity:.24;max-width:100%}
@media(max-width:1000px){.cover-art{height:145px;margin-top:18px}.cover-art .cover-emblem{height:120px}.cover-art .cover-background{height:145px}}
@media(max-width:700px){.cover-art{grid-template-columns:40% 60%;height:78px;margin:12px 0 2px}.cover-art .cover-emblem{height:76px}.cover-art .cover-background{height:78px}.cover-capabilities{margin-top:14px}}

/* Compact source artwork, framed only by the wordmark lockup. */
.platform-brand .brand-mark{position:relative;display:block;width:44px;height:50px;flex-shrink:0;overflow:hidden;mix-blend-mode:multiply;opacity:.88}
.platform-brand .brand-mark img{position:absolute;display:block;width:110px;height:auto;max-width:none;left:50%;top:50%;transform:translate(-50%,-50%)}
.login-page .platform-brand{gap:12px}
@media(max-width:700px){.platform-brand .brand-mark,.login-page .platform-brand .brand-mark{width:38px;height:44px}.platform-brand .brand-mark img{width:96px}}

</style>
