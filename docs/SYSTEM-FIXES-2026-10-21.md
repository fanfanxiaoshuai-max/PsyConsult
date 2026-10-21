# 整体验收问题修复与复验

后续A08专项处理见 [医学表述一致性修复记录](CLINICAL-CONSISTENCY-2026-10-21.md)。本文件保留该专项开始前的剩余问题描述。

日期：2026-10-21。对应 [原始14项验收清单](SYSTEM-ACCEPTANCE-2026-10-21.md)。原报告保留发现问题时的结果，不覆盖历史失败记录。

本轮完成已确认的软件缺陷修复，并修正已复现的诊断资料错误。问答继续使用自然语言，不恢复证据编号、逐条来源清单或固定评测界面。这里的回归测试是开发检查，不是用户界面新增功能，也不代表临床有效性认证。

## 逐项结果

| 编号 | 本轮处置 | 主要文件 | 复验与边界 |
|---|---|---|---|
| A01 用户隔离 | Redis/内存检查点使用用户和会话共同生成的命名空间；令牌绑定身份，拒绝冒用用户头 | app/service/chat_service.py；app/dependencies/auth.py | 内存与真实Redis合成探针通过；旧的未隔离检查点不自动导入 |
| A02 病例记忆 | 长期事实按用户＋会话读写，不再按医生汇集不同病例 | app/service/chat_service.py | 同医生两个病例及不同用户的合成读写回归通过；跨会话合并同一患者尚无病例主索引 |
| A03 审核权限 | 支持reader/reviewer/admin；普通用户不能审核，审核员不能发布/启用/回退；操作人由令牌确定 | app/dependencies/auth.py；app/app_config/settings.py；app/router/project_workbench.py | 身份冒用与各写操作的403/成功用例通过；这是令牌身份授权，尚无登录/账号管理界面或医院SSO |
| A04 图谱端点 | 新记录保留实体ID；历史快照从其封存的实体详情成员关系恢复端点，遇歧义拒绝猜测 | agent/core/graph/browser_projection.py；candidate_preview.py；snapshot_repository.py；project_workbench.py | 精神分裂症疾病实体恢复13条记录/12条联系；同名鉴别概念保留自己的2条记录/1条联系；128实体、276记录、162实体对联系未缩水 |
| A05 刷新恢复 | 本机按已认证用户保存会话、消息及知识版本；恢复选中会话；损坏数据不直接加载 | front/clinical_cds/src/api/chatSessions.ts；src/App.vue | 浏览器实际刷新、切换通过；不等于服务器病历归档或跨设备同步；清理浏览器数据会清除本机记录 |
| A06 重复追问 | 复述、补问类请求只进入诊断阶段并尊重本轮范围；治疗阶段不重复症状/追问 | agent/agents/orchestrator.py；diagnosis_agent.py；treatment_agent.py | 实际追问只执行诊断阶段，保留3周病程，不再重复两遍 |
| A07 药物冗长 | 聊天使用简版药物视图，不输出记录ID、原始JSON和逐条来源；完整记录留在知识详情/原报告 | agent/core/graph/evidence_report.py；agent/agents/drug_review_agent.py | 舍曲林＋帕罗西汀样本从14946字符降至91字符；不能把单药或类别背景当作药物对的直接结论；换药间隔等条件保留回归通过 |
| A08 标准混用 | **部分修复，医学内容一致性仍待收敛**：修正焦虑资料的病程、附加症状、惊恐条件及社交焦虑编码；补充适应障碍鉴别；停用同义词表未经核对的编码和量表条目映射 | mock_data/icd11_anxiety.md；agent/core/clinical_reference.py；agent/config/symptom_synonyms.json；agent/tools/vector_tool.py | 资料入口回归通过，真实样本已纠正GAD阈值和原症状编码；但仍出现应激源日期未明却概括“符合时间条件”等表述，尚不标记医学内容整体验收通过 |
| A09 断流生命周期 | 无完成帧的EOF明确失败并保留已有正文；支持停止、重新提问；后端210秒/前端240秒超时；刷新时标出未完成回答 | front/clinical_cds/src/api/chatStream.ts；src/App.vue；app/service/chat_service.py | 分片UTF-8、无末尾换行、截断、异常、取消与超时回归通过；界面停止和恢复输入已实测 |
| A10 日期测试 | 对齐封存包的生成日期，再严格比较其余内容，避免日期跨天导致内容一致仍失败 | app/test/test_candidate_preview.py | 完整回归通过；不放松条目内容或审核处置的校验 |
| A11 校验写文件 | 已存在且内容一致的封存台账只读校验，不再重写 | agent/core/graph/audit.py | 两次校验mtime保持不变；本轮完整回归未再出现该写入失败 |
| A12 路由等待 | 明确症状、诊断限定、追问和药物审查走确定路径；其他路由模型20秒超时后回退 | agent/agents/orchestrator.py | 超时回退回归通过；症状样本约30秒完成，仍需另做并发和性能基准，不能保证每次时延 |
| A13 明文日志 | 移除短输入、缓存匹配问题和向量查询正文的显式记录，保留长度、状态和耗时 | app/service/chat_service.py；agent/tools/vector_tool.py | 对修改路径检查并保留日志回归；未清理历史日志，不代表完成生产日志/第三方SDK隐私审计 |
| A14 内部英文 | 输入校验改为中文标签；补齐治疗反应、病因排除等类别名称 | front/clinical_cds/src/App.vue；components/knowledge-graph/labels.ts | 浏览器短输入显示“输入提示”，不再显示input_validation |

