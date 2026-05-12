# RAG 知识库问答系统

基于 RAG (Retrieval-Augmented Generation) 架构的智能知识库问答系统。支持多格式文档上传，通过向量检索与 LLM 生成实现自然语言问答。

## 功能

- **多格式文档解析**：支持 PDF、DOCX、HTML、CSV、Markdown、TXT
- **智能分块**：按段落边界切分 + 重叠窗口
- **向量检索**：ChromaDB + TF-IDF 本地嵌入，零依赖下载
- **RAG 问答**：检索增强生成，回答带来源引用
- **可配置参数**：Chunk 大小、重叠比例、Top-K、相似度阈值、温度
- **对话历史**：持久化存储，支持导出 Markdown

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境
cp .env.example .env
# 编辑 .env 填入你的 API_KEY

# 启动
streamlit run app.py
```

## 项目结构

```
├── app.py              # Streamlit 前端
├── src/
│   ├── parser.py       # 文档解析模块
│   ├── vectorstore.py  # 向量存储与嵌入
│   └── rag.py          # RAG 问答模块
├── data/               # 示例文档
└── requirements.txt
```

## 技术栈

- Streamlit — Web UI
- ChromaDB — 向量数据库
- scikit-learn — TF-IDF 嵌入
- OpenAI SDK — LLM 调用（兼容 DeepSeek 等）

## 使用说明

1. **文档管理**页面上传文档，支持预览解析结果
2. **智能问答**页面输入问题，系统检索相关文档并生成回答
3. **对话历史**页面查看、导出、删除历史记录
