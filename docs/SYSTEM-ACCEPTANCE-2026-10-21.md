# PsyConsult 整体验收与剩余问题清单

后续修复与复验结果见 [2026-10-21修复记录](SYSTEM-FIXES-2026-10-21.md)。下文保留最初验收时的发现与失败结果。

验收日期：2026-10-21（Asia/Shanghai）。目标：课题展示、本地完整运行，并据此决定下一轮范围。

**结论：主链路可运行，但整体验收尚未全部通过。已确认14项问题或设计缺口，另有未验证范围。先修已有功能，再决定新增功能。**

本轮未修复应用逻辑、未切换真实启用版本、未改密钥或审核决定。问答使用少量合成病例，会产生现有模型接口调用；隔离探针使用随机合成标记和测试会话。已有测试和校验流程会同内容重写 inventory.json，这一副作用记录为A11。

## 验证结果

| 项目 | 结果 | 证据与边界 |
|---|---|---|
| Python语法与前端类型检查/构建 | 通过 | compileall、npm run build；构建仍有第三方注释及大包提示 |
| 依赖一致性 | 通过 | 使用项目自带 uv，检查120个包无冲突；venv未装pip不是依赖损坏 |
| 后端完整测试 | **212通过、2失败，共214项** | 36.59秒；单独复跑失败项为1失败、1通过，未把首次失败隐藏 |
| 本地接口/会话探针 | 22通过、2失败，共24项 | 两个失败探针对应同一个用户隔离问题，分别使用内存和真实Redis |
| Redis | 通过 | 随机检查点写入、重连、恢复、继续；TTL 86392–86398秒；未重启容器 |
| Milvus | 通过连接 | 指南集合50条；长期记忆与基础缓存集合各12条。这些计数不等于医学质量或长期记忆端到端通过 |
| Neo4j | 通过连接 | 1976个节点；当前发布快照浏览/问答并不依赖实时Neo4j去重建全部内容 |
| Redis/Milvus不可用降级 | 通过独立进程探针 | 指向本机关闭端口，分别无状态/空记忆/缓存未命中；未停止正在运行的服务 |
| 图谱与发布版 | 部分通过 | 128实体、276唯一知识记录、162实体对连线；记录集合未丢，但发现重名端点歧义A04 |
| 图谱常见搜索 | 通过接口检查 | 抑郁症、双相情感障碍、失眠、帕罗西汀、舍曲林、精神分裂症、6A72；不能据此忽略其他同名候选 |
| 审核/发布/回退 | 隔离测试通过 | 工作版/发布版浏览及899条审核导出成功；真实激活指针未改；角色授权缺口见A03 |
| 真实模型问答 | 流程完成，质量部分不通过 | 3次真实样本均正常完成并固定至同一知识版本，发现重复、冗长及标准混用 |
| 前端流式异常 | 部分通过 | 正常分片、连接失败提示通过；无done的截断流未标失败；是对原函数的合成fetch探针 |
| 会话界面 | 切换通过、刷新恢复失败 | 浏览器实测；前端内存状态与后端检查点不能混为一谈 |

当前启用：知识版本2（project-cf5cb3277205）。工作区899条原始审核项中787项项目审核通过、44项停用、68项依据不足/隔离；276条发布知识记录与899条原始审核条目不是同一统计口径。

## 实际问答样本

| 合成输入 | 执行阶段（省略总路由） | 用时 | 结果 |
|---|---|---|---|
| 最近3周压力大、心慌、入睡困难；只要症状/鉴别 | 诊断 | 90.738秒 | 没有追加空药物审查；有标准混用A08 |
| 复述病程，再问两个问题 | 诊断＋治疗 | 8.797秒 | 记住3周，但同一段内容重复两遍A06 |
| 仅审查舍曲林与帕罗西汀联用 | 药物审查 | 4.198秒 | 路由正确；14,946字符的冗长记录清单A07 |

第一轮accepted状态帧在0.076秒到达，但这不是医学正文首字时间。后台该次总路由用时71.348秒。样本数量有限，不宣称性能SLA或总体准确率。

## 问题总表

P0：多用户使用前必须解决的隔离问题。P1：影响主要行为、内容可靠性或重要使用体验。P2：稳定性、验收基线、运维和展示优化。优先级不是声称正在发生真实患者数据泄漏。