## 验证记录

- 后端完整回归：**235通过**，38.96秒。最后补充医学资料与提示后，相关路径再次复测：**24通过**。
- 前端聊天与保存回归：**9通过**；类型检查和生产构建通过。
- 构建仍有既有的第三方PURE注释、大包提示；Python保留langchain-community弃用提示。这些提示未作为本轮功能失败处理。
- 最终运行探针使用合成数据；原启用版本保持**知识版本2 / project-cf5cb3277205**，未重新发布或切换真实台账。
- 问答策略、已核对资料或同义词发生修改并重启后，会改变缓存策略指纹，避免再次命中修正前的答案；发布知识快照的原始字节和校验和保留。

本机证据（忽略目录，不包含真实患者信息）：

- `.tools/fix-pytest-v8.log`、`.tools/fix-last-targeted.log`
- `.tools/fix-acceptance-v8/runtime-probes.json`、`medical-spotcheck.json`及各合成回答JSON
- `.tools/fix-acceptance-final/redis-isolation.json`
- `.tools/fix-acceptance-20261021/refresh-restored.png`、`cancel-and-retry.png`
- `.tools/fix-acceptance-20261021/graph-endpoints-restored.png`：界面已显示疾病节点13实体/12联系

### 仍未关闭的内容问题

最终合成样本见`final_symptoms.json`。虽然回答已保留3周病程、使用数月条件、改用正确的适应障碍编码，且不再声称已经排除躯体病因，但仍存在：

- 已承认应激源日期未知，又在支持线索中写成符合起病时间条件。
- 把当前3周病程概括为不满足其他焦虑障碍的常规时间要求，缺少足够个体信息。
- 默认不主动输出编码的表达要求没有被模型稳定遵守。

因此，技术探针中的PASS仅代表请求、版本及流式流程成功，不能作为这段医学内容全部正确的证明。这部分保留为A08待复核项；本轮未用文本替换掩盖上述矛盾，也未恢复用户已撤销的证据编号展示。

## 医学资料修正的出处

使用已封存并核对哈希的WHO ICD-11 CDDR 2024 PDF，出版信息见 [WHO官方页面](https://www.who.int/publications/i/item/9789240077263)。核对页码为PDF284/印刷266（广泛性焦虑）、PDF289/印刷271（惊恐）、PDF302/印刷284（社交焦虑）、PDF370/印刷352（适应障碍）。修改的是独立RAG摘要与问答入口，不把这些修改伪装成重新发布了知识图谱。

旧Milvus集合保留。命中旧焦虑文档时返回当前核对文本；焦虑/应激相关查询可直接读取本地核对摘要，不依赖旧分块或重新计算向量。本轮未全量重建其他指南与说明书集合，也未做全面医学认证。

## 本地身份与角色配置

当前本机继续使用既有API_AUTH_TOKEN，绑定doctor_001，默认本地管理员；原密钥未修改。浏览器从`/api/identity`读取身份，不再用可任意填写的用户头作为身份来源。

需要多用户时，在`agent/.env`配置API_AUTH_USERS JSON映射，字段为每个用户的token和role（reader/reviewer/admin）；示例见`agent/.env.example`，示例令牌必须替换。配置多身份后，旧单令牌路径不再接受请求。前端凭其配置的访问令牌加载对应用户及权限；本轮不创建任何真实新账号或新密钥。

reader可问答和浏览；reviewer另外可审核；admin另外可发布、启用和回退。未开启任何认证时不允许修改知识。角色控制并不能替代后续账号生命周期、医院SSO和审计制度。

## 后续需单独决定的范围

1. 服务端病例档案、跨设备同步、会话导出/清理和保留策略；当前刷新恢复使用本机浏览器存储，Redis推理检查点仍有24小时TTL。
2. 登录/账号管理或医院SSO、凭据签发和撤销；当前完成的是令牌绑定身份及后端角色校验。
3. 其他医学资料与不同病例的持续复核，以及并发、故障恢复和响应时延基准。样本正确不等于所有医疗回答已经通过验收。
