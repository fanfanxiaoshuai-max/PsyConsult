<template>
  <section class="graph-view" aria-label="实体关系图">
    <header class="canvas-header"><div><span class="live-dot"></span><strong>关系网络</strong><span class="count">{{ visualGraph.nodes.length }} 个实体 · {{ visualGraph.edges.length }} 条联系</span></div><span class="interaction-hint">单击查看详情 · 双击展开</span></header>
    <div ref="container" class="canvas"></div>
    <div v-if="!nodes.length" class="empty"><div class="empty-symbol">⌘</div><h3>从一个实体开始探索</h3><p>搜索疾病、症状或药物，查看它们之间的联系。</p></div>
    <footer class="canvas-footer"><div class="legend"><span><i class="drug"></i>药物</span><span><i class="disease"></i>疾病 / 诊断</span><span><i class="treatment"></i>治疗</span><span><i class="symptom"></i>症状 / 其他</span></div><div class="canvas-controls"><button aria-label="缩小图谱" @click="zoomBy(0.85)">−</button><button class="fit" @click="fit">回到中心</button><button aria-label="放大图谱" @click="zoomBy(1.15)">+</button></div></footer>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import cytoscape from 'cytoscape'
import type { Core } from 'cytoscape'
import type { Entity, Relation } from '@/types/knowledgeGraph'
import { relationLabel } from './labels'
const props = defineProps<{nodes: Entity[]; edges: Relation[]; active: boolean; centerId: string; selectedId: string; selectedEdgeId: string}>()
const emit = defineEmits<{selectNode: [id: string]; selectEdge: [id: string]; expand: [id: string]}>()
const container = ref<HTMLElement | null>(null)
let cy: Core | undefined
let resizeObserver: ResizeObserver | undefined
const visualGraph = computed(() => ({nodes: props.nodes, edges: props.edges}))
function fit() {
  if (!cy || !container.value?.clientWidth) return
  cy.resize(); cy.fit(undefined, 65)
  if (cy.zoom() > 1) cy.zoom(1)
  cy.center()
}
function zoomBy(factor: number) { if (cy) cy.zoom({level: Math.min(1.8, Math.max(0.2, cy.zoom() * factor)), renderedPosition: {x:cy.width()/2,y:cy.height()/2}}) }
function syncSelection() { if (!cy) return; cy.elements().unselect(); const selected=props.selectedId || props.selectedEdgeId; if(selected) cy.getElementById(selected).select() }
function category(node: Entity) {
  const kind = node.label
  if (['Drug', 'DrugClass', 'DrugFormulation', 'DoseRange', 'MaxDose', 'TherapeuticRange'].includes(String(kind))) return 'drug'
  if (['Disease', 'DiagnosticGroup', 'DifferentialDiagnosis', 'DifferentialConsideration', 'Episode', 'Criterion', 'ClinicalSubtype', 'Subtype', 'Severity'].includes(String(kind))) return 'disease'
  if (['Treatment', 'TreatmentStrategy', 'TreatmentModality', 'Psychotherapy', 'NeuromodulationTherapy', 'TreatmentGoal', 'TreatmentDuration', 'MaintenanceTherapyDuration'].includes(String(kind))) return 'treatment'
  return 'symptom'
}
function draw() {
  if (!cy) return
  const {nodes, edges} = visualGraph.value
  const visible = new Set(nodes.map(n => n.id))
  cy.elements().remove()
  cy.add([...nodes.map(n => ({data: {id: n.id, label: n.name.length > 14 ? n.name.slice(0,13) + '…' : n.name, category: category(n), root: n.id === props.centerId ? 1 : 0}})), ...edges.filter(e => visible.has(e.source) && visible.has(e.target)).map(e => ({data: {...e, label: relationLabel(e.type)}}))])
  const others=nodes.filter(n=>n.id!==props.centerId).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'))
  const positions: Record<string, {x:number;y:number}> = {[props.centerId]:{x:0,y:0}}
  let offset=0, ring=1
  while(offset<others.length) {
    const count=Math.min(ring*8,others.length-offset)
    for(let i=0;i<count;i++) {
      const n=others[offset+i]!
      const angle=-Math.PI/2+i*Math.PI*2/count
      positions[n.id]={x:Math.cos(angle)*(205+(ring-1)*150),y:Math.sin(angle)*(145+(ring-1)*115)}
    }
    offset+=count;ring++
  }
  cy.layout({name:'preset',positions,fit:false}).run()
  syncSelection(); fit()
}
onMounted(() => {
  cy=cytoscape({container:container.value!, minZoom:0.15, maxZoom:1.8, wheelSensitivity:0.18, style:[
    {selector:'node',style:{shape:'round-rectangle',width:112,height:42,'background-color':'#f0f7f7','border-color':'#bed6d5','border-width':1,label:'data(label)',color:'#315a60','font-family':'Microsoft YaHei, sans-serif','font-size':12,'font-weight':500,'text-valign':'center','text-halign':'center','text-wrap':'wrap','text-max-width':'100px','overlay-opacity':0}},
    {selector:'node[category = "drug"]',style:{'background-color':'#fdf4e9','border-color':'#e6cba9',color:'#8a5e32'}},
    {selector:'node[category = "disease"]',style:{'background-color':'#f0eefb','border-color':'#cfc7ea',color:'#6b5a91'}},
    {selector:'node[category = "treatment"]',style:{'background-color':'#edf4fc','border-color':'#bcd3e9',color:'#416c91'}},
    {selector:'node[root = 1]',style:{width:130,height:48,'background-color':'#176d73','border-color':'#176d73',color:'#ffffff','font-size':14,'font-weight':600}},
    {selector:'node:selected',style:{'border-width':2,'border-color':'#208b91','underlay-color':'#208b91','underlay-opacity':0.07,'underlay-padding':6}},
    {selector:'edge',style:{'curve-style':'bezier','target-arrow-shape':'triangle','arrow-scale':0.7,'target-arrow-color':'#c1d0d6','line-color':'#c1d0d6',width:1.2,label:'','font-size':11,'text-rotation':'autorotate','text-background-color':'#ffffff','text-background-opacity':1,'text-background-padding':'5px','text-border-opacity':0,color:'#50727b','overlay-opacity':0}},
    {selector:'edge[type = "HAS_QUALIFIED_ASSERTION"]',style:{'target-arrow-shape':'none'}},
    {selector:'edge:selected',style:{label:'data(label)','line-color':'#35858a','target-arrow-color':'#35858a',width:2}},
    {selector:'node.hover',style:{'border-width':2,'border-color':'#5b999c'}},
  ]})
  cy.on('tap','node',e=>emit('selectNode',e.target.id()))
  cy.on('dbltap','node',e=>emit('expand',e.target.id()))
  cy.on('tap','edge',e=>emit('selectEdge',e.target.id()))
  cy.on('mouseover','node',e=>{e.target.addClass('hover');if(container.value)container.value.style.cursor='pointer'})
  cy.on('mouseout','node',e=>{e.target.removeClass('hover');if(container.value)container.value.style.cursor='default'})
  resizeObserver=new ResizeObserver(()=>{if(props.active)requestAnimationFrame(fit)})
  resizeObserver.observe(container.value!)
  draw()
})
watch(visualGraph,draw)
watch(()=>props.centerId,draw)
watch(()=>[props.selectedId,props.selectedEdgeId],syncSelection)
watch(()=>props.active,active=>{if(active)requestAnimationFrame(fit)})
onBeforeUnmount(()=>{resizeObserver?.disconnect();cy?.destroy()})
</script>
<style scoped>
.graph-view{position:relative;min-width:0;background-color:#fcfdfd;background-image:radial-gradient(#dce6e8 .7px,transparent .7px);background-size:18px 18px;border:1px solid #e1e9ec;border-radius:16px;overflow:hidden;box-shadow:0 4px 20px #254d5910;display:flex;flex-direction:column}
.canvas-header{height:59px;flex-shrink:0;display:flex;align-items:center;justify-content:space-between;padding:0 20px;border-bottom:1px solid #e9eef0;background:#ffffffec;gap:12px}.canvas-header>div{display:flex;align-items:center;gap:9px}.canvas-header strong{font-size:13px;font-weight:600;color:#2d4855}.live-dot{width:6px;height:6px;border-radius:50%;background:#4a9b91}.count,.interaction-hint{font-size:11px;color:#8a9aa4}.count{margin-left:6px}.canvas{height:510px;min-height:360px;width:100%;flex:1}.canvas-footer{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;background:#ffffffd9;border-top:1px solid #edf1f3;gap:12px}.legend{display:flex;flex-wrap:wrap;gap:8px 14px;font-size:11px;color:#71848e}.legend span{display:flex;align-items:center;gap:6px;white-space:nowrap}.legend i{width:7px;height:7px;border-radius:2px}.drug{background:#d8b182}.disease{background:#a897cc}.treatment{background:#8db6da}.symptom{background:#78a9a5}.canvas-controls{display:flex;align-items:center;border:1px solid #dfe7eb;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 5px #294b5808;flex-shrink:0}.canvas-controls button{height:29px;min-width:30px;border:0;background:white;color:#526e7b;font-size:18px;cursor:pointer}.canvas-controls button:hover{background:#eef6f6}.canvas-controls .fit{font-size:11px;padding:0 10px;border-inline:1px solid #e8edef}.empty{position:absolute;inset:60px 0 60px;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}.empty-symbol{font-size:28px;color:#82aaa8;background:#edf5f4;border:1px solid #d9e9e7;border-radius:14px;width:58px;height:58px;display:grid;place-items:center}.empty h3{font-size:15px;font-weight:500;color:#526c77;margin:20px 0 8px}.empty p{font-size:12px;color:#8e9ea6;text-align:center;padding:0 16px}
@media(max-width:650px){.interaction-hint{display:none}.canvas-header{padding:0 14px}.canvas-header>div{flex-wrap:wrap;gap:6px}.count{margin-left:0}.canvas-footer{padding:12px;flex-wrap:wrap}.canvas{height:430px}.legend{gap:10px}}
</style>
