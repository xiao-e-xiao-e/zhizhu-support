"""会话管理路由。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from ..schemas import SessionDetail, SessionSaveRequest, SessionSummary
from ..services import sessions

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary])
def list_sessions() -> list[SessionSummary]:
    return [SessionSummary(**row) for row in sessions.list_sessions()]


@router.get("/{name}", response_model=SessionDetail)
def get_session(name: str) -> SessionDetail:
    payload = sessions.get_session(name)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {name}")
    return SessionDetail(**payload)


@router.put("/{name}", response_model=SessionDetail)
def save_session(name: str, payload: SessionSaveRequest) -> SessionDetail:
    messages = [m.model_dump() for m in payload.messages]
    saved = sessions.save_session(name, messages)
    return SessionDetail(**saved)


@router.delete("/{name}")
def delete_session(name: str) -> dict:
    if not sessions.delete_session(name):
        raise HTTPException(status_code=404, detail=f"会话不存在: {name}")
    return {"deleted": name}


@router.get("/{name}/export", response_class=PlainTextResponse)
def export_session(name: str) -> PlainTextResponse:
    markdown = sessions.export_markdown(name)
    if markdown is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {name}")

    # HTTP 头只能承载 latin-1 字节，中文文件名直接塞进 filename= 会抛
    # UnicodeEncodeError 导致 500。这里同时给出 ASCII 回退名和
    # RFC 5987 的 filename*=UTF-8'' 编码名，现代浏览器会用后者。
    ascii_fallback = (
        "".join(ch if (ch.isascii() and (ch.isalnum() or ch in "-_")) else "_" for ch in name)
        or "session"
    )
    disposition = (
        f'attachment; filename="{ascii_fallback}.md"; '
        f"filename*=UTF-8''{quote(f'{name}.md', safe='')}"
    )

    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )
