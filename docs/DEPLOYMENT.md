# 知助：开发和部署说明

当前为 M4 智能工作流版本，包含受限工具助手、经确认建单、执行追踪和 FAQ 审核发布。使用与验收见 M4_ACCEPTANCE.md，知识管理见 M3_ACCEPTANCE.md，工单流程见 M2_ACCEPTANCE.md。M5 仍按 PROJECT_PLAN.md 实施，尚未通过正式公网验收。

当前版本 2.6.1 使用常规账号登录，已移除公开凭据与体验指引接口。数据库升级至 0007，支持产品授权、历史资源退役与助手回复关联。部署使用 DEMO_MODE=false；四个业务账号使用独立随机密码，凭据只保存在被忽略的私有存储中。账号与资料流程见 [业务使用说明](BUSINESS_GUIDE.md)。

## 本地启动

推荐 Python 3.12 和 Node.js 24。保留失效的旧 backend/.venv，新环境使用 backend/.venv-dev。

在项目根目录执行，激活环境后以下 python 均指向新环境：

```powershell
python -m venv backend/.venv-dev
backend/.venv-dev/Scripts/Activate.ps1
python -m pip install -r backend/requirements-dev.lock
# 仅当 .env 不存在时复制 .env.example；已有配置请保留
cd backend
# 在三个后端终端均设置相同环境（端口不要与 API 冲突）
$env:CHROMA_HOST='127.0.0.1'
$env:CHROMA_PORT='8001'
# 终端一启动 Chroma：chroma run --path ../chroma_db --host 127.0.0.1 --port 8001
python manage.py migrate
# 首次升级登记旧向量资料；保留内容，不会虚构遗失的原件
python manage.py adopt-legacy
python manage.py create-admin --username admin
# 终端二启动 API
python run.py
# 终端三启动后台进程（同一虚拟环境与配置）
# python worker.py
```

管理员密码通过交互输入，至少 12 位。系统不内置默认账号或密码。管理员登录后可在“账号设置”创建客服和用户账号。

另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问 http://127.0.0.1:5173。所有业务 API 需要登录，Cookie 不向 JavaScript 暴露。写请求额外发送 `X-CSRF-Protection: 1`，并校验存在的 Origin；前端已统一处理。

API Key、模型地址和模型名在服务端 .env 配置。前端不存储或覆盖这些配置。模型首次使用可能下载；仅验证账号与数据库时可以设置 WARMUP_ON_STARTUP=false。/api/health 检查进程存活，/api/ready 仅检查业务数据库连接和用户表可读，不代表嵌入模型或远程 LLM 已就绪。

## 旧聊天记录迁移

升级不会自动向新用户公开原 chat_history.json。确认归属后执行：

```powershell
cd backend
python manage.py import-sessions --username admin --file ../chat_history.json
```

导入前验证全部输入，已有同名会话跳过，原 JSON 保留。数据库事务按单个会话提交；若中途运行失败，重跑会继续导入尚不存在的会话。导入前备份数据库；不要在用户正编辑同名会话时导入。M3 的 adopt-legacy 会将现有 Chroma 资料登记为已发布修订，以维持原有可检索性；没有保留原件的旧资料不提供原件下载。后续新上传默认待处理、待审核发布。

## 容器验证

Compose 使用独立持久化卷，不会自动挂载仓库原有向量库。需要重新导入产品资料。PostgreSQL、Chroma 和 API 不向主机公开端口，Web 默认仅绑定 127.0.0.1:8080。

```powershell
# 首次运行：从模板生成配置，随机设置数据库密码，沿用已有项目模型配置
# 已存在的配置不会被覆盖
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-deploy.ps1
docker compose --env-file .env.deploy.local config --quiet
docker compose --env-file .env.deploy.local up --build -d
docker compose --env-file .env.deploy.local exec api python manage.py create-admin --username admin
docker compose --env-file .env.deploy.local ps
```

API 启动时执行迁移、adopt-legacy 及 unify-assistant-history，随后启动单个 Uvicorn 进程。unify-assistant-history 只把尚未关联的真实助手记录补入统一对话历史，重复运行会跳过已处理的记录，退役记录不会恢复。数据库和 Chroma 健康后启动 API，API readiness 通过后启动 Web 和后台 worker。向量卷只挂载到 Chroma，API 与 worker 通过 HTTP 访问，避免多个本地 PersistentClient 进程共用数据目录。原始文件保存在 document_storage 卷，模型保存在 model_cache 卷。首次模型下载失败会记录日志，应检查缓存与网络。

worker 通过数据库心跳检测健康；文档页面超过 60 秒无心跳时显示离线提示。运行 `docker compose --env-file .env.deploy.local logs -f worker` 查看失败原因。

API 仅在 Compose 私有网络开放，信任该网络中的代理转发头。Nginx 覆盖客户端传入的 X-Forwarded-For；不要直接暴露该 API 容器端口。增加其他代理时重新配置受信任地址和转发规则。

如果报 `couldn't find env file`，先运行上述 init-deploy.ps1，再重试 Compose 命令。`.env.deploy.local` 是本机配置，不随仓库分发，已加入 Git 和 Docker 构建上下文的忽略规则。若原项目尚未配置 API Key，编辑该文件补齐后即可启用远程模型问答；仅构建镜像不需要 API Key。

默认端口 8080 被占用时，可在首次生成配置时追加 `-WebPort 8088`。配置已经存在时，直接修改 `.env.deploy.local` 中的 WEB_PORT，并同步 CORS_ORIGINS 中的端口。本工作区当前使用 8088，访问地址为 http://127.0.0.1:8088。

