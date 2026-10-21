<template>
  <main class="kg-panel" v-loading="busy">
    <header class="page-header">
      <div><div class="eyebrow"><span class="eyebrow-line"></span> KNOWLEDGE EXPLORER <span class="version">{{ stats?.version || '知识图谱' }}</span></div><h2>探索临床知识之间的联系</h2><p class="subtitle">从疾病、症状与药物出发，浏览关联与知识来源。</p></div>
      <div class="header-actions"><div class="stat"><strong>{{ stats?.entities ?? '—' }}</strong><span>知识实体</span></div><div class="stat"><strong>{{ stats?.knowledge_records ?? stats?.source_checked_relations ?? stats?.relations ?? '—' }}</strong><span>{{ stats?.knowledge_records !== undefined ? '知识记录' : stats?.version==='kg_v2' ? '原文已核对' : '关系记录' }}</span></div><button class="refresh" aria-label="刷新图谱状态" @click="loadStats"><el-icon><RefreshRight /></el-icon></button></div>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <section class="search-card" aria-label="知识搜索">
      <div class="search-bar">
        <div class="name-search"><label for="kg-entity-search">实体名称</label><el-input id="kg-entity-search" v-model="query" placeholder="输入药名、疾病或症状，如：帕罗西汀" :prefix-icon="Search" maxlength="200" clearable @keyup.enter="search" /></div>
        <el-button type="primary" @click="search">搜索并展开 <el-icon class="search-arrow"><Right /></el-icon></el-button>
        <span class="search-divider"></span>
        <div class="relation-filter"><label for="kg-relation-filter">关系类型筛选（可选）</label><el-select id="kg-relation-filter" v-model="relationType" placeholder="全部关系类型" aria-label="关系类型筛选" no-match-text="没有匹配的关系类型，药名请在实体名称中输入" clearable filterable @change="refilter"><el-option v-for="type in stats?.relation_types || []" :key="type" :label="relationLabel(type)" :value="type" /></el-select></div>
      </div>
      <p class="search-help">药名请在“实体名称”中输入；右侧筛选仅用于选择“相互作用”“合用禁忌”等关系类型。搜索后自动展开唯一结果，多个结果时请选择候选。</p>
      <div v-if="searched" class="results"><span class="result-label">{{ results.length ? '匹配实体' : '搜索结果' }}</span><div class="result-chips"><button v-for="item in results" :key="item.id" :class="{chosen:root===item.id}" @click="focus(item.id)"><i></i>{{ item.name }}<small>{{ entityLabel(item.label) }}</small><span v-if="root===item.id" class="chip-check">✓</span></button><span v-if="!results.length" class="no-result">当前图谱未收录匹配实体。</span></div><span v-if="results.length" class="result-count">{{ results.length }} 个候选</span></div>
      <p v-if="resultText.includes('细化')" class="result-hint">{{ resultText }}</p>
    </section>
    <div v-if="stats?.version==='kg_v2'" class="coverage-note"><span>中国说明书 {{ stats.cn_records }} 条 · 美国标签补充 {{ stats.us_supplement_records }} 条</span><el-checkbox v-model="includeUnreviewed" @change="refilter">显示旧版未核实关系</el-checkbox></div>
    <div class="workspace-heading"><div><h3>{{ centerName || '知识关系工作区' }}</h3><span v-if="root" class="center-caption">当前中心实体</span></div><span class="evidence-status"><i></i>{{ stats?.version.startsWith('project-') ? '已发布知识 · 保留适用条件' : stats?.version==='kg_v2' ? (includeUnreviewed ? '含旧版未核实关系 · 请查看逐条来源' : '仅显示原文已核对关系') : '仓库来源可追溯 · 医学原文待核实' }}</span></div>
    <p v-if="message && !message.startsWith('点击节点')" class="message" aria-live="polite">{{ message }}</p>
    <div class="graph-grid"><GraphCanvas :nodes="nodes" :edges="edges" :active="active" :center-id="root" :selected-id="selectedEntity?.id || ''" :selected-edge-id="selectedRelation?.id || ''" @select-node="selectNode" @select-edge="selectEdge" @expand="expand" /><EntityDetail :entity="selectedEntity" :relation="selectedRelation" :sources="selectedSources" :endpoints="endpoints" @expand="expand" /></div>
    <div class="supporting-panels"><details class="audit"><summary><span>当前关系列表 <b>{{ edges.length }}</b></span><span class="summary-hint">查看全部关联</span></summary><button class="relation-row" v-for="edge in edges" :key="edge.id" @click="selectEdge(edge.id)"><span>{{ nodeName(edge.source) }}</span><small>{{ relationLabel(edge.type) }} →</small><span>{{ nodeName(edge.target) }}</span></button></details>
    <details class="audit"><summary><span>待审核数据 <b>{{ stats?.pending?.length || 0 }}</b></span><span class="summary-hint">数据质量记录</span></summary><p class="audit-note">这些记录尚未作为有效关系导入，保留待审核。</p><article v-for="(item, i) in stats?.pending || []" :key="i"><strong>{{ item.source_id || item.kind }}</strong><p>{{ item.reason }}</p><pre>{{ JSON.stringify(item.original, null, 2) }}</pre></article></details></div>
    <details v-if="stats?.review?.length" class="audit"><summary>旧版关系复核清单（{{ stats.review.length }} 条）</summary><article v-for="r in stats.review" :key="r.edge_id"><strong>{{ r.source }} → {{ r.target }}</strong><p>{{ r.reason }}</p></article></details>
    <p class="page-footnote">图谱展示仓库已收录的知识。未查询到关联，不代表不存在相关风险。</p>
  </main>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { graphApi } from '@/api/knowledgeGraph'
