# 融合副本使用说明

## 启动和停止

在 PowerShell 中：

```powershell
cd D:\PsyConsult-Fusion
.\scripts\run.ps1 infra
.\scripts\local-app.ps1 start
.\scripts\local-app.ps1 status
```

浏览器打开 http://127.0.0.1:5273/ 。后端仅监听本机 5100，前端 5273。已有后台进程时不要重复 start；用 `.\scripts\local-app.ps1 stop` 停止本副本前后端，用 `.\scripts\run.ps1 stop-infra` 停止融合数据库。Node.js 需在 PATH 中；Python 使用本副本 `.venv`，不使用旧文档中 E 盘路径。

基础设施独立使用 Redis 6380、Milvus 19531/9092、Neo4j 7475/7688，Compose 项目为 psyconsult-fusion。不要改用原版 Compose 启动命令，避免误操作冻结实例。原版容器保持停止，卷仍保留。

## 登录及实际流程

个人入口可创建账号，注册只获得个人权限。专业人员通过“专业人员入口”输入原有配置中的访问令牌；绑定身份与 reader/reviewer/admin 角色沿用原 API_AUTH_TOKEN/API_AUTH_USERS 设置。令牌仅在本机配置文件中查看，不要粘贴到聊天、提交到 Git 或写进前端环境变量。正式运行库没有预置验收账号。

1. 个人可科普问答、自评、记笔记、上传报告。问答保存默认关闭；需要授权会话时先显式保存。
2. 报告上传后先核对识别文字，再点击生成解读。文字识别在本地，自动解读和问答调用已配置的模型服务；真实资料使用前应明确该服务的数据处理安排。
3. 分享时选择具体资料、专业接收人和有效期，确认固定快照。以后新增或修改的内容不会自动追加到授权。
4. 专业人员从授权收件箱显式建立病例；核对后保存专业确认记录，勾选回传时才向个人显示。临床助手自动回答保留未确认标记。
5. 个人可撤销授权。专业端随即失去该授权资料访问权；已有专业确认记录与关联问答按病例保留。
6. 专业工作台可切回原临时问答。知识管理继续使用原审核、发布、启用及回退流程；公众知识另保留来源及草稿状态。

语音先转写进入输入框，用户核对后发送；使用麦克风需要浏览器许可。音频接口不持久化录音。也可不使用语音而直接输入。

## 数据与恢复

新账号、授权、病例等位于 `data/platform/platform.sqlite3`，上传位于 `data/platform/uploads`。原知识工作台数据库仍为 `logs/knowledge-workbench.sqlite3`。运行时配置为 `agent/.env` 与前端 `.env.local`，数据与秘密均已忽略提交。上线或迁移前还需单独备份新产生的数据。

`.tools/ui-acceptance-data` 是独立的虚构验收数据库，`.tools/runtime-acceptance` 与 `.tools/document-probes` 是实测产物。正常运行使用 `data/platform`，不要为正常启动设置 `PSYCONSULT_PLATFORM_DATA` 到验收目录。

恢复原版时先阅读 `D:\PsyConsult-Preserved\20261021-pre-fusion-01\README.md`，再使用同目录 `RESTORE.ps1`，恢复到新的空目录及新卷，不覆盖融合副本。冷备文件已逐文件校验，隔离数据库恢复已核对；恢复脚本本身做过语法检查，未再次独立完整执行一遍。Redis 冷备中的原绝对过期时间可能已到期，另保存逻辑 DUMP/相对 TTL 导出供核对恢复。

保全覆盖项目及盘点出的本地服务，不是整台 Windows 的磁盘镜像。项目 `.tools` 内浏览器资料已纳入；原外部浏览器的独立 localStorage 未导出，也没有清除。原版 5173 和融合版 5273 为不同来源，原浏览器诊疗草稿不会自动迁入。

## 后续开发检查

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd front\clinical_cds
npm.cmd run test:platform
npm.cmd run test:chat
npm.cmd run type-check
npm.cmd run build
```

公众来源评估：在根目录执行 `.\.venv\Scripts\python.exe scripts/evaluate_community_retrieval.py --help` 查看参数。当前存在未命中用例，完整通过的退出门禁不会成功，不应隐藏这些缺口。
