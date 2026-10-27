# 知助 · 智能客服与知识协作平台

**ZhiZhu Support** 是面向软件产品团队的智能应用，把产品资料、流式 AI 对话、人工工单和 FAQ 运营连成一个工作流程。

用户可以自然交流、查询产品资料、跟进本人工单；需要人工协助时，由助手整理草稿，用户核对后提交。客服处理问题，再将可复用的解决方案审核发布到知识库。

仓库地址：[xiao-e-xiao-e/zhizhu-support](https://github.com/xiao-e-xiao-e/zhizhu-support)。开发分支为 `dev`，默认主分支为 `master`；当前改造通过草稿 PR 审核，获得确认后再合并。

## 已实现的功能

- **统一智能助手**：普通交流、公开身份与模型信息、产品资料检索、相似工单与工单状态查询；正文边生成边显示，停止和断线保留已收到的内容。
- **可追溯回答**：文中引用与右侧资料面板对应，保留回答当时使用的片段和修订版本。
- **完整知识入库**：PDF、DOCX、HTML、CSV、Markdown、TXT 解析，后台任务、失败重试、分块预览、文档修订、审核发布、撤回、回滚和归档。
- **人工支持闭环**：工单草稿确认、幂等提交、接单分配、评论、解决、重新打开与关闭；提交时保存相关对话副本。
- **FAQ 知识运营**：从已解决问题整理草稿，审核后后台入库并发布，避免未审核内容进入用户回答。
- **权限与账号**：用户、客服、管理员三类角色；产品授权、私人会话隔离、本人或团队工单范围；不公开登录密码。
- **业务界面**：最近对话、可折叠侧栏、资料与草稿面板、手机抽屉、回答反馈、会话重命名及导出。
- **工程交付**：PostgreSQL / SQLite、数据库迁移、Docker Compose、健康检查、CI、自动回归与真实模型评估。

当前应用版本为 **2.6.1**，数据库结构为 **0007**。项目已完成 M1–M4 的实现与本机验收，M5 公网部署加固仍按计划推进。

## 快速启动（Docker，PowerShell）

需要 Docker Compose。首次构建需要网络下载依赖和本地嵌入模型。

```powershell
git clone https://github.com/xiao-e-xiao-e/zhizhu-support.git
cd zhizhu-support
git switch dev

# 生成部署配置和独立随机数据库密码；已有配置不会覆盖
.\scripts\init-deploy.ps1 -WebPort 8088

# 编辑 .env.deploy.local，填写自己的 API_KEY，核对 API_BASE_URL 与 CHAT_MODEL
docker compose --env-file .env.deploy.local up -d --build

# 首次部署交互创建管理员，密码不通过命令行参数传递
docker compose --env-file .env.deploy.local exec api python manage.py create-admin --username admin
```

打开 [http://127.0.0.1:8088](http://127.0.0.1:8088)。管理员登录后创建产品、版本和业务账号，并通过文档管理上传、入库及发布资料。新安装不会自动拥有本机已有的账号或业务数据。

```powershell
# 查看服务与健康状态
docker compose --env-file .env.deploy.local ps

# 更新代码后重建并启动
docker compose --env-file .env.deploy.local up -d --build
```

Compose 的运行项目名继续使用 `support-platform`，以兼容已有的 PostgreSQL、向量库、原件和模型缓存卷。项目与仓库改名不会迁移或重置这些卷。新安装可以显式指定独立的 Compose 项目名；已有部署沿用原项目名。

原生开发、配置解释、升级步骤及公网准备见 [开发和部署说明](docs/DEPLOYMENT.md)。

## 技术架构

```text
Vue 3 + TypeScript + Vite + Element Plus + Pinia
                       │ REST / SSE
                       ▼
                  FastAPI API
                       │
         ┌─────────────┼────────────────┐
         ▼             ▼                ▼
   SQLAlchemy       Chroma 服务     兼容 OpenAI 的模型 API
   PostgreSQL       BGE / ONNX      工具选择与正文流式生成
   或 SQLite        本地语义嵌入
         ▲             ▲
         └──── 独立入库 worker ──────────┘
```

| 目录 | 内容 |
| --- | --- |
| `frontend/src/` | 智能助手、业务页面、状态管理、引用与草稿面板 |
| `backend/app/` | 身份授权、资料管理、检索、工具运行、工单与 FAQ 业务 |
| `backend/migrations/` | Alembic 数据迁移 |
| `backend/tests/`、`frontend/tests/` | 隔离回归与前端事件处理检查 |
| `backend/evals/` | 检索、问答、工具执行和 FAQ 质量评估 |
| `backend/business_documents/` | 可经正常业务流程入库的产品指南 |
| `deploy/`、`compose.yaml` | 容器部署与反向代理 |
| `docs/` | 项目计划、部署、业务使用与验收记录 |

运行配置、凭据、数据库、上传原件、模型缓存和私有验证产物均不入库。

## 开发检查

后端使用 Python 3.12，前端使用 Node.js 24。原生开发先创建虚拟环境并安装 `backend/requirements-dev.lock`。

```powershell
cd backend
python -m ruff check app manage.py worker.py tests migrations evals
python -m pytest -q

cd ../frontend
npm ci
npm test
npm run build
```

CI 分别验证 SQLite、专用 PostgreSQL 和前端构建。真实模型评估另行运行，会消耗模型 API 用量；历史评估报告记录其对应版本的结果。

## 项目文档

- [项目计划书](docs/PROJECT_PLAN.md)与[执行记录](docs/EXECUTION_LOG.md)
- [业务账号与产品资料](docs/BUSINESS_GUIDE.md)
- [M2 工单与权限](docs/M2_ACCEPTANCE.md)、[M3 知识入库与版本](docs/M3_ACCEPTANCE.md)、[M4 智能工作流](docs/M4_ACCEPTANCE.md)
- [知识问答评估](docs/evaluations/m3-baseline/REPORT.md)与[工具及 FAQ 评估](docs/evaluations/m4-baseline/REPORT.md)

项目由最初的 Streamlit 知识库问答系统逐步演进而来；原有主分支历史保留，新的开发与审核围绕智能客服和知识协作流程开展。