| 编号 | 优先级 | 状态 | 问题 |
|---|---|---|---|
| A01 | P0 | 已复现 | 不同用户共用 session_id 时会话串读 |
| A02 | P1 | 代码确认，未验证实际跨病例误召回 | 长期临床记忆按医生用户归集，缺少病例边界 |
| A03 | P1 | 已复现（隔离接口探针） | 审核与发布未区分普通使用者和管理员 |
| A04 | P1 | 已复现 | 图谱以名称连接，重名实体被错误分配关系 |
| A05 | P1 | 已复现（浏览器） | 刷新页面后会话列表与消息丢失 |
| A06 | P1 | 已复现（真实模型） | 多轮追问被诊断、治疗两个阶段重复回答 |
| A07 | P1 | 已复现（真实接口） | 药物审查仍输出冗长的记录编号和原始字段 |
| A08 | P1 | 已复现并抽查原文 | 回答中的诊断标准存在来源混用 |
| A09 | P1 | 中断探针已复现；超时/取消缺口代码确认 | 流式回答中断识别与请求生命周期不完整 |
| A10 | P2 | 已复现，根因确认 | 审核包测试随日期变化失败 |
| A11 | P2 | 一次失败、单独复跑通过；并发根因待进一步确认 | 校验路径重写共享台账，出现文件写入失败 |
| A12 | P2 | 样本已测，未做性能基准 | 首轮症状分析出现较长路由等待 |
| A13 | P2 | 代码确认；未检索任何真实病例日志 | 日志仍可能包含临床输入片段 |
| A14 | P2 | 界面已复现 | 输入校验提示暴露内部英文节点名 |

## 逐项处置与验收标准

### A01 · 不同用户共用 session_id 时会话串读（P0）

**影响：** 多用户接入时可能把另一位用户的上下文带入本轮推理。仅本地单人演示不能证明用户隔离。

**验证证据：** 在内存和真实 AsyncRedisSaver 两个探针中，用户 B 的输出都包含用户 A 的合成标记；没有访问真实患者数据。

**相关文件：** `app/service/chat_service.py:190`、`app/dependencies/auth.py:19`

**建议补齐：** 后端以已认证用户＋病例/会话构造不可伪造的状态命名空间，校验会话归属；不能仅依赖前端生成的 session_id。

**再次验收必须达到：** A/B 使用同名会话仍完全隔离；冒用归属被拒绝；同一用户同一病例的多轮恢复继续通过。

**本地证据：** [isolation-probes.json](../.tools/acceptance-20261021/isolation-probes.json)

### A02 · 长期临床记忆按医生用户归集，缺少病例边界（P1）

**影响：** 同一医生处理不同患者时，长期记忆可能把前一位患者的信息带到新会话。

**验证证据：** _extract_long_term_context 与写入都仅使用 _user_fact_namespace(user_id)，没有 patient_id/case_id；本轮合成会话未达到第五轮后台提取，不宣称已实测长期记忆泄漏。

**相关文件：** `app/service/chat_service.py:73`、`app/service/chat_service.py:100`、`app/service/chat_service.py:312`

**建议补齐：** 病例事实按病例隔离，医生的展示偏好独立存储；新建病例时不得继承其他患者事实。

**再次验收必须达到：** 同医生的病例 A/B 植入不同事实后，B 检索结果不含 A；医生个人偏好仍可复用。

### A03 · 审核与发布未区分普通使用者和管理员（P1）

**影响：** 掌握共享令牌的调用方可以自行填写 X-User-Id，进入审核/发布接口；操作人字段尚不是可信账户身份。

**验证证据：** 真实 FastAPI 路由＋假的工作区对象中，doctor_001 的审核请求返回 200。使用的是测试令牌和合成条目，没有写真实台账。前端当前身份固定为 doctor_001。

**相关文件：** `app/dependencies/auth.py:19`、`app/router/project_workbench.py:10`、`front/clinical_cds/src/App.vue:201`

**建议补齐：** 接入账户身份和角色授权，普通问答权限与审核发布权限分开，后端确定操作人。

**再次验收必须达到：** 普通用户审核/发布返回 403；管理员可操作；伪造 X-User-Id 不改变已认证身份。

**本地证据：** [role-probe.json](../.tools/acceptance-20261021/role-probe.json)

### A04 · 图谱以名称连接，重名实体被错误分配关系（P1）

**影响：** 搜索选中同名实体中的不同候选时，可能看到空图；这是上轮关系恢复未覆盖到的缺口。

