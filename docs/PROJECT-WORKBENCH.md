# 知识审核与版本管理

更新日期：2026-10-20。此文替代此前只读候选预览的操作说明。侧栏“知识审核与版本管理”入口及 http://127.0.0.1:5173/#candidate 地址保持不变。

## 现在可以做什么

1. 知识浏览：切换工作版本和已启用版本，查询疾病、症状、药物或编码，查看条件、原文依据及关系展示。
2. 逐项审核：查看 899 条可追溯记录，填写意见后审核通过、退回修改或停用。支持状态筛选、分页和导出项目审核记录。
3. 版本发布与回退：填写说明、校验并发布不可变知识快照，再启用该版本；回退会恢复上次启用的版本，首次启用后的回退则恢复未启用发布版本的状态。
4. 操作记录：保存操作人、时间、条目或版本标识。页面过期后提交会被拒绝，重新加载后可重试。

界面不再要求专家签字，不显示专家待审数量或课题用途横幅。项目审核状态由已完成的数据和来源校验初始化，与历史原文核对台账分开保存，没有生成或改写专业签字记录。

初始项目状态为：787 项审核通过，44 项停用，68 项依据不足或隔离。通过项包括结构性校验和保留适用条件的修订结果；不表示原始旧值原封不动有效。历史原值仅用于追溯。依据不足、隔离和已撤销记录不能直接点击通过，需先补全数据与来源再重新构建。

## 发布的实际范围

启用现已联动本页面的“已启用版本”、普通“知识图谱”浏览及新一轮问答。详见[知识版本与问答检索联动](KNOWLEDGE-VERSION-LINK.md)。发布快照只包括审核通过的实体与修订记录，记录关联的审核项、主体和相关实体也必须通过。首次发布包含 128 个实体、277 条去重知识记录。各实体详情会引用同一记录，因此详情中的记录数量相加可能大于去重总数。

工作版本的审核变更不会覆盖已发布快照。变更后需要重新发布、启用才能反映到已启用版本；回退可查询旧快照。问答通过独立适配器读取发布快照，Neo4j kg_v2 作为未启用发布版时的配置基线保留，不覆盖其数据库内容。

## 文件位置

| 文件 | 职责 |
|---|---|
| `agent/core/graph/project_workbench.py` | 项目审核状态、版本筛选、快照、启用与回退、历史记录 |
| `app/router/project_workbench.py` | 鉴权与请求校验，`/api/knowledge-workbench` 接口 |
| `front/clinical_cds/src/api/candidateGraph.ts` | 工作区接口与类型 |
| `front/clinical_cds/src/components/knowledge-graph/CandidateGraphPanel.vue` | 知识浏览、审核操作和版本页 |
| `front/clinical_cds/src/components/knowledge-graph/KnowledgeGraphPanel.vue`、`EntityDetail.vue` | 原图谱页面去掉专家待审措辞，保留来源核对状态 |
| `logs/knowledge-workbench.sqlite3` | 本机项目审核、版本快照和操作历史，已由 logs 忽略规则排除提交 |
| `app/test/test_project_workbench.py` | 新增 8 项工作流与接口回归 |
| `scripts/verify_project_workbench.py` | 真实本机工作区接口验收 |

SQLite 事务和页面修订号避免并发覆盖。发布版本绑定来源及审核结果指纹，重复内容不会生成新版本；启用检查版本快照完整性。原始冻结台账和现有图谱数据保持不变。

## 验证

后端全量 192 项测试通过；前端类型检查及构建通过。新增测试验证退回、恢复通过、禁止批准无依据项、版本持久化、两版切换与回退、快照不可变、篡改拒绝、鉴权、输入边界和过期提交。

浏览器已走通首版发布、启用、已启用版本查询、回退、条目退回及重新通过；重启后记录保留，首版已重新启用。本机最终 18 项接口验收全部通过，当前版本和接口计数见[本机验收记录](PROJECT-WORKBENCH-ACCEPTANCE.json)，界面见[截图](PROJECT-WORKBENCH.png)。构建有既有包体积和依赖注释提示，后端有既有 LangChain 弃用提示，不影响本轮检查通过。

前后端管理命令保持不变，先启动 Docker Desktop 后执行：

```powershell
cd D:\PsyConsult
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 infra
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local-app.ps1 start
```

本机状态保存在 `logs/knowledge-workbench.sqlite3`。备份时先停止前后端，再复制该文件；请勿清理它，否则审核操作和版本历史将丢失。源资料、数据库及密钥仍按既有复现说明管理。
