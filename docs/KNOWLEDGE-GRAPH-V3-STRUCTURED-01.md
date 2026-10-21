# 首批结构化修订

阶段记录：本报告保留首批50项的结果及当时测试数据。后续349项现已完成结构化处置，最新状态见[后续全量报告](KNOWLEDGE-GRAPH-V3-STRUCTURED-02.md)。

日期：2026-10-20。本批把50项修订落实到离线候选数据；399项中仍有349项待结构化。**候选数据已改变，不代表临床审核通过，也未切换运行版本。**

## 实际改变

| 范围 | 原记录项数 | 候选数据中的结果 |
|---|---:|---|
| 症状示例 | 18 | 父领域到例子的错误`SUBTYPE_OF`改为`HAS_EXAMPLE`，不倒置端点，也不把例子当作诊断充分条件 |
| 精神分裂症病程 | 6 | 3个节点改为`CourseSpecifier`，3条关系改为`HAS_COURSE_SPECIFIER`；附具体病程条件 |
| 编码 | 14 | 更正1项；3项改为相关类别映射；10项撤销错误或过宽的编码，不猜测替代码 |
| 剂量、浓度、换药与相互作用 | 12 | 11项由15条带范围的记录替代；1项撤销未限定的锂起始量，另行待确认 |
| 合计 | 50 | 全部记录修改前后结果、来源定位与原审核指纹 |

多个原始条目可以对应同一条新规则，因此原记录项数与新规则数不同。相同新规则按稳定标识去重，15条规则通过15条`HAS_SCOPED_RULE`关系连接对应药物。候选结构图共36条关系，包含21条已改写的原关系。

具体变化包括：恶劣心境的ICD-11编码从6A73改为所核WHO CDDR 2024的6A72；抑郁障碍上位概念不再直接等同F32/F33；病程节点附上相应发作、缓解间隔和持续型适用条件。持续型在首次发作时的至少一年要求被保存为有条件的要求，没有变成所有病程的统一阈值。

药物记录把地区、来源版本、适用人群、适应症、阶段及合用情境分开。锂的美国标签和英国指南范围保留各自单位与情境；浓度不会填入起始剂量字段。换药记录分别存储两个方向；相互作用记录区分影响药物和受影响药物，不自动恢复原来的绝对禁忌关系。

本批依据已有审核所绑定的原文实施，未覆盖原`reviews.json`，未把补查或专家状态改成通过。10项撤码及1项撤销起始量属于已落实的数据编辑，但其具体替代值仍待补充，不能据50项编辑宣称50个医学问题均已解决。

## 查看与复现

- [修改前后对照，可搜索](KNOWLEDGE-GRAPH-V3-STRUCTURED-01.html)
- `knowledge_sources/v3/remediation/structured-batch-01.json`：50项明确编辑指令及原记录/审核指纹。
- `knowledge_sources/v3/remediation/structured-receipt-01.json`：实际修改结果、批次和候选指纹。
- `mock_data/kg_v3_candidate/structured-graph.json`：仅包含本批结构化结果的图数据。
- `agent/core/graph/structured_candidate.py`：校验、应用编辑、规则去重和候选查询。
- `app/test/test_structured_graph_candidate.py`：编码、方向、病程条件、单位、剂量范围及来源约束回归。

已有原文缓存时，在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/prepare_structured_graph_batch.py
.\.venv\Scripts\python.exe -X utf8 scripts/build_graph_candidate.py
.\.venv\Scripts\python.exe -X utf8 scripts/inspect_graph_candidate.py "6A72"
.\.venv\Scripts\python.exe -X utf8 scripts/inspect_graph_candidate.py "幻听"
.\.venv\Scripts\python.exe -X utf8 scripts/inspect_graph_candidate.py "锂盐"
```

候选查询仅用于检查结构化结果。它先核对候选与审核输入的一致性，再搜索新值；不把已撤销编码、旧别名或历史草案当成当前事实返回。

## 验收和边界

本批完成后，全量后端回归为**143项通过**，包括18项新增结构化回归。命令行候选查询也已实际确认：搜索6A72返回恶劣心境，且`activation_ready=false`。

针对本批的回归检查覆盖：端点完整性；原关系方向保持；错误子型关系消除；6A72可检索且6A73不再作为匹配别名；病程限定；地区与单位分开；浓度与剂量分开；换药方向；相互作用方向；缺失/篡改的证据、取血时间、数量或审核标记被拒绝。

候选版仍为`activation_ready=false`，全部新增节点与关系均不进入自动推理。kg_v2文件及其版本选择未更改，网页不会因本批离线数据变化而显示新版结果。后续349项处置见上方最新报告；未解决内容的补证、临床专业审核以及新版独立联调仍在发布范围之外。