**验证证据：** 发布版有 5 组重名实体：精神分裂症、双相障碍、躁狂发作、物质使用、躯体疾病。前一份同名节点显示 0 条记录/连线，后一份分别有 13/4/3/2/2 条连线。并非证明每一组都应合并为同一概念。

**相关文件：** `agent/core/graph/browser_projection.py:9`、`agent/core/graph/candidate_preview.py:59`、`agent/core/graph/project_workbench.py:103`

**建议补齐：** 知识记录保留 subject_id/related_id，浏览按 ID 连接；为重名不同类型提供区分信息，旧快照兼容不得凭名称静默猜测。

**再次验收必须达到：** 逐个搜索/展开五组候选并与冻结记录的原始端点核对；不新增重复编号，不把鉴别概念与疾病定义直接混同。

**本地证据：** [duplicate-entity-names.json](../.tools/acceptance-20261021/duplicate-entity-names.json)、[ambiguous-endpoints.json](../.tools/acceptance-20261021/ambiguous-endpoints.json)、[full-graph-integrity.json](../.tools/acceptance-20261021/full-graph-integrity.json)

### A05 · 刷新页面后会话列表与消息丢失（P1）

**影响：** 演示过程中刷新/关闭页面后无法从界面找回会话；后端检查点存在不等于前端能恢复。

**验证证据：** 新建“诊疗会话 2”发送合成短输入；切换会话可找回，刷新后仅剩新的空会话。

**相关文件：** `front/clinical_cds/src/App.vue:201`、`front/clinical_cds/src/App.vue:288`

**建议补齐：** 增加受归属校验的会话列表/消息读取与恢复；选定本地单人或后端持久化方案后实施。

**再次验收必须达到：** 刷新、关闭重开均能恢复会话和版本标记，切换不会串话；清除数据有明确范围。

**本地证据：** [ui-before-refresh.txt](../.tools/acceptance-20261021/ui-before-refresh.txt)、[ui-after-refresh.txt](../.tools/acceptance-20261021/ui-after-refresh.txt)、[ui-before-refresh.png](../.tools/acceptance-20261021/ui-before-refresh.png)、[ui-after-refresh.png](../.tools/acceptance-20261021/ui-after-refresh.png)

### A06 · 多轮追问被诊断、治疗两个阶段重复回答（P1）

**影响：** 简单追问仍执行额外阶段，回答重复且徒增调用。

**验证证据：** 追问“复述已提供病程，再给出两个最需要补问的问题”，输出 322 字符，前后两半完全相同；执行了 differential_diagnosis 和 treatment_recommend。

**相关文件：** `agent/agents/orchestrator.py:43`、`agent/core/workflow/graph_manager.py:60`、`agent/agents/treatment_agent.py:45`

**建议补齐：** 识别随访/补问意图，按本轮需求选择阶段；保持用户已确认的自然回答方式。

**再次验收必须达到：** 同样追问只回答一次，仍记住 3 周病程；明确治疗问题继续正常进入治疗节点。

**本地证据：** [live_followup.json](../.tools/acceptance-20261021/live_followup.json)、[answer-quality.json](../.tools/acceptance-20261021/answer-quality.json)

### A07 · 药物审查仍输出冗长的记录编号和原始字段（P1）

**影响：** 未满足用户此前要求的自然、简洁问答体验，关键结论被大量背景资料淹没。

**验证证据：** “仅做药物资料审查：舍曲林与帕罗西汀联用”输出 14,946 字符，包含记录编号、定位和 &quot; 转义的 JSON；该药物对没有直接记录时仍列大量单药背景。路由本身正确。

**相关文件：** `agent/agents/drug_review_agent.py:23`、`agent/core/graph/evidence_report.py:70`

**建议补齐：** 默认答复聚焦所问药物/药物对，简述已知、未知和需确认条件；完整记录保留在可展开详情中。

**再次验收必须达到：** 默认正文无记录编号、原始 JSON 和逐条来源堆砌；无直接记录时清楚说明，背景不被当成直接证据。

**本地证据：** [live_drug_only.json](../.tools/acceptance-20261021/live_drug_only.json)、[answer-quality.json](../.tools/acceptance-20261021/answer-quality.json)

### A08 · 回答中的诊断标准存在来源混用（P1）

**影响：** 内容流畅不能代表医学表述准确；当前不能宣称回答医学准确性验收通过。

**验证证据：** 样本将 GAD 的“≥6个月”写成 ICD-11 要求。所缓存 WHO CDDR 2024（PDF物理第284页、印刷第266页）的 essential features 写的是“至少数个月”。原 PDF SHA-256 与来源目录一致；这是抽查发现，不是全量医学复核。

