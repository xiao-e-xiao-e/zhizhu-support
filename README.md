# RAG 知识库问答系统

基于检索增强生成（Retrieval-Augmented Generation）的本地知识库问答系统。
上传文档 → 自动切分与向量化 → 提问时先检索相关片段，再由大模型基于片段作答，
回答附带可展开的参考来源与相似度分数。

前后端分离：后端提供 REST + SSE 接口，前端是独立的 Vue 单页应用。

## 架构

```
frontend/                     Vue 3 + Vite + TypeScript + Element Plus
    │  HTTP / SSE（开发期经 Vite 代理）
    ▼
backend/app/
    ├── routers/              接口层：documents / chat / sessions / system
    ├── services/
    │   ├── parser.py         多格式解析 + 段落感知分块
    │   ├── embedding.py      fastembed（ONNX Runtime）本地语义嵌入
    │   ├── vectorstore.py    ChromaDB 持久化集合（余弦空间）
    │   ├── rag.py            检索 → 拼上下文 → LLM 生成（支持流式）
    │   └── sessions.py       会话 JSON 持久化（原子写入）
    └── core/config.py        统一配置
    ▼
chroma_db/                    向量库（sqlite3）
data/                         示例文档
```

## 快速开始

### 1. 后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 安装依赖
pip install -r requirements.txt

# 配置
cp .env.example .env
# 编辑 .env，填入 API_KEY

# 启动
python run.py
```

后端跑在 `http://127.0.0.1:8000`，接口文档在 `http://127.0.0.1:8000/docs`。

首次启动会自动下载嵌入模型 `BAAI/bge-small-zh-v1.5`（约 95MB），
之后缓存在 `backend/.model_cache/`。

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。开发服务器已配置 `/api` 代理到后端 8000 端口，
前端代码里只写相对路径，无需额外处理跨域。

生产构建：

```bash
npm run build          # 产物在 frontend/dist/
```

## 技术栈

| 层 | 选型 |
|---|---|
| 前端框架 | Vue 3.5（`<script setup>` + TypeScript） |
| 构建工具 | Vite 8 |
| UI 组件 | Element Plus（自定义主题令牌） |
| 状态管理 | Pinia |
| 路由 | Vue Router 4 |
| Markdown | markdown-it + highlight.js（按需注册语言） |
| 后端框架 | FastAPI + Uvicorn |
| 向量数据库 | ChromaDB（PersistentClient，余弦距离空间） |
| 嵌入模型 | fastembed + BAAI/bge-small-zh-v1.5（ONNX Runtime，512 维） |
| LLM 调用 | openai SDK（兼容 DeepSeek 等 OpenAI 格式端点） |
| 文档解析 | PyPDF2、python-docx、html.parser、csv |

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/config` | 前端所需默认配置（不回传 API Key） |
| POST | `/api/documents/upload` | 上传并入库（多文件） |
| POST | `/api/documents/preview` | 只解析预览，不入库 |
| GET | `/api/documents` | 已入库文件列表 |
| GET | `/api/documents/stats` | 知识库统计 |
| POST | `/api/documents/search` | 纯向量检索（不调 LLM） |
| GET | `/api/documents/{name}/chunks` | 查看某文件的分块 |
| DELETE | `/api/documents/{name}` | 删除某文件的全部分块 |
| POST | `/api/chat/ask` | 非流式问答 |
| POST | `/api/chat/stream` | SSE 流式问答 |
| GET | `/api/sessions` | 会话列表 |
| GET | `/api/sessions/{name}` | 会话详情 |
| PUT | `/api/sessions/{name}` | 覆盖保存会话 |
| DELETE | `/api/sessions/{name}` | 删除会话 |
| GET | `/api/sessions/{name}/export` | 导出为 Markdown |

## 相比旧版（Streamlit 单体）的改动

旧版本是单进程 Streamlit 应用，`app.py` + `src/` 三个模块，前端逻辑与业务逻辑混在一起。
本次重构为前后端分离，同时修掉了四个实质性缺陷：

1. **依赖声明缺失**：旧 `requirements.txt` 没列 `scikit-learn` 与 `numpy`，
   而代码默认路径依赖它们，照 README 装完必然 ImportError。
   新版改用 fastembed，依赖清单与实际导入一致。

2. **向量库退化为文档存储器**：旧实现在本地模式下每次入库都重新拟合 TF-IDF 词汇表，
   历史向量随之失效；检索时更是把全库文档拉出来重新拟合、手算余弦，
   ChromaDB 的 HNSW 索引从未被使用，检索复杂度是 O(N) 全量扫描。
   新版入库与检索共用同一个嵌入模型，检索走 `collection.query()`，索引真正生效。

3. **相似度语义错误**：旧实现用 `1 - distance` 当相似度，但集合是默认的 L2 空间，
   L2 距离无上界，换算结果可以为负且与余弦无关。
   新版显式声明 `hnsw:space=cosine`，`1 - distance` 就是余弦相似度。

4. **中文适配**：旧实现用 `char_wb`（按词边界切字符 n-gram），
   对中文这类无空格语言会退化。新版直接换成中文语义向量模型，
   从根本上不再依赖字面匹配。