import type { Entity, Relation, Source, Stats } from '@/types/knowledgeGraph'
import GraphCanvas from './GraphCanvas.vue'
import { Search, Right, RefreshRight } from '@element-plus/icons-vue'
import { entityLabel, relationLabel } from './labels'
import EntityDetail from './EntityDetail.vue'
const props=defineProps<{userId: string; active: boolean}>()
const stats=ref<Stats | null>(null), query=ref('舍曲林'), relationType=ref(''), error=ref(''), message=ref('')
const includeUnreviewed=ref(false)
const busy=ref(false), searched=ref(false), results=ref<Entity[]>([]), resultText=ref('')
const nodes=ref<Entity[]>([]), edges=ref<Relation[]>([]), sourceIndex=new Map<string,Source>()
const selectedEntity=ref<Entity | null>(null), selectedRelation=ref<Relation | null>(null), selectedSources=ref<Source[]>([]), root=ref('')
let generation=0, detailGeneration=0
const centerName = computed(() => nodes.value.find(n => n.id === root.value)?.name || '')
const endpoints=computed(() => selectedRelation.value ? `${nodes.value.find(n=>n.id===selectedRelation.value?.source)?.name} → ${nodes.value.find(n=>n.id===selectedRelation.value?.target)?.name}` : '')
function nodeName(id: string) { return nodes.value.find(n=>n.id===id)?.name || id }
function fail(e: unknown) { error.value=e instanceof Error ? e.message : '请求失败，请重试。' }
async function loadStats() { try { const latest=await graphApi.stats(props.userId); if(stats.value && stats.value.version!==latest.version) { ++generation; ++detailGeneration; nodes.value=[]; edges.value=[]; results.value=[]; sourceIndex.clear(); root.value=''; selectedEntity.value=null; selectedRelation.value=null; selectedSources.value=[]; relationType.value=''; searched.value=false; message.value='' } stats.value=latest; error.value='' } catch(e) { fail(e) } }
async function search() { const g=++generation; busy.value=true; try { const r=await graphApi.search(query.value.trim(),props.userId); if(g!==generation)return; results.value=r.items; searched.value=true; resultText.value=r.total ? `找到 ${r.total} 个候选实体${r.truncated ? '，请细化名称查看其余结果' : ''}；请选择实体。` : '当前图谱未收录匹配实体。'; error.value=''; if(r.items.length===1 && r.items[0]) await focus(r.items[0].id) } catch(e) { if(g===generation)fail(e) } finally { if(g===generation)busy.value=false } }
async function selectNode(id: string) { const g=++detailGeneration; try { const d=await graphApi.detail(id,props.userId); if(g!==detailGeneration)return; selectedEntity.value=d.entity; selectedRelation.value=null; selectedSources.value=d.sources; error.value='' } catch(e) { if(g===detailGeneration)fail(e) } }
function selectEdge(id: string) { ++detailGeneration; selectedEntity.value=null; selectedRelation.value=edges.value.find(e=>e.id===id)||null; selectedSources.value=(selectedRelation.value?.source_ids||[]).map(s=>sourceIndex.get(s)).filter((s):s is Source=>!!s) }
async function graph(id: string, replace: boolean) {
  const g=++generation; busy.value=true
  try { const r=await graphApi.neighbors(id,relationType.value,props.userId,includeUnreviewed.value); if(g!==generation)return
    if(stats.value && r.version!==stats.value.version) { replace=true; await loadStats() }
    if(replace) { sourceIndex.clear(); root.value=id }
    r.sources.forEach(s=>sourceIndex.set(s.id,s))
    const allNodes=[...new Map([...(replace?[]:nodes.value),...r.nodes].map(n=>[n.id,n])).values()]
    const allEdges=[...new Map([...(replace?[]:edges.value),...r.edges].map(e=>[e.id,e])).values()]
    nodes.value=allNodes.slice(0,150); const visible=new Set(nodes.value.map(n=>n.id)); edges.value=allEdges.filter(e=>visible.has(e.source)&&visible.has(e.target)).slice(0,300)
    message.value=r.message || '点击节点查看详情，双击节点展开；点击连线查看关系证据。'
    if(r.version==='kg_v2' && !includeUnreviewed.value && r.total===0) {
      const name=r.nodes.find(n=>n.id===id)?.name || '该实体'
      message.value=`已找到“${name}”，但当前筛选下没有原文已核对的关联。可勾选“显示旧版未核实关系”查看已收录的旧关系；这不表示不存在相关医学知识。`
    }
    if(r.truncated || allNodes.length>150 || allEdges.length>300) message.value+=' 已限制展示数量，请筛选关系或更换中心实体。'
    error.value=''; await selectNode(id)
  } catch(e) { if(g===generation)fail(e) } finally { if(g===generation)busy.value=false }
}
function focus(id: string) { return graph(id,true) }
function expand(id: string) { return graph(id,false) }
function refilter() { if(root.value) return graph(root.value,true) }
watch(() => props.active, active => { if(active) void loadStats() })
onMounted(loadStats)
</script>
<style scoped>
.name-search,.relation-filter{min-width:0}.name-search label,.relation-filter label{display:block;margin-bottom:7px;font-size:11px;color:#607b88;font-weight:500}.search-bar>.el-button,.search-divider{align-self:end}.relation-filter .el-select{width:100%}.search-help{font-size:11px;color:#8498a2;line-height:1.8;margin:12px 0 0}

.coverage-note{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:16px;padding:10px 14px;border-radius:9px;background:#e9f2ef;color:#568276;font-size:11px}
.kg-panel{grid-column:2 / -1;min-width:0;padding:32px 30px 24px;color:#2c4755;background:linear-gradient(180deg,#f6f9fa 0%,#f1f6f7 100%);font-family:'Microsoft YaHei',sans-serif}.page-header{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:25px}.eyebrow{display:flex;align-items:center;gap:9px;font-size:10px;letter-spacing:1.6px;color:#80939c;font-weight:600}.eyebrow-line{width:18px;height:2px;background:#388e8b}.version{font-size:10px;letter-spacing:.2px;background:#e8f1f0;border:1px solid #d5e5e2;color:#53857f;padding:3px 7px;border-radius:5px}.page-header h2{font-size:25px;font-weight:600;letter-spacing:.5px;margin:12px 0 9px;color:#243e4b}.subtitle{font-size:12px;color:#87969f;margin:0;line-height:1.7}.header-actions{display:flex;align-items:center;gap:26px}.stat{display:flex;flex-direction:column;gap:6px;white-space:nowrap}.stat strong{font-size:24px;line-height:1;font-weight:500;font-variant-numeric:tabular-nums;color:#355866}.stat span{font-size:10px;color:#8b9ba4}.refresh{display:grid;place-items:center;width:33px;height:33px;border:1px solid #dfe7eb;border-radius:9px;background:white;color:#79919c;cursor:pointer}.refresh:hover{background:#eaf4f3;color:#247d7c}.search-card{border:1px solid #e0e8ec;background:white;border-radius:14px;padding:16px 18px;box-shadow:0 3px 12px #2e566908}.search-bar{display:grid;grid-template-columns:minmax(170px,1fr) auto 1px minmax(170px,230px);align-items:center;gap:12px}.search-divider{height:24px;background:#e7edf0;margin:0 2px}.search-bar :deep(.el-input__wrapper){box-shadow:none;background:#f4f7f9;border:1px solid #eaf0f2;border-radius:8px;padding:3px 12px}.search-bar :deep(.el-input__inner){font-size:12px;height:32px}.search-bar :deep(.el-button--primary){height:40px;border-radius:8px;background:#206f76;border-color:#206f76;font-size:12px;padding:0 17px}.search-bar :deep(.el-select__wrapper){box-shadow:none;min-height:40px;background:#fff;border:1px solid #e7edf0;border-radius:8px;font-size:12px}.search-arrow{margin-left:10px}.results{display:flex;align-items:center;gap:12px;border-top:1px solid #f0f3f5;margin-top:14px;padding-top:13px}.result-label,.result-count{color:#98a5ad;font-size:10px;flex-shrink:0}.result-count{margin-left:auto}.result-chips{display:flex;flex-wrap:wrap;gap:8px}.result-chips button{display:flex;align-items:center;gap:8px;background:#fff;border:1px solid #e0e8eb;color:#49616e;padding:7px 11px;font-size:12px;border-radius:7px;cursor:pointer}.result-chips button.chosen{background:#edf6f4;border-color:#b7d8d1;color:#286c65}.result-chips i{height:5px;width:5px;background:#81b5aa;border-radius:50%}.result-chips small{font-size:10px;color:#8a9c9e;border-left:1px solid #d5e4e0;padding-left:8px}.chip-check{font-size:11px;color:#388a7c}.no-result,.result-hint{font-size:12px;color:#7c919b}.workspace-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:26px 0 13px}.workspace-heading>div{display:flex;align-items:center;gap:12px}.workspace-heading h3{margin:0;font-size:14px;font-weight:600;letter-spacing:.5px}.center-caption{font-size:10px;color:#8d9ea8;border-left:1px solid #d6e0e5;padding-left:12px}.evidence-status{font-size:10px;color:#8c9698;display:flex;align-items:center;gap:6px}.evidence-status i{width:5px;height:5px;border-radius:50%;background:#cfb580}.message{font-size:12px;line-height:1.6;color:#718690;margin-top:0}.graph-grid{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:16px;align-items:stretch}.supporting-panels{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;align-items:start}.audit{border:1px solid #e0e8ec;border-radius:11px;background:#ffffffb8;overflow:hidden}.audit summary{padding:14px 16px;font-size:12px;color:#526c79;cursor:pointer;display:flex;align-items:center;justify-content:space-between;list-style:none;gap:12px}.audit summary::after{content:'⌄';font-size:13px;color:#8c9ca4}.audit[open] summary::after{transform:rotate(180deg)}.audit summary>span:first-child{display:flex;align-items:center;gap:8px}.audit b{font-size:10px;font-weight:500;background:#edf2f4;border-radius:4px;padding:2px 6px;color:#82959d}.summary-hint{margin-left:auto;font-size:10px;color:#a0adb4}.relation-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;width:100%;text-align:left;border:0;border-top:1px solid #eef2f4;background:white;padding:11px 16px;cursor:pointer;color:#4a6471;font-size:11px}.relation-row:hover{background:#f0f7f6}.relation-row small{color:#91a3ab;font-size:10px}.audit article{border-top:1px solid #e6edf0;padding:14px;font-size:11px;overflow-wrap:anywhere}.audit pre{white-space:pre-wrap;font-size:11px}.audit-note{font-size:11px;color:#8b989e;padding:0 16px;line-height:1.7}.page-footnote{font-size:10px;color:#98a7ae;margin:17px 0 0}.el-alert{margin-bottom:15px}
@media(max-width:1250px){.graph-grid{grid-template-columns:minmax(0,1fr) 250px}.kg-panel{padding:26px 22px}.header-actions{gap:18px}.page-header h2{font-size:22px}.evidence-status{font-size:9px}}
@media(max-width:1050px){.graph-grid{grid-template-columns:minmax(0,1fr)}.header-actions{gap:15px}.stat strong{font-size:20px}.page-header h2{font-size:20px}.search-bar{grid-template-columns:minmax(160px,1fr) auto}.search-divider{display:none}.search-bar .relation-filter{grid-column:1 / -1}.supporting-panels{grid-template-columns:1fr}.summary-hint{display:none}}
@media(max-width:820px){.kg-panel{grid-column:1 / -1;padding:22px 16px}.page-header{align-items:start}.header-actions .stat{display:none}.page-header h2{font-size:20px}.workspace-heading{flex-wrap:wrap;gap:8px}.results{flex-wrap:wrap}.result-count{display:none}.evidence-status{font-size:10px}.search-card{padding:13px}.result-chips button{padding:7px 9px}}
</style>
