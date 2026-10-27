"""RAG 问答编排：检索 → 拼上下文 → LLM 生成。

相比原实现新增流式输出（SSE），让前端可以逐字渲染。
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from openai import OpenAI

from ..core.config import get_settings
from .vectorstore import search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个知识库助手。根据用户提供的资料片段回答问题。

要求：
- 只根据提供的资料回答，不要编造信息。
- 如果资料不足以回答问题，直接说明"当前知识库中没有足够的信息回答此问题"。
- 回答尽量简洁、有条理，使用 Markdown 格式组织内容。
- 引用资料时用 [资料N] 的形式标注来源编号。
- 用中文回答。
"""


def resolve_llm_config(override: dict[str, Any] | None = None) -> dict[str, str]:
    """合并前端传入的 LLM 配置与后端 .env 配置。前端配置优先。"""
    settings = get_settings()
    override = override or {}
    return {
        "api_key": override.get("api_key") or settings.api_key,
        "api_base_url": override.get("api_base_url") or settings.api_base_url,
        "chat_model": override.get("chat_model") or settings.chat_model,
    }


def _build_client(config: dict[str, str]) -> OpenAI:
    api_key = config["api_key"]
    if not api_key or api_key == "your_api_key_here":
        raise RuntimeError("未配置 API Key，请在后端 .env 或前端设置中填写")
    return OpenAI(api_key=api_key, base_url=config["api_base_url"])


def _build_context(results: list[dict]) -> str:
    parts: list[str] = []
    for i, item in enumerate(results, 1):
        parts.append(f"[资料{i} | 来源: {item['source']}]\n{item['content']}")
    return "\n\n".join(parts)


def ask(
    query: str,
    top_k: int = 5,
    temperature: float = 0.3,
    similarity_threshold: float = 0.0,
    llm_override: dict[str, Any] | None = None,
) -> dict:
    """非流式问答，便于脚本与测试使用。"""
    results = search(query, top_k=top_k, similarity_threshold=similarity_threshold)
    if not results:
        return {
            "answer": "当前知识库中尚未收录相关文档，请先上传一些文档。",
            "sources": [],
            "contexts": [],
        }

    settings = get_settings()
    config = resolve_llm_config(llm_override)
    client = _build_client(config)

    response = client.chat.completions.create(
        model=config["chat_model"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"以下是与用户问题相关的资料：\n\n{_build_context(results)}\n\n用户问题：{query}",
            },
        ],
        temperature=temperature,
        max_tokens=settings.max_tokens,
    )

    return {
        "answer": response.choices[0].message.content or "",
        "sources": list(dict.fromkeys(r["source"] for r in results)),
        "contexts": results,
    }


def ask_stream(
    query: str,
    top_k: int = 5,
    temperature: float = 0.3,
    similarity_threshold: float = 0.0,
    llm_override: dict[str, Any] | None = None,
) -> Iterator[dict]:
    """流式问答。逐条 yield 结构化事件，由路由层编码为 SSE。"""
    results = search(query, top_k=top_k, similarity_threshold=similarity_threshold)

    if not results:
        yield {"type": "contexts", "data": []}
        yield {
            "type": "delta",
            "data": "当前知识库中尚未收录相关文档，请先到「文档管理」上传一些文档。",
        }
        yield {"type": "done", "data": {"sources": [], "contexts": []}}
        return

    # 先把检索结果推给前端，用户能立刻看到「命中了哪些片段」
    yield {"type": "contexts", "data": results}

    settings = get_settings()
    config = resolve_llm_config(llm_override)
    client = _build_client(config)

    stream = client.chat.completions.create(
        model=config["chat_model"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"以下是与用户问题相关的资料：\n\n{_build_context(results)}\n\n用户问题：{query}",
            },
        ],
        temperature=temperature,
        max_tokens=settings.max_tokens,
        stream=True,
    )

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield {"type": "delta", "data": delta}

    yield {
        "type": "done",
        "data": {
            "sources": list(dict.fromkeys(r["source"] for r in results)),
            "contexts": results,
        },
    }
