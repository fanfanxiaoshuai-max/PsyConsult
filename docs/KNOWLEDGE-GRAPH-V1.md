# 知识图谱第一轮增强

实施日期：2026-10-19（北京时间）。本轮增强现有仓库知识，不增加未经核实的诊疗规则。

## 使用

打开 http://127.0.0.1:5173，点击左侧“知识图谱”。输入中文名称、英文名或已有症状别名，选择候选实体；同名不同类型保留独立候选。点击节点查看详情，双击节点或使用“展开关联”按钮展开一跳关系。连线点击后显示关系来源；下方“当前关系列表”提供可用键盘操作的同等入口。关系类型筛选后重新以中心实体加载。

前端每次最多取60条关系，累计显示最多150个节点、300条关系；达到上限会提示筛选。节点颜色区分药物、疾病和其他实体。默认隐藏关系文字以减少遮挡，选择连线时展示关系类型。图谱视图切换使用 v-show，聊天会话不会因切换被销毁。

## 数据与证据

- 原始 `mock_data/*.json` 保持原样。
- `mock_data/kg_v1/entities.json`：214个实体，以标签和原ID共同生成稳定编号；同名不同类型分开。
- `relations.json`：376条有效关系，端点均为明确编号；原图谱423条关系中包含同名跨标签匹配扩展，不以关系数量增长为目标。
- `sources.json`：643条来源记录，定位到仓库文件及 JSON 指针，保留原始内容，包括已有症状别名记录。
- `aliases.json`：来自节点原有中英文名称及 `symptom_synonyms.json` 的可解析别名；不把原有编码当成已验证的医学标准。
- `resolutions.json`：记录按来源文件唯一类型消歧的决策，以及13条缺失端点的待审核关系。待审核关系未进入有效查询结果。

所有记录标为 `medical_source_unverified`：这是仓库级来源追溯，不是指南原文核验。没有编造指南版本、页码或证据等级。没有把“未收录”解释为“没有相互作用”或“可以安全合用”。无直接双药关系时仍返回这一限制。

## 实现位置

- `agent/core/graph/models.py`：保留旧实体模型，增加标准图谱类型。
- `normalizer.py`、`validator.py`：确定性转换与全量校验。
- `repository.py`：只读、参数化查询；连接池复用及关闭；读取前检查版本就绪状态。
- `retriever.py`：名称、英文名和别名匹配；候选排序、关系类别过滤、双药直接关系检索；在截断前筛选双药关系。
- `agent/tools/graph_tool.py`：增强版本默认走统一固定查询，返回来源位置和未核实提示。legacy默认也走统一的参数化查询；原有可选LLM查询仅保留在legacy路径，不参与增强版验收。
- `scripts/build_knowledge_graph.py`：构建后校验，事务内导入完整版本；内容摘要锁定，禁止用不同内容覆盖同一版本。
- `scripts/import_graph.py --dataset kg_v1`：兼容入口；原导入方式仍可用。
- `app/dependencies/auth.py`：抽取原有共享鉴权，聊天接口行为保持一致。
- `app/router/knowledge_graph.py`、`app/schemas/knowledge_graph.py`、`app/service/knowledge_graph_service.py`：只读API、边界校验和服务编排。
- `app/app_main.py`：注册路由，应用退出时关闭图谱连接池。
- 两套Settings新增 `KG_VERSION`；`app/infra/cache.py`按图谱版本选用独立Milvus缓存集合，精确和语义查询共同隔离。
- `front/clinical_cds/src/components/knowledge-graph/`：独立页面、Cytoscape画布和证据详情组件。
- `src/api/knowledgeGraph.ts`、`src/types/knowledgeGraph.ts`：前端请求与类型；`App.vue`提供视图切换和异步组件加载。

所有新增读取API需要与聊天相同的Bearer和X-User-Id规则：

- GET `/api/knowledge-graph/search?q=舍曲林&limit=20`
- GET `/api/knowledge-graph/entities/{id}`
- GET `/api/knowledge-graph/entities/{id}/neighbors?limit=40&relation_type=INTERACTS_WITH`
- GET `/api/knowledge-graph/stats`

数据库断开时接口返回503及友好提示，不把数据库错误详情返回浏览器。页面只读，不提供任意Cypher或写入接口。

## 构建、切换与回退

