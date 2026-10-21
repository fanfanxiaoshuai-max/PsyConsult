# PsyConsult 统一平台融合副本

后续更新：[首页文案、公众来源核对及检索第二轮验收](docs/COMMUNITY-SOURCE-REVIEW.md)。

本机入口：http://127.0.0.1:5273/ 。个人健康空间、专业工作台、知识管理中心共用一个产品入口，通过用户明确授权连接资料与病例。原专业工作台继续保留。

**开发请使用 `D:\PsyConsult-Fusion`。原目录 `D:\PsyConsult` 已冻结，不要在原目录启动融合代码或执行迁移。**

完整保全包：`D:\PsyConsult-Preserved\20261021-pre-fusion-01`，包含原工作区、未提交内容、配置、知识文件、本地数据库、数据库卷导出、镜像及恢复说明。包内含凭据与本地业务数据，只在本机保管。

启动与使用见 [融合使用说明](docs/FUSION-USAGE.md)，实现边界见 [实施方案](docs/FUSION-PLAN.md)，已执行的检查及未完成项见 [验收报告](docs/FUSION-ACCEPTANCE.md)。下方保留原系统说明；其中 5000/5173 为原版端口，融合副本使用 5100/5273。

---

# PsyConsult — 精神科临床决策支持系统原型

知识审核与版本管理入口：<http://127.0.0.1:5173/#candidate>。支持项目内部审核、知识版本发布、启用与回退；启用版本同步用于知识浏览和新一轮问答。详见[操作说明](docs/PROJECT-WORKBENCH.md)及[版本联动与验收](docs/KNOWLEDGE-VERSION-LINK.md)。

基于 **LangGraph 多智能体**的临床决策支持系统（Clinical CDS）：Vue 3 前端 + FastAPI 后端，通过 SSE 流式返回鉴别诊断、治疗推荐与药物相互作用审查建议。会话级状态由 **LangGraph Checkpoint + Redis** 管理，支持多轮临床问答的状态恢复与连续推理。

## 架构

```
Vue 3 前端 (Vite :5173)
  → POST /api/chat {query, session_id}          Bearer Token + X-User-Id 鉴权
  → 语义缓存 (Milvus qa_semantic_cache)          命中直接返回，且该轮仍写入 checkpoint
  → LangGraph Agent 图 (session_id = thread_id)
       START → history_compression → orchestrator（意图路由）
                 ├─→ differential_diagnosis → treatment_recommend → drug_interaction → END
                 ├─→ treatment_recommend     → drug_interaction → END
                 └─→ drug_interaction        → END
  → SSE 流式响应逐节点推送
```

**三层结构**

| 目录 | 说明 |
|---|---|
| `agent/` | LangGraph 多智能体推理核心：领域 Agent、StateGraph 编排、Redis Checkpoint、Milvus 长期记忆、Neo4j 知识图谱工具 |
| `app/` | FastAPI 接口层：鉴权、输入校验、语义缓存、SSE 流式响应 |
| `front/clinical_cds/` | Vue 3 + TypeScript 单页应用（三栏工作台） |
| `docker/` | Redis（redis-stack）、Milvus、Neo4j、MySQL 本地基础服务 |
| `mock_data/` | 临床指南、ICD-11 诊断标准、药物资料 |
| `learn/` | 中文学习文档（01–15：架构走读、实测、踩坑、面试准备） |

## 记忆体系

- **会话级状态**：LangGraph Checkpoint + Redis（`session_id` 作 `thread_id`），保存病例信息、中间推理结果与工具调用上下文；TTL 24 小时读时续期。
- **上下文长度控制**：消息超过 16 条时自动压缩——保留最近 8 条，其余由 LLM 摘要为一条「历史会话摘要」（短期窗口 + 历史摘要）。
- **长期记忆**：每 5 轮从 checkpoint 历史提取临床要点（主诉/诊断/用药/量表分数）向量化存入 Milvus，跨会话按语义检索注入上下文。
- **优雅降级**：Redis / Milvus 不可用时图退化为无状态运行、记忆与缓存自动跳过，均不阻塞推理。

## 快速开始

```bash
# 1. 基础服务（redis-stack 自带 RediSearch，Checkpoint 依赖它）
cd docker && docker compose up -d

# 2. 配置密钥（最小配置仅需一项）
#    agent/.env:
#    DASHSCOPE_API_KEY=sk-xxx
pip install -r agent/requirements.txt

# 3. 启动后端（http://127.0.0.1:5000）
python -m uvicorn app.app_main:app --host 0.0.0.0 --port 5000

# 4. 启动前端（http://localhost:5173）
cd front/clinical_cds && npm install && npm run dev
```

`agent/.env` 完整可选项见 `CLAUDE.md` 与 `learn/02-tech-stack/`；Redis/Milvus/Neo4j 未配置时均有默认值，与 `docker/docker-compose.yml` 对齐。

## 常用命令

```bash
python -m pytest -q                                   # 后端测试（app/test）
python -m compileall -q agent app                     # 语法检查
cd agent && python main.py --query "患者近两周情绪低落..."   # CLI 单次问诊
cd front/clinical_cds && npm run type-check && npm run build  # 前端验证门禁
```

## 安全说明

知识图谱的399项修订现均有结构化处置，见[最新报告](docs/KNOWLEDGE-GRAPH-V3-STRUCTURED-02.md)及[修改前后对照](docs/KNOWLEDGE-GRAPH-V3-STRUCTURED-ALL.html)。候选版尚未发布，新增记录不进入推理；原文对照不等于临床专家审核。

- `agent/.env` 含密钥，已被 gitignore，切勿提交；文档示例一律使用占位符。
- `API_AUTH_TOKEN` 配置后强制 Bearer Token 校验；`X-User-Id` 需匹配 `^[A-Za-z0-9_.:-]{1,128}$`。
- 前端所有 Markdown 渲染前经 DOMPurify 净化。
- 本系统为原型，输出仅供临床参考，不构成诊疗依据；请勿存入真实患者数据。
