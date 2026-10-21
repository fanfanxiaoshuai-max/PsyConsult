# PsyConsult 本机复现记录与操作说明

更新时间：2026-10-19（北京时间）。当前状态：本机复现验收通过。模型、向量入库、三条推理入口、浏览器问答、缓存、多轮状态、长期记忆、历史压缩、CLI、启动降级及数据库重启保留均已验证。前后端和三个数据库正在运行；MCP 扩展仍按约定不在本阶段范围。

## 图谱第二轮补充（2026-10-19）

当前启用 `kg_v2`：五种药物共30条条件性原文核对记录（24条中国说明书，6条美国标签补充），临床专家审核尚待完成。376条旧版关系保留查阅，默认不进入v2推理；原文未逐项核实的实体属性不作为已验证事实传给Agent。药物审查改为按证据字段生成，避免补造来源外的监测频率。后端现为73项测试。实施、边界和版本回退见 [KNOWLEDGE-GRAPH-V2.md](KNOWLEDGE-GRAPH-V2.md)。下文为此前复现及第一轮的历史记录。

## 图谱增强补充（2026-10-19）

第一轮知识图谱增强已完成，当时启用 `kg_v1`：214个实体、376条有效关系、643条来源记录；原图谱单独保留。后端测试现为49项。新增页面、检索、证据与回退说明见 [KNOWLEDGE-GRAPH-V1.md](KNOWLEDGE-GRAPH-V1.md)。下文214节点/423关系等结果为首次复现时的旧图谱基线。

## 已对齐的目标

在 Windows 本机运行前后端，在 Docker 中运行 Redis Stack、Milvus、Neo4j；复现当前已接通的推理、检索、图谱、会话、压缩、长期记忆和缓存。MCP 接入属于第二阶段。

- 原仓库：https://github.com/xingdayup/PsyConsult
- 上游分支：`codex/hardening-baseline`
- 基准提交：`3d2fd3d74fbf245f451805f4aa4c2e5b5ac2682e`
- 本地目录：`D:\PsyConsult`
- 当前改动保留在工作区，未提交或推送。

## 已完成并实测

| 项目 | 结果 |
|---|---|
| 仓库下载、提交核对 | 通过 |
| 项目独立 Python | 3.12.15，`.venv`；原系统 3.11 不变 |
| Node / npm | 24.15.0 / 11.12.1 |
| WSL | 2.7.13.0，Linux 内核 6.18.33.2-2；已安装并通过版本检查 |
| Docker Desktop | 4.95.0，安装器退出码0 |
| Docker CLI / Compose | 29.8.2 / v5.6.0，通过版本检查与复现 Compose 配置校验 |
| Windows 功能 | WSL 和 VirtualMachinePlatform 已启用并重启生效 |
| 重启后主机检查 | Docker Linux Engine 29.8.2 可连接 |
| Redis Checkpoint 集成验证 | 写入、重连、恢复与续写通过，实测 TTL 86392–86398 秒 |
| Milvus 服务 | 2.4.0 启动正常，Python 客户端连接通过 |
| Neo4j 示例图谱 | 5.26.32；实际导入214个节点、423条关系，与静态预期一致 |
| 容器重启保留验证 | 三个容器重启后，先前 Checkpoint 与图谱计数保持一致 |
| 前端依赖 | 根据上游 `package-lock.json` 执行 `npm ci` |
| 前端类型检查和构建 | 通过；有非阻断的第三方注释和大文件警告 |
| 后端离线测试 | 19 项通过（原有11项，Checkpoint回归3项，缓存回归5项） |
| Python 语法检查 | 通过 |
| 依赖一致性检查 | `uv pip check` 通过 |
| 图谱数据静态检查 | 4 个 JSON，240 条节点记录、209 个不同 ID、389 条关系记录；13 条关系缺少端点 |
| 密钥文件 | 已配置并通过真实调用验证；`agent/.env` 被 Git 忽略，文档和前端不含模型密钥 |
| 模型接口 | `qwen-plus` 有效；`text-embedding-v2` 返回1536维 |
| 向量知识库 | 7份 Markdown、50个片段入库；检索工具返回资料和来源 |
| 真实 SSE 与路由 | 诊断→治疗→药审、治疗→药审、直接药审三条入口通过 |
| 缓存 | 重复问题立即命中约0.4秒；相近措辞实测 L1_SEMANTIC 命中 |
| 长期记忆 | 第5轮后台提取并写入，独立 MemoryManager 按同用户检索成功 |
| 历史压缩 | 独立会话预置20条合成历史后，真实请求产生历史摘要 |
| CLI | `agent/main.py --query ...` 真实模拟问答退出码0 |
| 故障降级 | 在独立进程连接故意关闭的端口，Redis无状态图与Milvus记忆/缓存跳过通过 |
| 浏览器 | 已从工作台提交虚构病例并观察“分析完成”；截图在 `docs/UI-VERIFICATION.png` |

