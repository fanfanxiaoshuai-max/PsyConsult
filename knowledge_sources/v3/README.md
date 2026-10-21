# kg_v3 全量核验工作目录

当前阶段（2026-10-20）：899项均已有本轮逐项检查结论，未处理项为0。838项医学内容中，371项有条件支持、399项需修订、55项依据不足、13项继续隔离；另61项仅结构一致。**清单处理完不等于全部主张获支持；临床专家审核全部待审，kg_v3尚未生成可激活图谱。现行kg_v2不受这些候选修订影响。**完整结果见`docs/KNOWLEDGE-GRAPH-V3-FULL-REVIEW.md`及可搜索的`docs/KNOWLEDGE-GRAPH-V3-REGISTER.html`。

## 固定范围

冻结自kg_v2：406条关系、13条隔离记录、230个实体、250个属性字段，共899个对象。上一轮30条已核对关系包含在406条中，全部进入本次台账，没有直接按上一轮标记自动判定本轮复核完成。

实体项核验名称、图谱类型、别名等身份信息；医学属性按独立的property项核验。61个与原实体显示名称逐字一致的name/name_cn属性只记为structural_only，不是医学命名已核实。另有838个对象需要医学来源对照。实体存在来源不等于所有属性都已核对。

## 文件

- `baseline.json`：冻结文件哈希清单。
- `baseline/`：原有实体、关系、来源、隔离记录、别名及上一轮来源声明的冻结副本。不要修改。
- `inventory.json`：899项固定清单、原始值、摘要、编号、优先级及批次。
- `attribute-lineage.json`：250个属性分别对应的原JSON文件、字段指针及原始值。
- `reviews.json`：每个对象唯一一条评审记录；保留待核对状态，不会自动判成依据不足。
- `catalog.json`：原文来源、下载状态、地区、实际字节SHA256、访问日期及原文缓存位置。
- `evidence.json`：原文对照结论及准确的推荐条款锚点或PDF物理页码。
- `search_attempts.json`：“依据不足、原文不可得、继续隔离”等结论所需的逐项检查记录，明确每项原主张和已查来源范围；不声称检索穷尽。
- `findings.json`：结构结果、399项候选修订及55项依据不足结论。13项隔离的具体处理见`reviews.json`及开放问题清单。
- `batches/2026-10-20-medication-02.json`：第二批55项独立记录包；应用前整批校验，拒绝覆盖不同的既有结论。
- `batches/2026-10-20-remainder-03.json`：原剩余746项独立记录包；没有默认剩余项结论或缩减范围。
- `receipts/2026-10-20-remainder-03.json`：历史153条已完成行不变及kg_v2数据前后哈希一致的回执。
- `progress.json`：程序校验后生成的实际进度。
- `batch-1.json` … `batch-4.json`：各对象后续处理批次。899项的台账和结构检查统一完成；批次清单用于医学/基础字段的后续分工，并非只检查了batch-1中的条目。

## 状态

- `pending_review`：未完成原文对照，不能作为已检查结论。
- `structural_only`：只确认仓库结构或文字一致性；不计为医学核验完成。
- `source_supported`：在证据中保留的版本、地区、人群与条件下，原记录获得支持。
- `amended`：原文对照表明需要修订；必须有明确的候选修改，尚未应用到现行图谱。
- `conflicting`：存在需保留的依据差异；不能静默选择一方。
- `insufficient_evidence`、`unavailable_source`、`quarantined`：必须有针对该对象的查找或检查记录，不能作为“未处理”的替代状态。

所有记录的临床专家审核仍为pending。程序代理不得伪造专家通过。NICE来源标记为UK，不能被展示成中国批准说明书或中国指南结论；WHO来源标记为WHO及2024版。

## 继续核验与复核

在项目根目录运行：

```powershell
# 校验固定范围、每项结论、来源字节及引用位置，更新进度；不写数据库
.\.venv\Scripts\python.exe -X utf8 scripts/audit_full_graph.py
# 校验并应用一个明确批次；只写离线审计台账，不启用新图谱
.\.venv\Scripts\python.exe -X utf8 scripts/apply_graph_audit_batch.py knowledge_sources/v3/batches/2026-10-20-medication-02.json
# 导出包含899项、可搜索的离线HTML台账
.\.venv\Scripts\python.exe -X utf8 scripts/export_graph_audit.py
# 获取来源目录中的公开原文；实际PDF/HTML只缓存到被忽略的.tools目录
.\.venv\Scripts\python.exe -X utf8 scripts/fetch_graph_audit_sources.py
# 从实际NICE HTML原文提取推荐条款锚点，供人工逐项阅读对照
.\.venv\Scripts\python.exe -X utf8 scripts/inspect_graph_audit_sources.py
```

来源缓存未随代码提交。缺少缓存时不能复现“原文文件已验证”的通过结果，需重新获取相同字节的原文。源站文件发生变化时，要建立新的来源版本并复核对应证据，不能更新哈希后沿用旧结论。

校验会拒绝：缩减固定清单、删除评审行、改写冻结原文、用结构检查冒充医学核对、来源不可用却判为支持、原文件哈希改变、推荐锚点不存在、PDF页码越界、未给修订方案或伪造专家审核。现阶段不提供kg_v3激活入口，避免将未完成的台账误认为已经完成核实的图谱。

`all_items_adjudicated`表示全清单都有处理结果。旧字段`full_medical_review_complete`仅表示原文对照流程完成；`full_medical_verification_complete=false`与`activation_ready=false`明确表示没有宣称全部医学主张通过、候选修订已应用或获临床专家签审。`unresolved_medical_items=68`列出依据不足与隔离项，`candidate_amendments_not_applied=399`列出待实施修订。
