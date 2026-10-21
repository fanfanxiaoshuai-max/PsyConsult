# 从 GitHub 部署融合版

仓库保存代码、知识资料、评估用例、依赖清单和配置示例。真实密钥、个人账号、病例、上传文件、运行日志及数据库卷不随 Git 上传；原机的完整保全包继续单独保管。

## Windows 首次安装

准备 Git、Python 3.12、Node.js（满足前端 package.json 的 engines 要求）及 Docker Desktop，启动 Docker Desktop。在新目录操作，不覆盖现有系统。

```powershell
git clone https://github.com/fanfanxiaoshuai-max/PsyConsult.git
cd PsyConsult
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r agent/requirements-fusion.lock
npm.cmd --prefix front/clinical_cds ci
Copy-Item agent/.env.fusion.example agent/.env
```

编辑 `agent/.env`，填写自己的 `DASHSCOPE_API_KEY`，并为 `API_AUTH_TOKEN` 设置自己的专业入口令牌；本地数据库演示密码应与 Compose 配置一致。不要提交填写后的文件。

```powershell
.\scripts\run.ps1 infra
.\scripts\local-app.ps1 start
.\scripts\local-app.ps1 status
```

打开 http://127.0.0.1:5273/ 。个人入口自行创建账号，专业入口填写刚配置的访问令牌。首次安装的账号和业务数据为空。OCR、语音及模型问答还取决于本机依赖和模型服务配置。

## 迁移已有数据

Git 克隆不会还原本机数据库。需要延续已有数据时，另行安全迁移 `data/platform/`、知识工作台数据库及 Redis/Milvus/Neo4j 卷，并核对知识索引和启用版本。完整保全包不应上传仓库。操作细节见 [融合使用说明](FUSION-USAGE.md)。

## 检查与停止

```powershell
.\scripts\run.ps1 offline-test
npm.cmd --prefix front/clinical_cds run build
.\scripts\local-app.ps1 stop
.\scripts\run.ps1 stop-infra
```

这些是新环境安装步骤，不能替代在目标电脑执行一次完整部署验收。系统为辅助原型，现有验证范围与限制见 [融合验收](FUSION-ACCEPTANCE.md)及[公众来源审查](COMMUNITY-SOURCE-REVIEW.md)。