离线测试使用模拟响应；真实集成结果另见 `docs/E2E-VERIFICATION.json`、`docs/CACHE-VERIFICATION.json` 和 `docs/INFRASTRUCTURE-VERIFICATION.json`。其中三条正常路由耗时约59、33、14秒，缓存命中约0.4秒；耗时受网络与模型负载影响，不是性能保证。依赖锁定文件记录的本机环境已通过上述验证。

## 当前如何使用

直接访问 `http://127.0.0.1:5173`，前后端已在后台运行。

```powershell
Set-Location D:\PsyConsult
.\scripts\local-app.ps1 status
# 只停止本脚本管理的前后端；数据库保留运行
.\scripts\local-app.ps1 stop
# 以后需要重新启动时执行；不要在已有服务占用端口时重复启动
.\scripts\local-app.ps1 start
```

后台日志：`logs/backend.log`、`logs/backend-process.out.log`、`logs/backend-process.err.log`、`logs/frontend-process.out.log`。启动脚本设置UTF-8并绕过localhost代理，避免中文日志乱码和本地HTTP被代理转发。

### 1. 密钥已配置（以下仅供以后重建或轮换）

1. 按阿里云官方说明开通百炼并创建 API Key，选择华北2（北京），与项目默认端点对应。
2. 在本机编辑 `D:\PsyConsult\agent\.env`，只将 `DASHSCOPE_API_KEY=` 后面的空值换为实际密钥并保存。
3. 不要把实际密钥写入文档、前端或版本库。当前密钥已在本地保存并验证，无需再次填写。

官方说明：https://help.aliyun.cn/zh/model-studio/get-api-key

地域说明：https://help.aliyun.com/zh/model-studio/regions

默认模型为 `qwen-plus`，向量模型为 `text-embedding-v2`，当前均已验证可用。真实模型测试、向量入库和问答会产生 API 调用；具体额度和价格以账号控制台为准。
### 2. 基础设施已就绪（无需再安装或重启）

已通过 Windows UAC 获取管理员授权并完成 WSL 2.7.13、WSL/虚拟机平台功能和 Docker Desktop 4.95.0 安装。用户随后已重启；Docker Linux Engine 已实际连接成功，Redis、Milvus、Neo4j 三个容器保持运行。

以后开机需要运行项目时，从开始菜单启动 Docker Desktop，等待 Docker Engine 就绪。可在项目根目录检查：

```powershell
Set-Location D:\PsyConsult
.\scripts\check-host.ps1
```

也可分别检查：

```powershell
wsl --version
```

使用 WSL 2 后端。首次启动如有必要的界面确认，请按界面完成。

官方安装说明：https://docs.docker.com/desktop/setup/install/windows-install/

```powershell
docker --version
docker compose version
docker info
```

`docker info` 必须能连接服务端；重启后已验证成功。本机可见内存约126 GiB、D盘空闲约2.17 TiB，容量足够本地复现。Codex 沙箱内可能显示 Docker 命名管道权限不足，在常规本机权限下已验证可连接；无需因此修改 Docker 权限。

安装日志在 `.tools/install-prereqs.log`，结果在 `.tools/install-prereqs.json`（两个安装器退出码均为0，`rebootRequired=true`）。备用本地安装器因检测到原安装器正在运行而退出，没有执行重复安装。官方安装包已做 SHA256 校验，备用 Docker EXE 的数字签名也通过验证。

## 后续启动顺序

所有命令在项目根目录的 PowerShell 执行。若脚本执行策略阻止运行，可仅对当前 PowerShell 进程执行 `Set-ExecutionPolicy -Scope Process Bypass`。

```powershell
Set-Location D:\PsyConsult
# 新电脑重建依赖时使用；当前电脑已完成安装，无需重复。
.\scripts\setup.ps1

# Docker Engine 就绪后启动资料服务
.\scripts\run.ps1 infra
.\scripts\run.ps1 status

# 导入现有图谱，无模型费用；报告后跳过已知的13条缺端点关系
.\.venv\Scripts\python.exe scripts\import_graph.py

# 配置真实密钥后，验证聊天与1536维向量接口
.\.venv\Scripts\python.exe scripts\check_models.py

# 初始化示例 Markdown 检索集合，会调用 Embedding API
# 注意：上游脚本会覆盖 cloud_product_docs，不要用于存有其他资料的 Milvus。
.\.venv\Scripts\python.exe agent\test\milvus_rag.py

# 检查数据库真实能力（写入一条带过期时间的合成 checkpoint）
.\.venv\Scripts\python.exe scripts\check_services.py

# 尚无模型密钥时，只验基础设施；允许模型相关集合尚未创建
.\.venv\Scripts\python.exe scripts\check_services.py --infra-only

# 重启本项目三个数据库容器，并验证此前保存的状态及图谱仍存在
.\.venv\Scripts\python.exe scripts\check_persistence.py
```

在两个终端分别启动后端和前端：

```powershell
# 终端1
Set-Location D:\PsyConsult
.\scripts\run.ps1 backend
```

