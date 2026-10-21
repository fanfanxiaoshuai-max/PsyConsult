# 知识图谱第二轮：五种药物的条件性证据

实施日期：2026-10-19。当前启用 `kg_v2`。本轮范围为舍曲林、帕罗西汀、氟西汀、奥氮平、锂盐，每种6条，共30条原文核对记录。这里的“核对”指程序代理读取并定位原始说明书，不代表临床专家审核或完整临床知识库。

## 使用

打开 http://127.0.0.1:5173，点击“知识图谱”，搜索药物并选择候选。默认仅显示已核对原文的关系；点击连线或下方关系列表查看摘要、适用条件、处理提示、制剂范围、原文页码和链接。勾选“显示旧版未核实关系”可查阅旧记录，原始属性默认折叠并标注未逐项核实。旧版关系复核清单保留109条涉及本轮药物的旧关系及复核状态，其中未覆盖的记录不标为已验证。

`kg_v2` 有230个实体、406条关系：30条已核对记录与376条旧版未核实关系。旧关系仍存储，但默认不进入v2检索和药物审查。`kg_v1` 和 legacy 原库仍独立存在，未清空。

## 来源与边界

| 药物 | 实际使用的文件 | 标签修订 | 地区 | 记录数 |
|---|---|---|---|---|
| 舍曲林 | 晖致中国公开的左洛复片说明书 | 2026-03-01 | 中国 | 6 |
| 帕罗西汀 | 南方科技大学医院公开的石家庄康泽20mg普通片说明书扫描件 | 2022-05-25 | 中国 | 6 |
| 氟西汀 | 礼来医学网百优解胶囊说明书 | 2025-02-05 | 中国 | 6 |
| 奥氮平 | 翰森/豪森欧兰宁普通片说明书 | 2025-08-21 | 中国 | 6 |
| 锂盐 | DailyMed上Hikma碳酸锂普通片/胶囊标签，非缓释制剂 | 2026-08 | 美国补充 | 6 |

帕罗西汀网站的2025-03-18为医院网页发布日期，不能当作说明书修订日期。锂盐的6条记录明确保留美国地区和制剂限制，不能替代中国批准说明书。奥氮平旧礼来链接实际404，已记录为不可用且不用于任何证据；本轮改用豪森公开原文。未虚构指南等级、临床专家签名或失效链接的核对结果。

原文PDF仅保存在被忽略的 `.tools/knowledge_sources/`；目录中提交的是来源元信息、文件SHA256、页码和摘要。重新下载时如原文内容改变会拒绝静默更新。核对记录均为 `source_checked_by_agent`，全部 `expert_review=pending`。

## 条件与旧记录处理

每条记录保留人群、地区、制剂、条件、行动提示、页码及修订日期；`section`为原文检索主题提示，页码采用PDF物理页序号。不按三元组合并不同条件。不会自动把药物类别警示扩展成每个药物成员的直接关系。

- 氟西汀与MAOI的双向清洗期分别保存；不把两个方向统一为14天。
- 氟西汀与锂盐的血锂升高和降低报告同时保留。
- 舍曲林与锂盐的试验药代结果和震颤增加同时保留，不概括为无风险。
- 旧“帕罗西汀与舍曲林绝对禁忌”记录缺乏本轮原文足够支持，标记待进一步核实并排除出v2推理。此处理不表示可以安全联用。
- 13条原始缺端点关系继续隔离；本轮证据不足以修复它们，未补造端点。

这是有限覆盖的药物证据升级。疾病、诊断、治疗、剂量和其他药物旧记录未因此变成医学原文已核实；原RAG文档也没有被自动认证。

## Agent与缓存

诊断和治疗仍沿用原Agent流程。`kg_v2`的药物审查节点使用固定检索结果直接生成证据报告，逐条保留摘要、条件、行动提示及来源，不让模型补造监测频率或处方。当前问题未给药名时，优先参考本轮治疗输出，再参考最近明确给药名的用户轮次。数据库不可用时明确返回证据不足。