## Docker 代理连接失败排查

如果拉取镜像时报 `127.0.0.1:7890 ... connection refused`，表示 Docker 正在使用本地代理，但对应端口当时不可连接。先启动代理程序并检查实际 HTTP 或混合代理端口：

```powershell
Get-NetTCPConnection -LocalPort 7890 -State Listen -ErrorAction SilentlyContinue
curl.exe --proxy http://127.0.0.1:7890 --connect-timeout 10 --max-time 20 --output NUL --silent --show-error --write-out '%{http_code}' https://registry-1.docker.io/v2/
docker pull python:3.12-slim
```

代理端口必须与程序设置一致。访问 Registry `/v2/` 返回 401 说明已经收到服务端鉴权响应，可以继续用 `docker pull` 验证完整下载链路。

打开 Docker Desktop → Settings → Resources → Proxies。如果使用 Windows 系统代理，Docker Desktop proxy 选择 System proxy；若界面提供 Containers proxy，将其设为 Same as host proxy，或配置同一个有效代理。手动配置时填写代理程序实际的 HTTP 代理地址，例如 `http://127.0.0.1:7890`。应用设置后重试构建；仍使用旧配置时再安排重启 Docker Desktop。

如果网络能够直连 Docker Hub，也可以在 Docker Desktop 中选择 No proxy。Docker Desktop 不使用 daemon.json 中的代理设置，应通过其设置界面配置。[Docker 代理设置](https://docs.docker.com/desktop/settings-and-maintenance/settings/#proxies)，[daemon.json 适用范围](https://docs.docker.com/engine/daemon/proxy/)。

代理开启并且基础镜像拉取成功后，使用已经准备好的本地部署配置重试：

```powershell
docker compose --env-file .env.deploy.local build
```

## 生产环境配置

正式部署前完成计划书剩余的 M5。至少设置 APP_ENV=production、COOKIE_SECURE=true、PostgreSQL DATABASE_URL 和精确的 HTTPS CORS_ORIGINS。生产模式会拒绝非 PostgreSQL 数据库和非 Secure Cookie 配置，同时关闭公开 API 文档。

当前 Compose 提供 HTTP 内网入口，需要由 HTTPS 网关或入口代理转发到回环地址。只有 HTTPS 访问才能携带 Secure Cookie。API Key、数据库密码通过运行环境或秘密管理服务注入；不提交 .env、数据库或模型缓存。

正式域名、服务器、TLS 证书与云资源配置在实际部署时确定；本仓库不会自行购买资源或发布公网服务。

## 验证

```powershell
cd backend
python -m pytest -q
python -m ruff check app manage.py worker.py tests migrations evals
python -m alembic check
cd ../frontend
npm test
npm run build
```

PostgreSQL 回归使用一个专用的可清空测试库，切勿指向业务数据库：

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://support:testpassword@127.0.0.1:5432/support_test'
python -m pytest -q
Remove-Item Env:TEST_DATABASE_URL
```

测试会清空 TEST_DATABASE_URL 中业务表的数据，因此强制要求数据库名称以 _test 结尾。CI 同时运行 SQLite 和 PostgreSQL 用例；测试中的模型输出使用替身，不消耗 API 额度，不代表真实模型端到端效果。

依赖升级时，在 Python 3.12 约束下重新生成跨平台锁文件，再跑上述检查：

```powershell
uv pip compile requirements.txt --python-version 3.12 --universal --no-header --no-annotate -o requirements.lock
uv pip compile requirements-dev.txt --constraint requirements.lock --python-version 3.12 --universal --no-header --no-annotate -o requirements-dev.lock
```

## 备份和变更

生产发布前使用 pg_dump 创建 PostgreSQL 备份，保存当前镜像标签与 Alembic 版本，同时暂停 worker、停止向量写入并备份 Chroma 数据卷与 document_storage 原件卷。恢复时将关系数据、向量数据及原件恢复到同一时点。M5 需实际演练并记录恢复耗时和数据核对结果。禁止对实际部署使用 `docker compose down -v`，该命令会删除业务数据卷。

数据库变更先在测试库运行迁移及回归，再升级生产。回滚优先恢复上一版本镜像；涉及不兼容 schema 时按已验证的迁移或备份方案处理，不对生产库直接执行未经演练的降级命令。


## 前端发布与旧页面恢复

HTML 导航和 `index.html` 使用 `Cache-Control: no-store`，构建产物中带内容哈希的 `/assets/` 文件使用长期不可变缓存。不存在的资源必须返回 404，并带 `no-store`，不能通过 SPA 回退返回首页；否则浏览器会把 HTML 当作 JS/CSS 并报 MIME 错误。

每次构建在 HTML 中写入独立版本标识。页面恢复可见时检查新版本并提示用户更新；路由资源加载失败时，只有确认服务端已换版本才自动重载目标路由，同一目标版本在一分钟内最多自动重载一次。离线、版本未变化或浏览器存储受限时提供手动重新加载入口，避免刷新循环。页面已有的进行中操作不会仅因检查到更新而被自动丢弃。

首次从不含此机制的旧页面升级，需按 Ctrl+F5 强制刷新一次。旧登录凭据已失效时重新登录即可，无需再次初始化账号或知识资料。`ERR_NETWORK_IO_SUSPENDED` 表示浏览器暂停了网络任务，恢复网络或重新打开页面后重试。

账号退出或切换时清空资料状态并使旧请求失效；上一个登录周期迟到的 401 不会让新账号退出，旧资料响应也不能覆盖新账号的资料。`npm test` 覆盖版本恢复与刷新限制，CI 在构建前执行这些检查。