**相关文件：** `agent/agents/diagnosis_agent.py:25`、`agent/tools/vector_tool.py:93`

**建议补齐：** 术语、编码、诊断阈值绑定标准及版本；后台做代表性内容复核和回归，不恢复用户已撤销的前台证据编号格式。

**再次验收必须达到：** 选定标准的关键阈值逐条有对应原文；不能把 DSM/ICD 或不同版本要求混写；缺资料时明确未核实。

**本地证据：** [live_symptoms.json](../.tools/acceptance-20261021/live_symptoms.json)、[medical-spot-check.json](../.tools/acceptance-20261021/medical-spot-check.json)

原文依据：[WHO CDDR 2024，PDF第284页](https://iris.who.int/server/api/core/bitstreams/dcf73611-9e0f-4d5c-85f6-85a58b0da6de/content#page=284)。网络抓取该文件超时，本轮以项目已缓存且SHA-256核对通过的WHO原始PDF及页文本完成核对。不要用搜索摘要替代原文。

### A09 · 流式回答中断识别与请求生命周期不完整（P1）

**影响：** 连接正常结束但没有 done 帧时，半截回答没有标为失败；请求长期不结束时用户缺少取消操作。

**验证证据：** 执行 App.vue 原始 sendQuery/消息更新函数，仅把 fetch 换为合成流：正常分片流通过；缺 done 帧的流仍保留半截答案和阶段标签，isThinking 已变 false、failed 未设置。源码未使用 AbortController/总时限。

**相关文件：** `front/clinical_cds/src/App.vue:351`、`front/clinical_cds/src/App.vue:391`

**建议补齐：** 显式追踪完成标记，截断显示未完成；增加取消、总超时与保留部分结果的重试入口。

**再次验收必须达到：** 完整、截断、超时、断网、用户取消分别有正确终态，不把未完成回答当成成功，不串到其他会话。

**本地证据：** [frontend-stream-probes.json](../.tools/acceptance-20261021/frontend-stream-probes.json)、[frontend-stream-probe.mjs](../.tools/acceptance-20261021/frontend-stream-probe.mjs)

### A10 · 审核包测试随日期变化失败（P2）

**影响：** 现有测试套件不能稳定给出全绿结果，跨天后会产生假失败。

**验证证据：** 保存包 generated_on 为 2026-10-20，build_packet 使用当天日期。只保留保存的 generated_on 后，包的其余内容摘要完全一致；运行时 CandidatePreview 已对日期作了相应处理。

**相关文件：** `agent/core/graph/expert_review.py:118`、`app/test/test_candidate_preview.py:103`

**建议补齐：** 测试固定日期或比较稳定内容，与运行时校验语义一致；不要为消除测试失败篡改历史审核时间。

**再次验收必须达到：** 跨天/不同时区复跑得到一致结果，实际知识改动仍会使完整性校验失败。

**本地证据：** [pytest.log](../.tools/acceptance-20261021/pytest.log)、[recheck.log](../.tools/acceptance-20261021/recheck.log)、[artifact-check.json](../.tools/acceptance-20261021/artifact-check.json)

### A11 · 校验路径重写共享台账，出现文件写入失败（P2）

**影响：** 只读浏览/校验可能触发磁盘写入，存在并发或文件占用敏感性。

**验证证据：** 全量测试中 validate_candidate→validate_audit→freeze 在 inventory.json 写入时报 OSError[22]，单独复跑通过。freeze 即使文件内容不变仍调用 write；本轮未做真实工作区的破坏性压力测试，不能断言并发就是唯一根因。

**相关文件：** `agent/core/graph/audit.py:95`、`agent/core/graph/candidate_preview.py:23`

**建议补齐：** 初始化/重建与只读校验分离；写入增加必要的互斥及原子替换，避免浏览请求重写封存文件。

**再次验收必须达到：** 多个只读请求和校验并行运行不改台账字节/修改时间、不出现读半截文件或写入错误。

**本地证据：** [pytest.log](../.tools/acceptance-20261021/pytest.log)、[recheck.log](../.tools/acceptance-20261021/recheck.log)

### A12 · 首轮症状分析出现较长路由等待（P2）

**影响：** 状态提示很快出现，但正文等待时间可能影响演示体验。

**验证证据：** 首轮总耗时90.738秒、accepted帧0.076秒；该轮后台路由日志71.348秒。后续追问8.797秒，药物审查4.198秒。样本只有这三次，不计算P95、不据此宣称稳定吞吐。

**相关文件：** `agent/agents/orchestrator.py:83`、`app/service/chat_service.py:238`

**建议补齐：** 先区分模型渠道、路由与检索耗时，设定演示可接受时限；稳定性评估后再决定是否更换模型或增加规则路由。

**再次验收必须达到：** 在约定设备/渠道下，多次代表性请求的耗时分布可复现，并有可取消的超时策略。

**本地证据：** [live_symptoms.json](../.tools/acceptance-20261021/live_symptoms.json)、[live_followup.json](../.tools/acceptance-20261021/live_followup.json)、[live_drug_only.json](../.tools/acceptance-20261021/live_drug_only.json)

### A13 · 日志仍可能包含临床输入片段（P2）

**影响：** 真实使用前需要明确日志最小化、访问和保留策略。当前不能把日志轮转等同于隐私保护。

**验证证据：** vector_tool 打印 query 前120字符；缓存命中日志包含 matched_question。此次不读取真实患者会话验证泄漏，只依据代码和合成数据判断。

**相关文件：** `agent/tools/vector_tool.py:103`、`app/service/chat_service.py:209`、`app/infra/logging_config.py:47`

**建议补齐：** 默认仅记录请求标识、长度与耗时，调试内容脱敏并限制权限/保留周期。

**再次验收必须达到：** 包含合成姓名/联系方式的请求不会以明文进入普通运行日志；授权调试有明确开关与审计。

### A14 · 输入校验提示暴露内部英文节点名（P2）

**影响：** 用户看到 input_validation，影响中文界面一致性。

**验证证据：** 浏览器发送两字合成输入“验收”，正确拦截推理，但输出标题为 input_validation。

**相关文件：** `front/clinical_cds/src/App.vue:304`

**建议补齐：** 补齐阶段中文映射，输入提示无需呈现内部节点名。

**再次验收必须达到：** 短输入显示清晰中文提示，并继续不调用模型。

**本地证据：** [ui-before-refresh.txt](../.tools/acceptance-20261021/ui-before-refresh.txt)、[ui-before-refresh.png](../.tools/acceptance-20261021/ui-before-refresh.png)

## 尚未验证，不能计为通过

- 真实专家审核、全量回答医学准确率、PHQ-9/GAD-7全题评分与危机情况的完整评测。
- 高并发、多设备、多浏览器、长时间稳定性与实际P95耗时。
- 真实生产断电/容器重启/整机重启后的恢复；本轮仅验证Redis客户端重连恢复。
- 备份导出后的完整恢复、数据保留/删除策略、生产账号管理和监控告警。
- 真实模型服务商断网/配额耗尽/限流；本轮测试了本地模拟断流和Redis/Milvus关闭端口降级。
- 全新电脑从零安装；本轮验收当前已有环境，未重新安装依赖或更改系统执行策略。
- 长期临床记忆第五轮提取及同医生跨病例召回的真实端到端验证。

## 下一轮建议范围（尚未实施）

1. **先修已有功能：** 会话隔离A01、图谱端点A04、刷新恢复A05、追问去重A06、药物回答简化A07、断流识别A09。范围仍需用户决定，不自动开工。
2. **稳住质量与验收：** 标准来源核对A08、跨天测试A10、只读校验A11、耗时定位A12、中文提示A14。后台验证不需要恢复被撤销的前台证据编号格式。
3. **接入多人或真实数据前：** 病例级记忆A02、账户角色A03、日志数据保护A13，加上备份恢复与监控的明确验收。

## 复核方式

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .tools\acceptance-recheck --junitxml=.tools\acceptance-recheck.xml
cd front\clinical_cds
npm run build
cd ..\..
.\.tools\uv\bin\uv.exe --cache-dir .tools\uv-cache pip check --python .venv\Scripts\python.exe
.\.venv\Scripts\python.exe scripts\run_system_acceptance.py
```

加上 `--live-chat` 会再次调用当前模型渠道并生成新的合成会话；不加该参数时只检查本地接口、短输入及隔离探针。脚本不会执行真实发布、回退或审核变更。复跑前不要同时运行多个读写同一台账的验收进程；A11尚未修复。

证据位于本机 `.tools/acceptance-20261021/`（被Git忽略）；本报告和同名JSON是可保留的结论与问题清单。完整测试失败、已通过项目和未验证项目均保留，不用抽查代替全量结论。
