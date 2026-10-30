"""问答路由：普通问答与 SSE 流式问答。"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..core.auth import current_user
from ..core.database import session_factory
from ..models import User
from ..schemas import AskRequest
from ..services import rag, sessions
from ..services.catalog import validate_scope

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
def ask(payload: AskRequest, user: User = Depends(current_user)) -> dict:
    """非流式问答，便于脚本调用与联调排查。"""
    scope = _scope(payload, user.id)
    try:
        result = rag.ask(
            payload.question,
            top_k=payload.top_k,
            temperature=payload.temperature,
            similarity_threshold=payload.similarity_threshold,
            history=_history(payload, user.id),
            product_id=payload.product_id, version_id=payload.version_id, user_id=user.id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("问答失败")
        raise HTTPException(status_code=502, detail="问答服务暂时不可用，请稍后重试") from exc

    if payload.session:
        saved = sessions.append_messages(
            user.id,
            payload.session,
            [
                {"role": "user", "content": payload.question},
                {
                    "role": "assistant",
                    "content": result["answer"],
                    "sources": result["sources"],
                    "contexts": result["contexts"],
                },
            ], scope=scope,
        )
        result["message_id"] = saved["written_message_ids"][-1]
    return result


@router.post("/stream")
def ask_stream(payload: AskRequest, user: User = Depends(current_user)) -> StreamingResponse:
    """SSE 流式问答。

    事件序列：
        contexts → delta* → done
    出错时发送 error 事件，不中断 HTTP 连接。
    """

    scope = _scope(payload, user.id)
    history = _history(payload, user.id)

    def event_stream():
        answer_parts: list[str] = []
        contexts: list[dict] = []
        sources: list[str] = []
        message_id: int | None = None
        metrics = {}

        try:
            for event in rag.ask_stream(
                payload.question,
                top_k=payload.top_k,
                temperature=payload.temperature,
                similarity_threshold=payload.similarity_threshold,
                history=history,
                product_id=payload.product_id, version_id=payload.version_id, user_id=user.id,
            ):
                kind = event["type"]
                if kind == "contexts":
                    contexts = event["data"]
                elif kind == "delta":
                    answer_parts.append(event["data"])
                elif kind == "done":
                    sources = event["data"].get("sources", [])
                    metrics = {k: v for k, v in event["data"].items() if k not in {"sources", "contexts"}}
                # 保存成功后再发 done，确保客户端获知持久化结果。
                if kind != "done":
                    yield _sse(kind, event["data"])
        except Exception:  # noqa: BLE001
            logger.exception("流式问答失败")
            yield _sse("error", {"message": "问答服务暂时不可用，请稍后重试"})
            return

        if payload.session and answer_parts:
            try:
                saved = sessions.append_messages(
                    user.id,
                    payload.session,
                    [
                        {"role": "user", "content": payload.question},
                        {
                            "role": "assistant",
                            "content": "".join(answer_parts),
                            "sources": sources,
                            "contexts": contexts,
                        },
                    ], scope=scope,
                )
                message_id = saved["written_message_ids"][-1]
            except Exception:  # noqa: BLE001
                logger.exception("会话保存失败")
                yield _sse("error", {"message": "回答已生成，但保存失败，请手动保存当前会话"})
                return

        yield _sse("done", {"sources": sources, "contexts": contexts, "message_id": message_id, **metrics})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _history(payload: AskRequest, owner_id: str) -> list[dict]:
    if payload.session:
        return sessions.recent_history(owner_id, payload.session)
    budget = 16000
    history = []
    for message in reversed(payload.history):
        if len(message.content) > budget:
            break
        history.append(message.model_dump())
        budget -= len(message.content)
    return list(reversed(history))


def _scope(payload: AskRequest, owner_id: str):
    with session_factory()() as db:
        validate_scope(db, payload.product_id, payload.version_id, owner_id)
    scope = (payload.product_id, payload.version_id)
    if payload.session:
        sessions.ensure_access(owner_id, payload.session)
        existing = sessions.get_session(owner_id, payload.session)
        if existing and scope != (existing["product_id"], existing["version_id"]):
            raise HTTPException(409, "请新建会话后切换产品或版本")
    return scope
