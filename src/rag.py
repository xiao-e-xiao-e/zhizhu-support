"""RAG 问答模块：检索 + LLM 生成。"""
from __future__ import annotations

import os

from openai import OpenAI

from .vectorstore import search

_SYSTEM_PROMPT = """你是一个知识库助手。根据用户提供的资料片段回答问题。

要求：
- 只根据提供的资料回答，不要编造信息。
- 如果资料不足以回答问题，直接说明"当前知识库中没有足够的信息回答此问题"。
- 回答尽量简洁、有条理。
- 引用资料时注明来源文件名。
- 用中文回答。
"""


def _get_client() -> OpenAI:
    api_key = os.getenv("API_KEY", "")
    base_url = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
    if not api_key:
        raise RuntimeError("请在 .env 中设置 API_KEY")
    return OpenAI(api_key=api_key, base_url=base_url)


def _get_chat_model() -> str:
    return os.getenv("CHAT_MODEL", "gpt-4o-mini")


def _build_context(results: list[dict]) -> str:
    """将检索结果拼成 LLM 上下文。"""
    parts: list[str] = []
    for i, item in enumerate(results, 1):
        parts.append(f"[资料 {i} | 来源: {item['source']}]\n{item['content']}")
    return "\n\n".join(parts)


def ask(query: str, top_k: int = 5, temperature: float = 0.3, similarity_threshold: float = 0.0) -> dict:
    """RAG 问答主流程。

    Args:
        query: 用户问题
        top_k: 检索结果数
        temperature: LLM 生成温度
        similarity_threshold: 最低相似度阈值

    Returns:
        {answer: str, sources: [str], contexts: [dict]}
    """
    results = search(query, top_k=top_k, similarity_threshold=similarity_threshold)
    if not results:
        return {
            "answer": "当前知识库中尚未收录相关文档，请先上传一些文档。",
            "sources": [],
            "contexts": [],
        }

    context_text = _build_context(results)
    client = _get_client()
    model = _get_chat_model()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是与用户问题相关的资料：\n\n{context_text}\n\n用户问题：{query}"},
        ],
        temperature=temperature,
        max_tokens=1024,
    )

    answer = response.choices[0].message.content or ""
    return {
        "answer": answer,
        "sources": list({r["source"] for r in results}),
        "contexts": results,
    }