普通使用仍按原启动步骤。新开PowerShell如禁止运行脚本，先仅为当前进程设置执行策略：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd D:\PsyConsult
.\scripts\run.ps1 infra
.\scripts\local-app.ps1 start
```

重新生成并校验（不连接数据库，但会更新标准化JSON文件）：

```powershell
.\.venv\Scripts\python.exe scripts\build_knowledge_graph.py --dry-run
```

导入及切换：

```powershell
.\.venv\Scripts\python.exe scripts\import_graph.py --dataset kg_v1
.\.venv\Scripts\python.exe scripts\select_graph_version.py kg_v1
.\scripts\local-app.ps1 stop
.\scripts\local-app.ps1 start
```

回退到旧图谱：

```powershell
.\.venv\Scripts\python.exe scripts\select_graph_version.py legacy
.\scripts\local-app.ps1 stop
.\scripts\local-app.ps1 start
```

恢复增强版时把版本改回kg_v1，并再次重启。切换脚本会先检查版本是否有数据；仅修改本机忽略文件中的KG_VERSION，不输出密钥。旧214个节点、423条关系及旧缓存集合均保留。已有聊天历史不会重写，请用新会话检查切换后的回答。

增强节点统一使用KGEntity，关系为KG_LINK，实际医学关系类型保存在kind字段及payload；源记录使用KGSource，版本清单使用KGDataset。它们与原节点隔离。整个导入在单一事务内完成，并在提交前核验数量；导入失败不会发布就绪版本。相同内容重复导入保持数量不变。后续内容变更应创建新版本，不能覆盖已发布的kg_v1。

## 验收

- 后端固定案例涵盖中文长句、英文名、症状别名、同名多类型、双药查询、未收录与输入边界。
- `scripts/check_knowledge_graph.py`：真实数据库检查，重复导入、22条候选检索案例、关系来源与旧图谱隔离；报告为 `docs/KNOWLEDGE-GRAPH-VERIFICATION.json`。
- `scripts/check_graph_chat.py`：真实模型三条Agent入口及新版缓存；仅用教学问题，会产生API费用。
- `app/test/test_knowledge_graph_data.py`、`test_knowledge_graph_api.py`：数据完整性、检索、接口鉴权、失效提示及缓存版本隔离。
- 前端门禁：`npm run type-check`、`npm run build`。

当前实现按214实体规模读取候选再在Python排序；适合本地示例规模。大规模图谱需另行设计全文索引及分页。第一轮完成来源追溯与结构增强，医学内容仍需原文核实。

## 本机最终验收结果

- 后端49项测试通过，其中原有19项、新增30项；Python语法检查通过。
- 前端类型检查、生产构建通过；保留上游第三方注释及主包体积提示。
- 真实数据库重复导入通过；22条固定候选案例与3组关系来源检查通过。
- 真实模型三条入口通过（诊断→治疗→药审、治疗→药审、直接药审）；均实际调用query_knowledge_graph。新版缓存命中约0.2秒，非性能保证。
- HTTP实测legacy回退成功，再恢复kg_v1；两个版本缓存集合名称不同。
- 浏览器实测搜索、筛选（35条关联缩小为4条指定关系）、来源原始记录展开、画布回中、聊天草稿切换保留；390px窄屏无横向溢出，1440px宽屏图谱/详情双栏。
- 当前默认KG_VERSION=kg_v1；前后端在本机运行。截图：`docs/KNOWLEDGE-GRAPH-UI.png`。
- 所有改动保留在本地工作区，未提交或推送。

报告：`KNOWLEDGE-GRAPH-VERIFICATION.json`（数据/检索）、`KNOWLEDGE-GRAPH-CHAT-VERIFICATION.json`（真实模型/SSE）、`KNOWLEDGE-GRAPH-ACTIVATION.json`（回退/恢复）。

## 界面调整（2026-10-19）

图谱节点改为名称内嵌的圆角卡片，中心实体以深青色突出；默认缩放不超过100%，避免少量节点被自动放大。多实体采用分层环形排布，提供独立放大、缩小与回中按钮。选中关系时同步高亮连线。搜索栏、中文关系筛选、图例、来源卡片和待审核折叠区同步整理；长实体名在图中省略显示，详情保留完整名称。新版截图为 `KNOWLEDGE-GRAPH-REDESIGN.png`。
