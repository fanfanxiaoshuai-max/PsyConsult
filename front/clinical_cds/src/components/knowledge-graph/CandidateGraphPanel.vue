<template>
  <main class="candidate-panel">
    <header class="preview-header">
      <div><p class="eyebrow">知识图谱 / 审核记录</p><h2>知识审核与版本管理</h2><p class="subtitle">查看修订后的知识、原文依据和待解决问题。</p></div>
      <div class="header-actions"><el-button :loading="statsBusy" @click="refresh">重新加载</el-button><el-button :loading="downloading" @click="download">导出审核记录</el-button></div>
    </header>
    <div v-if="workflow" class="metrics">
      <div><strong>{{ workflow.counts.approved || 0 }}</strong><span>项审核通过</span></div>
      <div><strong>{{ workflow.total }}</strong><span>项记录可追溯</span></div>
      <div><strong>{{ (workflow.counts.blocked || 0) + (workflow.counts.returned || 0) }}</strong><span>项待处理</span></div>
      <div><strong>{{ workflow.releases.length }}</strong><span>个已发布版本</span></div>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-tabs v-model="tab" @tab-change="tabChanged">
      <el-tab-pane label="知识浏览" name="knowledge">
        <el-radio-group v-model="knowledgeView" @change="viewChanged" size="small" aria-label="知识数据版本"><el-radio-button value="working">工作版本</el-radio-button><el-radio-button value="active" :disabled="role !== 'admin' || !workflow?.active">已启用版本</el-radio-button></el-radio-group>
        <p class="small-note">{{ knowledgeView === 'active' ? '正在浏览已启用的发布快照。' : '正在浏览工作版本；发布内容按审核结果筛选。' }}</p>
        <form class="query-form" @submit.prevent="search">
          <el-input v-model="query" aria-label="知识搜索" placeholder="输入疾病、症状、药物或编码" maxlength="200" clearable />
          <el-button type="primary" native-type="submit" :disabled="!query.trim()" :loading="busy">搜索</el-button>
        </form>
        <div class="examples"><span>试试</span><button v-for="name in examples" :key="name" @click="example(name)">{{ name }}</button></div>
        <p v-if="searched" class="search-result" aria-live="polite">{{ searchMessage }}</p>
        <div class="knowledge-layout">
          <aside class="entity-list" aria-label="实体列表">
            <button v-for="entity in results" :key="entity.id" :class="{ selected: detail?.entity.id === entity.id }" @click="focus(entity)"><strong>{{ entity.name }}</strong><span>查看知识记录</span></button>
            <p v-if="!results.length">搜索后在此选择实体。</p>
          </aside>
          <section class="knowledge-body" v-loading="loadingDetail">
            <template v-if="detail">
              <div class="entity-heading"><div><h3>{{ detail.entity.name }}</h3><p>{{ detail.records.length }} 条带适用条件的记录</p></div><el-button size="small" @click="openReviews">查看相关审核条目</el-button></div>
              <p v-if="detail.review_counts.insufficient || detail.review_counts.withdrawn" class="open-note">相关原始条目中：{{ detail.review_counts.insufficient }} 项依据不足，{{ detail.review_counts.withdrawn }} 项已撤销。它们不作为下方有效结论展示。</p>
              <el-radio-group v-model="display" size="small" aria-label="展示方式"><el-radio-button value="cards">知识与证据</el-radio-button><el-radio-button value="graph">关系预览</el-radio-button></el-radio-group>
              <GraphCanvas v-if="display === 'graph'" :nodes="graphNodes" :edges="graphEdges" :active="active" :center-id="detail.entity.id" :selected-id="selectedRecord" selected-edge-id="" @select-node="selectRecord" @select-edge="selectRecord" @expand="selectRecord" />
              <p v-if="display === 'graph'" class="small-note">图中连线汇集两个实体之间的全部条件记录。点击实体或连线，下方显示对应记录。</p>
              <div class="record-cards">
                <article v-for="record in visibleRecords" :key="record.id" :class="{ highlighted: selectedRecordIds?.has(record.id) }">
                  <div class="record-label"><span>来源已核对</span><span>{{ record.evidence.map(e => region(e.region)).join(' / ') }}</span></div>
                  <p class="record-subject">涉及：{{ record.subject_name }}<span v-if="record.related_name"> · 关联对象：{{ record.related_name }}</span></p>
                  <h4>{{ record.title }}</h4>
                  <p v-for="(proof, i) in record.evidence" :key="i" class="conditions">{{ proof.scope_conditions }}</p>
                  <el-collapse><el-collapse-item title="查看具体条件与原文定位" :name="record.id">
                    <dl class="conditions-list"><template v-for="(value, key) in record.context" :key="key"><dt>{{ fieldLabel(String(key)) }}</dt><dd><pre>{{ format(value) }}</pre></dd></template></dl>
                    <div v-for="(proof, i) in record.evidence" :key="i" class="proof">
                      <a v-if="sourceLink(proof.source_id)" :href="sourceLink(proof.source_id)" target="_blank" rel="noopener noreferrer">{{ proof.source_title }}</a><span v-else>{{ proof.source_title }}</span>
                      <p>{{ region(proof.region) }} · {{ proof.edition || '版本以所绑定原文为准' }} · 定位：{{ format(proof.locator) }}</p>
                    </div>
                  </el-collapse-item></el-collapse>
                </article>
              </div>
              <el-empty v-if="!detail.records.length" description="已找到实体，但没有可展示的修订记录。请查看相关审核条目；没有记录不代表没有医学风险。" />
              <el-button v-if="display === 'graph' && selectedRecord" @click="selectedRecord = ''">显示全部记录</el-button>
              <el-button v-if="!selectedRecord && recordLimit < detail.records.length" @click="recordLimit += 12">继续显示（尚余 {{ detail.records.length - recordLimit }} 条）</el-button>
            </template>
            <el-empty v-else description="选择实体，查看修订内容与证据" />
          </section>
        </div>
      </el-tab-pane>
      <el-tab-pane label="逐项审核与未解决问题" name="reviews">
        <form class="query-form" @submit.prevent="reviewPage = 1; loadReviews()"><el-input v-model="reviewQuery" aria-label="审核条目搜索" placeholder="搜索原条目名称或编号" maxlength="200" /><el-select v-model="reviewStatus" aria-label="审核状态" @change="reviewPage = 1; loadReviews()"><el-option v-for="option in statuses" :key="option.value" :label="option.label" :value="option.value" /></el-select><el-button native-type="submit" :loading="reviewBusy">筛选</el-button></form>
        <p class="small-note">审核通过表示已完成项目内部的数据与来源核对。退回、停用和依据不足项不纳入发布内容。</p>
        <div class="review-table" v-loading="reviewBusy"><button v-for="row in reviewRows" :key="row.item_id" @click="reviewSelected = row"><span class="review-badge">{{ row.project_review.label }}</span><strong>{{ row.summary }}</strong><span>查看记录与审核操作 →</span></button></div>
        <el-empty v-if="!reviewBusy && !reviewRows.length" description="没有匹配的审核条目" />
        <el-pagination :current-page="reviewPage" :page-size="20" :total="reviewTotal" layout="total, prev, pager, next" @current-change="pageChanged" />
      </el-tab-pane>
      <el-tab-pane label="版本发布与回退" name="versions">
        <div class="version-intro"><h3>知识工作区版本</h3><p>发布会保存审核通过的知识快照。启用后，知识浏览与新一轮问答同步使用该版本；正在进行的回答保持原版本。</p><p>当前启用：{{ activeVersionName }}</p><p>问答检索版本：{{ workflow?.chat_version || 'kg_v2' }}</p><el-input v-model="releaseNote" maxlength="1000" placeholder="填写版本说明" aria-label="版本说明" /><div class="review-actions"><el-button type="primary" :loading="mutating" :disabled="role !== 'admin' || !workflow || !releaseNote.trim()" @click="publish">校验并发布</el-button><el-button :loading="mutating" :disabled="role !== 'admin' || !workflow?.active" @click="rollback">回退上次启用</el-button></div></div>
        <article v-for="release in workflow?.releases" :key="release.id" class="version-card"><div><strong>{{ release.name }}</strong><el-tag :type="workflow?.active === release.id ? 'success' : 'info'">{{ workflow?.active === release.id ? '已启用' : '已发布' }}</el-tag></div><p>{{ release.note }}</p><p>{{ release.entity_count }} 个实体 · {{ release.record_count }} 条知识记录 · {{ dateLabel(release.created_at) }}</p><p class="small-note">{{ release.id }} · 操作人 {{ release.actor }}</p><el-button :disabled="role !== 'admin' || workflow?.active === release.id || release.source_sha256 !== workflow?.working_sha256" :loading="mutating" @click="activate(release.id)">启用版本</el-button></article>
        <el-empty v-if="!workflow?.releases.length" description="尚未发布版本，填写说明后可生成首个版本" />
        <h3>操作记录</h3><div v-for="(event, i) in workflow?.events" :key="i" class="event-row"><strong>{{ actionLabel(event.action) }}</strong><span>{{ event.actor }} · {{ dateLabel(event.at) }}</span><small>{{ event.target || '工作版本' }}</small></div>
      </el-tab-pane>
    </el-tabs>
    <el-drawer :model-value="Boolean(reviewSelected)" title="条目详情与审核操作" size="min(680px, 95vw)" @close="reviewSelected = null">
      <template v-if="reviewSelected"><el-alert v-if="error" :title="error" type="error" show-icon :closable="false" /><h3>{{ reviewSelected.summary }}</h3><el-tag type="warning">{{ reviewSelected.project_review.label }}</el-tag><p>{{ reviewSelected.reason }}</p><p>{{ reviewSelected.project_review.note }}</p><el-input v-model="reviewNote" type="textarea" :rows="2" maxlength="1000" placeholder="填写审核意见" aria-label="审核意见" /><div class="review-actions"><el-button type="primary" :loading="mutating" :disabled="role === 'reader' || !reviewSelected.project_review.eligible || !reviewNote.trim()" @click="decide('approved')">审核通过</el-button><el-button :loading="mutating" :disabled="role === 'reader' || !reviewNote.trim()" @click="decide('returned')">退回修改</el-button><el-button type="danger" plain :loading="mutating" :disabled="role === 'reader' || !reviewNote.trim()" @click="decide('disabled')">停用</el-button></div><h4>核对要点</h4><ul><li v-for="question in reviewSelected.questions" :key="question">{{ question }}</li></ul><h4>原值（仅供追溯）</h4><pre class="review-json">{{ format(reviewSelected.original) }}</pre><h4>修订处置</h4><pre class="review-json">{{ format(reviewSelected.candidate_change || '原条目尚无通过审核的替代记录') }}</pre><h4>本轮补查结果</h4><pre class="review-json">{{ format(reviewSelected.supplemental_review || '本项见原文依据与候选处置') }}</pre><template v-if="reviewSelected.prior_supplement"><h4>此前补查及限制</h4><pre class="review-json">{{ format(reviewSelected.prior_supplement) }}</pre></template><div v-for="source in reviewSelected.additional_sources" :key="source.id" class="proof"><a v-if="safeUrl(source.url)" :href="safeUrl(source.url)" target="_blank" rel="noopener noreferrer">{{ source.title }}</a><p>{{ source.scope }}</p></div><h4>原文依据</h4><pre class="review-json">{{ format(reviewSelected.evidence) }}</pre></template>
    </el-drawer>
  </main>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { candidateApi, type CandidateDetail, type CandidateEntity, type WorkbenchStatus, type ReviewRow } from '@/api/candidateGraph'