改用字段报告的原因：真实模型试验虽能引用原文，仍额外添加了来源未支持的监测频率。试验结果保留在 `KNOWLEDGE-GRAPH-KG_V2-LLM-PILOT.json`，作为回归背景；最终报告在 `KNOWLEDGE-GRAPH-KG_V2-GROUNDING.json`。该改动仅约束药物审查报告，不表示所有模型输出都已完成逐句临床审核。

缓存仍按图谱版本与用户隔离，kg_v2不会复用kg_v1答案。回退只改变活动图谱版本，不回滚整个代码工作区。

## 文件位置

| 内容 | 文件 |
|---|---|
| 来源目录、日期、地区、制剂、SHA256 | `knowledge_sources/catalog.json` |
| 30条条件性证据原始维护文件 | `knowledge_sources/evidence.json` |
| 涉及五药的旧关系复核清单 | `knowledge_sources/review.json` |
| 原文文件哈希与引用页码范围验证 | `knowledge_sources/verification.json` |
| v2生成器 | `agent/core/graph/evidence_dataset.py` |
| 结构与来源完整性校验 | `agent/core/graph/validator.py` |
| 默认过滤、来源读取、统计 | `agent/core/graph/repository.py` |
| Agent检索、类别上下文与来源格式 | `agent/core/graph/retriever.py` |
| 条件性报告生成 | `agent/core/graph/evidence_report.py` |
| 药物Agent接入 | `agent/agents/drug_review_agent.py` |
| 只读接口及开关 | `app/router/knowledge_graph.py`、`app/service/knowledge_graph_service.py` |
| 图谱页面与证据卡片 | `front/clinical_cds/src/components/knowledge-graph/` |
| 前端类型与请求参数 | `front/clinical_cds/src/types/knowledgeGraph.ts`、`src/api/knowledgeGraph.ts` |
| 生成后的独立版本 | `mock_data/kg_v2/` |
| 数据/报告回归测试 | `app/test/test_knowledge_graph_v2.py` |

## 构建、验收和回退

在项目根目录的PowerShell中运行；若系统执行策略限制脚本，用下列单次进程命令，无须永久改变系统策略。

```powershell
# 只构建并校验，不连接数据库
.\.venv\Scripts\python.exe -X utf8 scripts/build_knowledge_graph.py --version kg_v2 --dry-run
# 导入独立版本（需要Neo4j）；同摘要重复导入幂等，内容变化会拒绝覆盖
.\.venv\Scripts\python.exe -X utf8 scripts/build_knowledge_graph.py --version kg_v2
# 启用并重启本项目
.\.venv\Scripts\python.exe -X utf8 scripts/select_graph_version.py kg_v2
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local-app.ps1 stop
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local-app.ps1 start
# 回退：将上面的选择版本改成kg_v1，再执行stop/start
.\.venv\Scripts\python.exe -X utf8 scripts/select_graph_version.py kg_v1
```

来源复查：`scripts/fetch_knowledge_sources.py` 下载目录中的公开PDF；`scripts/audit_knowledge_sources.py` 校验实际字节及页码范围，后者需要可选的pypdf，仅用于离线资料审计，不是运行系统的必要依赖。证据文件应先复核再构建；已导入版本不可变，更改内容应建立新版本。

验收结果：后端73项测试通过；前端类型检查与构建通过（仍有原依赖注释及包体积警告）。数据库重复导入、旧版本计数、默认过滤、旧关系显示开关、只读API、五药各6条证据、真实SSE、三Agent路由、独立缓存及kg_v2→kg_v1→kg_v2切换均已验证。详见 `KNOWLEDGE-GRAPH-KG_V2-VERIFICATION.json`、`KNOWLEDGE-GRAPH-KG_V2-CHAT-VERIFICATION.json`、`KNOWLEDGE-GRAPH-ACTIVATION.json`。

页面验收截图：`KNOWLEDGE-GRAPH-V2-UI.png`。全部改动仍在本地工作区，未提交或推送。
