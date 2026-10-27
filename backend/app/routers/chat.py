"""问答路由：普通问答与 SSE 流式问答。"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..schemas import AskRequest
from ..services import rag, sessions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/ask")
def ask(payload: AskRequest) -> dict:
    """非流式问答，便于脚本调用与联调排查。"""
    try:
        result = rag.ask(
            payload.question,
            top_k=payload.top_k,
            temperature=payload.temperature,
            similarity_threshold=payload.similarity_threshold,
            llm_override=payload.llm.model_dump() if payload.llm else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("问答失败")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if payload.session:
        sessions.append_messages(
            payload.session,
            [
                {"role": "user", "content": payload.question},
                {
                    "role": "assistant",
                    "content": result["answer"],
                    "sources": result["sources"],
                    "contexts": result["contexts"],
                },
            ],
        )
    return result


@router.post("/stream")
def ask_stream(payload: AskRequest) -> StreamingResponse:
    """SSE 流式问答。

    事件序列：
        contexts → delta* → done
    出错时发送 error 事件，不中断 HTTP 连接。
    """

    def event_stream():
        answer_parts: list[str] = []
        contexts: list[dict] = []
        sources: list[str] = []

        try:
            for event in rag.ask_stream(
                payload.question,
                top_k=payload.top_k,
                temperature=payload.temperature,
                similarity_threshold=payload.similarity_threshold,
                llm_override=payload.llm.model_dump() if payload.llm else None,
            ):
                kind = event["type"]
                if kind == "contexts":
                    contexts = event["data"]
                elif kind == "delta":
                    answer_parts.append(event["data"])
                elif kind == "done":
                    sources = event["data"].get("sources", [])
                yield _sse(kind, event["data"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("流式问答失败")
            yield _sse("error", {"message": str(exc)})
            return

        if payload.session and answer_parts:
            try:
                sessions.append_messages(
                    payload.session,
                    [
                        {"role": "user", "content": payload.question},
                        {
                            "role": "assistant",
                            "content": "".join(answer_parts),
                            "sources": sources,
                            "contexts": contexts,
                        },
                    ],
                )
            except Exception:  # noqa: BLE001
                logger.exception("会话保存失败，不影响本次回答")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
