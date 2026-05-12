"""AI 本地知识库 — 基于 RAG 架构的文档问答系统。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from src import parse_file, add_documents, ask, search, get_collection_stats, delete_document, extract_text

PROJECT_DIR = Path(__file__).parent
CHAT_HISTORY_FILE = PROJECT_DIR / "chat_history.json"

# --- 页面配置 ---
st.set_page_config(
    page_title="AI 知识库",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Session State 初始化 ---
DEFAULTS = {
    "stats": {"total_chunks": 0, "sources": 0},
    "messages": [],
    "chat_sessions": {},
    "current_session": None,
    "chunk_size": 500,
    "chunk_overlap": 100,
    "top_k": 5,
    "temperature": 0.3,
    "similarity_threshold": 0.0,
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ============ 聊天历史持久化 ============

def _load_chat_sessions() -> dict[str, list[dict]]:
    if CHAT_HISTORY_FILE.exists():
        try:
            return json.loads(CHAT_HISTORY_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_chat_sessions(sessions: dict[str, list[dict]]) -> None:
    CHAT_HISTORY_FILE.write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2), "utf-8"
    )


def save_current_chat() -> None:
    msgs = st.session_state.messages
    name = st.session_state.current_session
    if not msgs or not name:
        return
    sessions = _load_chat_sessions()
    sessions[name] = msgs
    _save_chat_sessions(sessions)


def load_chat_session(name: str) -> list[dict] | None:
    sessions = _load_chat_sessions()
    return sessions.get(name)


def list_chat_sessions() -> list[str]:
    return sorted(_load_chat_sessions().keys(), reverse=True)


def delete_chat_session(name: str) -> None:
    sessions = _load_chat_sessions()
    sessions.pop(name, None)
    _save_chat_sessions(sessions)


# ============ 侧边栏 ============

with st.sidebar:
    st.title("📚 AI 知识库")
    st.caption("基于 RAG 架构的本地文档问答系统")

    # --- API 配置 ---
    st.divider()
    st.subheader("⚙️ API 配置")

    api_key = st.text_input(
        "API Key", type="password",
        value=os.getenv("API_KEY", ""),
        help="OpenAI 兼容的 API Key",
    )
    api_base = st.text_input(
        "API Base URL",
        value=os.getenv("API_BASE_URL", "https://api.openai.com/v1"),
        help="DeepSeek: https://api.deepseek.com | MiMo: https://api.xiaomimimo.com/v1",
    )
    embedding_model = st.text_input(
        "Embedding 模型",
        value=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    )
    chat_model = st.text_input(
        "Chat 模型",
        value=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
    )

    if api_key:
        os.environ["API_KEY"] = api_key
    if api_base:
        os.environ["API_BASE_URL"] = api_base
    if embedding_model:
        os.environ["EMBEDDING_MODEL"] = embedding_model
    if chat_model:
        os.environ["CHAT_MODEL"] = chat_model

    # --- RAG 参数 ---
    st.divider()
    st.subheader("🔧 RAG 参数")

    st.session_state.chunk_size = st.number_input(
        "Chunk 大小 (字符)", min_value=100, max_value=3000,
        value=st.session_state.chunk_size, step=50,
        help="文本分块的目标大小，越大每个块包含的上下文越多，但检索精度会降低",
    )
    st.session_state.chunk_overlap = st.number_input(
        "Chunk 重叠 (字符)", min_value=0, max_value=500,
        value=st.session_state.chunk_overlap, step=20,
        help="相邻块之间的重叠字符数，避免关键信息被切断",
    )
    st.session_state.top_k = st.slider(
        "检索数量 (top_k)", min_value=1, max_value=20,
        value=st.session_state.top_k,
        help="每次从知识库检索的文档片段数",
    )
    st.session_state.temperature = st.slider(
        "生成温度", min_value=0.0, max_value=1.5,
        value=st.session_state.temperature, step=0.05,
        help="越高回答越有创造性，越低越保守严谨",
    )
    st.session_state.similarity_threshold = st.slider(
        "相似度阈值", min_value=0.0, max_value=1.0,
        value=st.session_state.similarity_threshold, step=0.05,
        help="低于此相似度的检索结果会被过滤，0 表示不过滤。设高可减少无关内容干扰",
    )

    # --- 知识库状态 ---
    st.divider()
    st.subheader("📊 知识库状态")

    if st.button("🔄 刷新统计", use_container_width=True):
        try:
            st.session_state.stats = get_collection_stats()
        except Exception:
            st.session_state.stats = {"total_chunks": 0, "sources": 0}

    col1, col2 = st.columns(2)
    col1.metric("文档块", st.session_state.stats["total_chunks"])
    col2.metric("文件数", st.session_state.stats["sources"])

    st.divider()
    st.caption("技术栈: Streamlit + ChromaDB + LLM")


# ============ 主区域：三个 Tab ============
tab_upload, tab_query, tab_history = st.tabs(["📤 文档管理", "💬 智能问答", "📋 对话历史"])

# ============ Tab 1: 文档管理 ============
with tab_upload:
    st.subheader("上传新文档")
    st.caption("支持 PDF、DOCX、HTML、CSV、Markdown、TXT 及代码文件")

    uploaded_files = st.file_uploader(
        "选择文件",
        type=["pdf", "docx", "html", "htm", "csv", "md", "txt",
              "py", "js", "ts", "json", "yaml", "yml"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    # ---- 文档预览 ----
    if uploaded_files and len(uploaded_files) == 1:
        with st.expander("🔍 文档内容预览（前 2000 字符）"):
            try:
                preview = extract_text(uploaded_files[0].name, uploaded_files[0].read())
                uploaded_files[0].seek(0)  # reset for later processing
                st.text(preview[:2000])
                if len(preview) > 2000:
                    st.caption(f"… 共 {len(preview)} 字符，仅显示前 2000")
            except Exception as e:
                st.warning(f"预览失败: {e}")

    if uploaded_files:
        col_btn, col_info = st.columns([1, 3])
        with col_btn:
            process_btn = st.button("📥 解析并入库", type="primary", use_container_width=True)
        with col_info:
            file_names = [f.name for f in uploaded_files]
            st.write(f"已选择 **{len(uploaded_files)}** 个文件: {', '.join(file_names)}")

        if process_btn:
            if not api_key:
                st.error("请先在侧边栏配置 API Key")
            else:
                total_chunks = 0
                fail_count = 0
                progress = st.progress(0, "正在解析文档...")
                status = st.empty()

                for i, file in enumerate(uploaded_files):
                    status.info(f"处理中: {file.name}")
                    try:
                        file_bytes = file.read()
                        chunks = parse_file(
                            file.name, file_bytes,
                            chunk_size=st.session_state.chunk_size,
                            chunk_overlap=st.session_state.chunk_overlap,
                        )
                        if chunks:
                            n = add_documents(file.name, chunks)
                            total_chunks += n
                    except Exception as e:
                        fail_count += 1
                        st.error(f"解析 {file.name} 失败: {e}")

                    progress.progress((i + 1) / len(uploaded_files))

                progress.empty()
                if fail_count:
                    status.warning(f"完成: {total_chunks} 块入库, {fail_count} 个文件失败")
                else:
                    status.success(f"完成! 共入库 {total_chunks} 个文本块")

                try:
                    st.session_state.stats = get_collection_stats()
                except Exception:
                    pass
                st.rerun()

    # ---- 已入库文档 ----
    st.divider()
    st.subheader("📋 已入库文档")

    try:
        from src.vectorstore import get_collection
        col = get_collection()
        metas = col.get(include=["metadatas"])
        sources_map: dict[str, int] = {}
        if metas["metadatas"]:
            for m in metas["metadatas"]:
                src = m["source"]
                sources_map[src] = sources_map.get(src, 0) + 1
    except Exception:
        sources_map = {}

    if sources_map:
        for filename, chunk_count in sorted(sources_map.items()):
            col_name, col_count, col_del, col_view = st.columns([3, 1, 1, 1])
            col_name.write(f"📄 {filename}")
            col_count.caption(f"{chunk_count} 块")
            if col_del.button("🗑️", key=f"del_{filename}", help=f"删除 {filename}"):
                delete_document(filename)
                st.session_state.stats = get_collection_stats()
                st.rerun()
            if col_view.button("🔍", key=f"view_{filename}", help=f"查看 {filename} 内容"):
                chunks_data = col.get(where={"source": filename}, include=["documents"])
                if chunks_data["documents"]:
                    with st.expander(f"📄 {filename} 内容", expanded=True):
                        for i, doc in enumerate(chunks_data["documents"]):
                            st.caption(f"Chunk {i+1}")
                            st.text(doc[:600])
    else:
        st.info("知识库为空，请上传文档")

    # ---- 快速搜索 ----
    st.divider()
    st.subheader("🔍 快速搜索")
    search_query = st.text_input("输入关键词查看相关文档片段", placeholder="输入搜索内容...")
    if search_query:
        try:
            results = search(search_query, top_k=st.session_state.top_k,
                           similarity_threshold=st.session_state.similarity_threshold)
            if results:
                for j, item in enumerate(results):
                    sim = item.get("similarity", 1.0 - item["distance"])
                    with st.expander(f"结果 {j+1} | {item['source']} (相似度: {sim:.3f})"):
                        st.text(item["content"][:800])
            else:
                st.info("未找到相关结果（可能是相似度阈值过高）")
        except Exception as e:
            st.error(f"搜索失败: {e}")


# ============ Tab 2: 智能问答 ============
with tab_query:
    st.subheader("💬 基于知识库的智能问答")

    # ---- 对话会话管理 ----
    session_col1, session_col2, session_col3 = st.columns([3, 1, 1])
    with session_col1:
        session_name = st.text_input(
            "会话名称",
            value=st.session_state.current_session or "",
            placeholder="给本次对话起个名（如：技术方案讨论），留空则不保存",
            label_visibility="collapsed",
        )
    with session_col2:
        if st.button("💾 保存", use_container_width=True):
            if session_name and st.session_state.messages:
                st.session_state.current_session = session_name
                save_current_chat()
                st.success(f"已保存: {session_name}")
                st.rerun()
            else:
                st.warning("请先输入会话名称并有对话内容")
    with session_col3:
        if st.button("🗑️ 清空", use_container_width=True):
            st.session_state.messages = []
            st.session_state.current_session = None
            st.rerun()

    # ---- 显示历史消息 ----
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📎 参考来源"):
                    for src in msg["sources"]:
                        st.caption(f"📄 {src}")
            if msg.get("contexts"):
                with st.expander("🔬 检索详情"):
                    for ctx in msg["contexts"]:
                        sim = ctx.get("similarity", 0)
                        st.caption(f"📄 {ctx['source']} | 相似度: {sim:.3f}")
                        st.text(ctx["content"][:300])

    # ---- 输入 ----
    if question := st.chat_input("输入你的问题，基于已入库文档回答..."):
        if not api_key:
            st.error("请先在侧边栏配置 API Key")
        else:
            st.session_state.messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)

            with st.chat_message("assistant"):
                with st.spinner("检索中..."):
                    try:
                        result = ask(
                            question,
                            top_k=st.session_state.top_k,
                            temperature=st.session_state.temperature,
                            similarity_threshold=st.session_state.similarity_threshold,
                        )
                        st.markdown(result["answer"])
                        if result["sources"]:
                            with st.expander(f"📎 参考来源 ({len(result['sources'])} 个文件)"):
                                for src in result["sources"]:
                                    st.caption(f"📄 {src}")
                        if result["contexts"]:
                            with st.expander("🔬 检索详情"):
                                for ctx in result["contexts"]:
                                    sim = ctx.get("similarity", 1.0 - ctx["distance"])
                                    st.caption(f"📄 {ctx['source']} | 相似度: {sim:.3f}")
                                    st.text(ctx["content"][:300])
                    except Exception as e:
                        st.error(f"请求失败: {e}")
                        result = {"answer": f"请求失败: {e}", "sources": [], "contexts": []}

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "sources": result.get("sources", []),
                    "contexts": result.get("contexts", []),
                })

            # 自动保存
            if st.session_state.current_session and st.session_state.messages:
                save_current_chat()


# ============ Tab 3: 对话历史 ============
with tab_history:
    st.subheader("📋 已保存的对话")

    sessions = list_chat_sessions()
    if not sessions:
        st.info("暂未保存过对话。在「智能问答」标签页中输入会话名称并点击保存。")
    else:
        for sname in sessions:
            col_name, col_load, col_delete, col_export = st.columns([3, 1, 1, 1])
            col_name.write(f"💬 {sname}")
            if col_load.button("📂 加载", key=f"load_{sname}", use_container_width=True):
                msgs = load_chat_session(sname)
                if msgs is not None:
                    st.session_state.messages = msgs
                    st.session_state.current_session = sname
                    st.success(f"已加载: {sname}")
                    st.rerun()
            if col_delete.button("🗑️", key=f"histdel_{sname}", use_container_width=True):
                delete_chat_session(sname)
                st.rerun()
            if col_export.button("📤", key=f"export_{sname}", use_container_width=True,
                                 help="导出为 Markdown"):
                msgs = load_chat_session(sname)
                if msgs:
                    md = f"# {sname}\n\n导出时间: {datetime.now(timezone.utc).isoformat()}\n\n"
                    for m in msgs:
                        role = "👤 用户" if m["role"] == "user" else "🤖 助手"
                        md += f"## {role}\n\n{m['content']}\n\n"
                        if m.get("sources"):
                            md += f"> 参考来源: {', '.join(m['sources'])}\n\n"
                        md += "---\n\n"
                    st.download_button(
                        "📥 下载 MD", data=md, file_name=f"{sname}.md",
                        mime="text/markdown", key=f"dl_{sname}",
                    )