import type { Entity, Relation } from '@/types/knowledgeGraph'
import GraphCanvas from './GraphCanvas.vue'
const props = defineProps<{ active: boolean; userId: string; role: string }>()
const workflow = ref<WorkbenchStatus>(), error = ref(''), query = ref(''), busy = ref(false), loadingDetail = ref(false), downloading = ref(false)
const statsBusy = ref(false), mutating = ref(false), releaseNote = ref('知识资料整理与来源核对完成'), reviewNote = ref(''), knowledgeView = ref('working')
const tab = ref('knowledge'), display = ref('cards'), results = ref<CandidateEntity[]>([]), detail = ref<CandidateDetail>(), searched = ref(false), searchMessage = ref(''), recordLimit = ref(12), selectedRecord = ref('')
const reviewQuery = ref(''), reviewStatus = ref('all'), reviewPage = ref(1), reviewRows = ref<ReviewRow[]>([]), reviewTotal = ref(0), reviewBusy = ref(false), reviewSelected = ref<ReviewRow | null>(null)
const examples = ['抑郁症', '双相情感障碍', '失眠', '帕罗西汀', '文拉法辛', '6A72']
const statuses = [{value:'all',label:'全部条目'},{value:'approved',label:'审核通过'},{value:'returned',label:'退回修改'},{value:'disabled',label:'已停用'},{value:'blocked',label:'依据不足 / 隔离'},{value:'amended',label:'原始分类：已修订'},{value:'source_supported',label:'原始分类：原文支持'},{value:'structural_only',label:'原始分类：结构一致'}]
let searchGeneration = 0, detailGeneration = 0, reviewGeneration = 0
function fail(e: unknown) { error.value = e instanceof Error ? e.message : '请求失败，请重试。' }
async function search() { const g = ++searchGeneration; ++detailGeneration; busy.value = true; detail.value = undefined; try { const r = await candidateApi.search(query.value.trim(), props.userId, knowledgeView.value); if (g !== searchGeneration) return; results.value = r.items; searched.value = true; searchMessage.value = r.total ? `找到 ${r.total} 个实体${r.truncated ? '，请细化搜索词' : ''}。` : '当前版本没有匹配实体；可在审核条目中查找撤销或历史记录。'; error.value = ''; if (r.items[0]) await focus(r.items[0]) } catch(e) { if(g === searchGeneration) fail(e) } finally { if(g === searchGeneration) busy.value = false } }
async function focus(entity: CandidateEntity) { const g = ++detailGeneration; loadingDetail.value = true; try { const d = await candidateApi.detail(entity.id, props.userId, knowledgeView.value); if (g !== detailGeneration) return; detail.value = d; recordLimit.value = 12; selectedRecord.value = ''; error.value = '' } catch(e) { if(g === detailGeneration) fail(e) } finally { if(g === detailGeneration) loadingDetail.value = false } }
function example(name: string) { query.value = name; void search() }
async function loadReviews() { const g = ++reviewGeneration; reviewBusy.value = true; try { const r = await candidateApi.reviews(reviewQuery.value, reviewStatus.value, reviewPage.value, props.userId); if(g !== reviewGeneration) return; reviewRows.value = r.items; reviewTotal.value = r.total; error.value = '' } catch(e) { if(g === reviewGeneration) fail(e) } finally { if(g === reviewGeneration) reviewBusy.value = false } }
function tabChanged() { if(tab.value === 'reviews') void loadReviews(); if(tab.value === 'versions') void refresh() }
function pageChanged(page: number) { reviewPage.value = page; void loadReviews() }
function openReviews() { reviewQuery.value = detail.value?.entity.name || ''; reviewStatus.value = 'all'; reviewPage.value = 1; tab.value = 'reviews'; void loadReviews() }
async function download() { downloading.value = true; try { const blob = await candidateApi.packet(props.userId); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'PsyConsult-项目审核记录.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) } catch(e) { fail(e) } finally { downloading.value = false } }
function format(value: unknown) { return typeof value === 'string' ? value : JSON.stringify(value, null, 2) }
function region(value: string) { const names: Record<string,string> = {CN:'中国具体产品',US:'美国具体产品',UK:'英国指南 / 产品',WHO:'WHO分类',study_specific:'特定研究'}; return names[value] || value }
function safeUrl(url: string) { try { return new URL(url).protocol === 'https:' ? url : '' } catch { return '' } }
function sourceLink(id: string) { return safeUrl(detail.value?.sources.find(s => s.id === id)?.url || '') }
function fieldLabel(key: string) { const names: Record<string,string> = {population:'适用人群',indication:'适应症',indications:'适应症',parameters:'数值与方向',constraints:'适用限制',phase:'治疗阶段',dose_profiles:'分人群 / 适应症用量资料',directions:'换药方向与间隔',allowed_indications:'标签中的适应症范围',scope_correction:'来源范围修正',prerequisites:'适用前提',prerequisite:'适用前提',symptoms_total_min:'症状总数门槛',affective_cluster_min:'情感簇要求',duration_weeks_min:'病程要求（周）',diagnostic_sufficiency:'是否足以独立诊断'}; return names[key] || key }
const selectedRecordIds = computed(() => {
  const selected = graphNodes.value.find(n => n.id === selectedRecord.value) || graphEdges.value.find(e => e.id === selectedRecord.value)
  const records = selected?.properties.records as {id:string}[] | undefined
  return records ? new Set(records.map(r => r.id)) : undefined
})
const visibleRecords = computed(() => {
  const records=detail.value?.records || []
  return display.value === 'graph' && selectedRecordIds.value ? records.filter(r => selectedRecordIds.value!.has(r.id)) : records.slice(0,recordLimit.value)
})
const graphNodes = computed<Entity[]>(() => detail.value?.browser_graph.nodes || [])
const graphEdges = computed<Relation[]>(() => detail.value?.browser_graph.edges || [])
function selectRecord(id: string) { selectedRecord.value = id }
async function refresh() { statsBusy.value = true; try { workflow.value = await candidateApi.status(props.userId); error.value = '' } catch(e) { fail(e) } finally { statsBusy.value = false } }
watch(reviewSelected, () => { reviewNote.value = '' })
const activeVersionName = computed(() => workflow.value?.releases.find(r => r.id === workflow.value?.active)?.name || '尚未启用发布版本')
function dateLabel(value: string) { return new Date(value).toLocaleString('zh-CN') }
function actionLabel(value: string) { const labels: Record<string,string> = {publish:'发布版本',activate:'启用版本',rollback:'回退版本',review_approved:'审核通过',review_returned:'退回修改',review_disabled:'停用条目'}; return labels[value] || value }
async function mutate(action: string, extra: Record<string, unknown>) { if (!workflow.value || mutating.value) return false; mutating.value = true; try { workflow.value = await candidateApi.change(action, {revision:workflow.value.revision,...extra}, props.userId); error.value = ''; return true } catch(e) { fail(e); await refreshAfterConflict(); return false } finally { mutating.value = false } }
async function refreshAfterConflict() { try { workflow.value = await candidateApi.status(props.userId) } catch { /* Keep the action error visible. */ } }
async function decide(status: string) { if (!reviewSelected.value) return; if(await mutate('review', {item_id:reviewSelected.value.item_id,status,note:reviewNote.value.trim()})) { reviewSelected.value = null; await loadReviews() } }
async function publish() { await mutate('publish', {note:releaseNote.value.trim()}) }
async function activate(id: string) { if(await mutate('activate', {release_id:id})) { knowledgeView.value = 'active'; results.value = []; detail.value = undefined; searched.value = false } }
async function rollback() { if(await mutate('rollback', {})) { knowledgeView.value = workflow.value?.active ? 'active' : 'working'; results.value = []; detail.value = undefined; searched.value = false } }
function viewChanged() { ++searchGeneration; ++detailGeneration; busy.value = false; loadingDetail.value = false; results.value = []; detail.value = undefined; searched.value = false; if(query.value.trim()) void search() }
onMounted(refresh)
</script>
<style scoped>
.candidate-panel{grid-column:2/-1;background:oklch(98% .007 200);padding:30px;min-width:0;color:#294853}.preview-header{display:flex;justify-content:space-between;align-items:center;gap:20px}.eyebrow{font-size:11px;color:#77969b;letter-spacing:1px}h2{font-size:25px;margin:8px 0}h2 span{font-size:12px;color:#668a89;border:1px solid #cce0dc;border-radius:6px;padding:3px 8px;vertical-align:middle}.subtitle{font-size:13px;color:#769096}.boundary{margin:20px 0;background:#fff7e7;border:1px solid #f0dfbc;border-radius:10px;padding:13px 16px;display:flex;gap:16px;font-size:12px;line-height:1.8;color:#816335}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}.metrics>div{background:white;border:1px solid #dfebea;border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:6px}.metrics strong{font-size:26px;font-weight:500}.metrics span{font-size:11px;color:#82979c}.query-form{display:flex;gap:10px;max-width:840px;margin:12px 0}.query-form .el-select{width:210px;flex-shrink:0}.examples{display:flex;gap:8px;flex-wrap:wrap;align-items:center;color:#85999c;font-size:11px;margin-bottom:16px}.examples button{border:1px solid #d9e7e5;border-radius:20px;padding:5px 12px;color:#507b77;background:white;cursor:pointer}.knowledge-layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:22px}.entity-list{border-right:1px solid #e0e9e8;padding-right:16px}.entity-list button{display:flex;flex-direction:column;gap:7px;text-align:left;width:100%;background:white;border:1px solid #dfe9e7;padding:14px;border-radius:10px;margin-bottom:9px;cursor:pointer;color:#365861}.entity-list button.selected{background:#eaf4f0;border-color:#71a89a}.entity-list span,.entity-list p{font-size:11px;color:#8a9c9b}.entity-list strong{font-size:13px;font-weight:500}.knowledge-body{min-width:0}.entity-heading{display:flex;justify-content:space-between;gap:10px;align-items:center}.entity-heading h3{font-size:20px;margin:8px 0}.entity-heading p,.search-result{font-size:12px;color:#819599}.open-note{font-size:12px;line-height:1.8;background:#f7f0e7;color:#8b7357;padding:10px;border-radius:8px}.record-cards article{background:white;border:1px solid #deebe7;border-radius:12px;padding:19px;margin:14px 0}.record-cards article.highlighted{border-color:#4e9a89;box-shadow:0 0 0 2px #cde9df}.record-label{display:flex;justify-content:space-between;gap:10px;font-size:10px;color:#a0824f}.record-label span:first-child{background:#fff4df;padding:3px 7px;border-radius:4px}h4{font-size:14px;line-height:1.8;font-weight:500}.conditions{font-size:12px;line-height:1.8;color:#819293}.conditions-list{display:grid;grid-template-columns:180px minmax(0,1fr);font-size:12px}.conditions-list dt,.conditions-list dd{padding:7px;border-bottom:1px solid #e8eeee;margin:0}.conditions-list dt{color:#829492;word-break:break-word}pre{white-space:pre-wrap;word-break:break-word;font-size:11px;font-family:inherit;line-height:1.7;margin:0}.proof{font-size:12px;border-top:1px solid #e6efed;padding-top:12px;margin-top:12px}.proof a{color:#338878}.proof p,.small-note{font-size:11px;line-height:1.8;color:#819594}.review-table{margin:16px 0}.review-table button{width:100%;display:grid;grid-template-columns:150px 1fr 170px;align-items:center;gap:15px;text-align:left;background:white;border:0;border-bottom:1px solid #e1eae7;padding:16px;cursor:pointer;color:#4a686e}.review-table strong{font-size:12px;font-weight:500}.review-table button>span:last-child{font-size:11px;color:#93a5a5}.review-badge{font-size:11px;color:#967c4d}.review-json{padding:12px;background:#f6f9f8;border:1px solid #e1ebe7;border-radius:8px;max-height:350px;overflow:auto}.candidate-panel :deep(.el-tabs__item){font-size:13px}.candidate-panel :deep(.graph-view){margin-top:15px}.candidate-panel :deep(.el-drawer__body){font-size:13px;line-height:1.8}
.record-subject{font-size:12px;color:#4d8177;margin:14px 0 0;line-height:1.8}
@media(max-width:1000px){.candidate-panel{padding:18px}.knowledge-layout{grid-template-columns:175px minmax(0,1fr)}.review-table button{grid-template-columns:110px 1fr}.review-table button>span:last-child{display:none}.conditions-list{grid-template-columns:1fr}}
@media(max-width:700px){.candidate-panel{grid-column:1/-1}.metrics{grid-template-columns:repeat(2,1fr)}.knowledge-layout{grid-template-columns:1fr}.entity-list{border:0;padding:0;display:flex;gap:8px;overflow:auto}.entity-list button{min-width:150px}.preview-header,.boundary{flex-direction:column;align-items:flex-start}.query-form{flex-wrap:wrap}.query-form .el-input{min-width:180px}.query-form .el-select{width:190px}}
</style>

<style scoped>
.review-actions{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.version-intro{max-width:850px;line-height:1.8;font-size:13px}.version-card{background:white;border:1px solid #deebe7;border-radius:12px;padding:20px;margin:15px 0;font-size:13px}.version-card>div{display:flex;gap:15px;align-items:center}.event-row{display:flex;gap:12px;flex-wrap:wrap;border-bottom:1px solid #deebe7;padding:12px 0;font-size:12px}.event-row small{overflow-wrap:anywhere;color:#78908e}.header-actions{display:flex;gap:8px;flex-wrap:wrap}
</style>