```powershell
# 终端2
Set-Location D:\PsyConsult
.\scripts\run.ps1 frontend
```

访问 `http://127.0.0.1:5173`。后端为 `http://127.0.0.1:5000`，接口文档在 `/docs`。两端已统一开发用 Token `local-dev-token`，它是本地访问令牌，与模型 API Key 不同。

前后端各自在对应终端按 Ctrl+C 停止。停止资料服务且保留数据：

```powershell
.\scripts\run.ps1 stop-infra
```

使用独立的 `docker/compose.repro.yml`，请勿与原 Compose 同时启动，以免端口冲突。数据库只绑定本机回环地址，数据保存在命名卷；没有添加删卷命令。MySQL 不在现有聊天主链路，因此本地复现配置不启动它。三项镜像已固定为实际拉取并验证的 digest，避免后续标签漂移。

## 本地修复与新增资料

- `agent/constraints-repro.txt`：限制 MCP <2、pymilvus <3、langchain-milvus <0.4。首次无约束安装的 MCP 2.3.0 与适配器在导入 `RequestContext` 时失败；调整后离线测试通过。
- `agent/requirements-repro.lock`：已安装依赖的精确版本快照；当前环境已通过离线测试和数据库、模型集成验证。
- `agent/config/settings.py`：固定配置文件相对于源码的位置，避免从不同工作目录启动时找错 `.env`。
- `agent/core/workflow/checkpointer.py`：将秒转换为依赖所要求的分钟（原值相当于60天而不是24小时）；使用依赖实际提供的异步上下文清理接口，初始化失败时也清理连接。
- `app/infra/cache.py`：真实联调发现，默认有界一致性不能保证刚写入的缓存立即可见，现对精确和向量缓存读取使用强一致性；COSINE 返回相似度，先转换为 `1 - similarity` 再应用距离0.08阈值。增加5项回归测试，并通过真实精确/语义命中验证。
- `front/clinical_cds/.env.local`：后端地址由5001改为5000，添加匹配的本地开发 Token。
- `scripts/import_graph.py`：导入现有 JSON，不重新调用 LLM、不清空图谱；先导入所有节点再导入有效关系。运行 `--dry-run` 可只审计数据；`--strict` 会在任何写入前拒绝缺端点的数据。
- `graph-data-audit.json`：13条无对应节点关系的完整清单。没有凭空补全节点或改写源资料。

静态数据中的同标签、同ID节点会按 `MERGE` 合并。5个名称出现在不同标签下，按原脚本语义仍保留为不同节点，且只按ID匹配关系会命中多个节点。因此240条节点记录、209个不同ID最终得到214个节点；389条关系记录排除13条缺端点关系，再按原匹配方式展开和去重，得到423条关系。实际导入结果与静态预期一致，没有改写源医学资料。这些跨标签歧义仍属于示例数据局限。

## 完整验收清单

以下均不能仅以“页面有回答”判定通过。验证期间只使用虚构病例。

| 功能 | 验收证据 | 当前状态 |
|---|---|---|
| 模型 | 聊天有响应，Embedding 返回1536维 | 通过 |
| Redis | 真实 checkpoint 写入、重连、恢复、续写、TTL 检查 | 通过 |
| Milvus RAG | 文档入库数量、查询返回内容及来源 | 通过：50个片段，实际工具检索通过 |
| Neo4j | 有效节点与关系入库、查询命中 | 通过：图谱工具和Agent工具事件均已验证 |
| SSE 与前端 | 真实流从 accepted 到 done，页面显示各阶段 | 通过：浏览器展示分析完成 |
| 路由与三个 Agent | 分别验证诊断、治疗、药物审查入口及工具事件 | 通过 |
| 多轮与重启恢复 | 固定 session_id，状态连续并可恢复 | 通过：五轮含缓存轮均写入；独立连接和容器重启保留通过 |
| 历史压缩 | 超过16条消息，产生摘要 | 通过：20条预置合成历史触发真实LLM压缩；没有用20轮真实问答冒充此测试 |
| 长期记忆 | 每5轮触发提取，写入 Milvus，独立实例按同用户检索命中 | 通过 |
| 缓存 | 相同问题命中、相近问题观察阈值、缓存轮写入 checkpoint | 通过 |
| 降级 | 独立初始化进程连接故意关闭的端口，验证跳过 | 通过；不代表已实现运行中所有故障的自动切换 |
| 可重复运行 | 重启前后端和容器，检查资料、状态恢复 | 通过：后台进程停止启动、数据库容器重启保留均已验证 |

离线检查可重复执行：

```powershell
.\scripts\run.ps1 offline-test
.\.venv\Scripts\python.exe -m compileall -q agent app scripts
.\.venv\Scripts\python.exe scripts\import_graph.py --dry-run
```

当前系统仍是上游原型，知识数据也是仓库示例。完整复现指功能链路可运行且可验证，不代表临床有效性获得验证，也不保证在线模型输出逐字一致。
