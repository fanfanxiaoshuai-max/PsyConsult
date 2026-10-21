# 知识图谱候选版处置与补查

后续已增加只读候选预览、逐项专家待审包及本地演示验收，详见[演示与专家审核交接](CANDIDATE-DEMO-HANDOFF.md)。下文保留原处置阶段记录，专家审核仍未完成。

日期：2026-10-20。399项修订均已有结构化处置，已落地为可重复构建的**离线候选版**，尚未替换运行中的kg_v2。

## 已执行的处置

- 899项冻结记录全部进入处置台账，与原审核逐条绑定。
- 399条需修订项已在候选版执行安全处置：移除106个原属性、停用230条原关系、限制63个实体仅供显示。
- 为这399项保存了原始记录指纹、具体修订及原文依据。首批50项和后续349项均已应用候选编辑；后续349项包括316项有条件替换、33项明确撤销。详见[后续全量结构化报告](KNOWLEDGE-GRAPH-V3-STRUCTURED-02.md)。
- 13条缺失或含糊端点记录继续隔离，没有猜测端点或恢复导入。
- 候选实体和关系全部标为不进入推理。增加发布白名单，kg_v3、kg_v3_candidate及未知版本会在数据库读取和版本切换前被拒绝。

**已执行的是旧断言的安全处置，不是399条临床修订全部完成。**结构化草案也尚未通过临床专家审核，不能直接生成处方或诊断规则。运行图谱、原审核结论均未覆盖。

## 55条依据不足项的补查

新增取得21份原始资料：6份具体产品标签/SmPC、15篇论文的原作者摘要。摘要来自官方NLM接口，未取得或宣称阅读论文全文。

| 补查结果 | 数量 | 当前处理 |
|---|---:|---|
| 找到限定范围的替换依据 | 37 | 保存候选说明、来源、地区/人群/制剂限制；原断言继续停用 |
| 新资料仍不能支持原断言 | 7 | 不恢复原关系，也不据此证明相反结论 |
| 证据存在分歧 | 2 | 并列记录证据与局限，禁止显示为“无相互作用” |
| 本轮仍未解决 | 9 | 保留原逐条检索记录，继续待补证 |

例如，氟伏沙明影响阿立哌唑清除的研究不能证明反向升高氟伏沙明；特定联合治疗试验不能证明数学意义的“协同增效”；美国或英国标签不能写成中国批准规则。这些限制已进入补查台账。

原审核的55条依据不足结论未被覆盖；37条是新增的候选替换依据数量，不是新增“审核通过”数量。全部临床专家审核仍为待完成。

## 文件与复核

- `knowledge_sources/v3/remediation/rechecks.json`：55条逐项补查结果。
- `knowledge_sources/v3/remediation/sources.json`：21份来源元数据、公开链接、缓存指纹；原始缓存位于被忽略的`.tools/knowledge_sources/v3/remediation/`。
- `knowledge_sources/v3/remediation/progress.json`：候选处置统计及候选内容指纹。
- `mock_data/kg_v3_candidate/candidate.json`：899项处置、399条草案、隔离记录、来源定位和输入指纹。
- [可搜索处置台账](KNOWLEDGE-GRAPH-V3-REMEDIATION.html)：输入药物、疾病或状态，可查看具体处理和草案。
- `agent/core/graph/remediation.py`：构建、来源指纹检查、原文定位检查及候选校验。
- `agent/core/graph/release.py`：显式发布白名单。
- `app/test/test_graph_remediation.py`：覆盖范围、停用效果、原文篡改、研究方向和发布阻断回归。

已有原文缓存时，在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/prepare_graph_rechecks.py
.\.venv\Scripts\python.exe -X utf8 scripts/prepare_structured_graph_batch.py
.\.venv\Scripts\python.exe -X utf8 scripts/prepare_remaining_graph_batch.py
.\.venv\Scripts\python.exe -X utf8 scripts/build_graph_candidate.py
```

补充资料缓存缺失时，先运行`scripts/fetch_remediation_sources.py`（需要网络）。原有50项审核来源仍按既有获取流程准备。缓存缺失、指纹变化或论文摘要定位不符会阻止构建；不会退化为默认通过。

## 发布前仍需完成

399项的结构化处置已完成。发布前仍需对临床内容与适用条件进行专业复核；对已撤销但需要替代值的项目、原55项依据不足和13项隔离记录取得直接依据或维持停用；完成新版独立联调。目前`activation_ready=false`，新增可用于推理的规则为0。现有kg_v2也仍是未经临床专家审核的原型资料。

## 验证

全量后端回归通过；候选构建可重复，候选内容与封存输入一致。回归覆盖来源指纹、55条补查覆盖、399条处置、研究方向、证据分歧、篡改拒绝、候选版禁用，以及kg_v2文件与处置前指纹一致性。前端代码本轮未修改。
