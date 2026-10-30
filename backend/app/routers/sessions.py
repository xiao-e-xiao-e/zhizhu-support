"""会话管理路由。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from ..core.auth import current_user
from ..core.database import session_factory
from ..models import User
from ..schemas import SessionDetail, SessionSaveRequest, SessionSummary
from ..services import sessions
from ..services.catalog import validate_scope

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary])
def list_sessions(user: User = Depends(current_user)) -> list[SessionSummary]:
    return [SessionSummary(**row) for row in sessions.list_sessions(user.id)]


@router.get("/{name}", response_model=SessionDetail)
def get_session(
    name: str = Path(min_length=1, max_length=120), user: User = Depends(current_user)
) -> SessionDetail:
    payload = sessions.get_session(user.id, name)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {name}")
    return SessionDetail(**payload)


@router.put("/{name}", response_model=SessionDetail)
def save_session(
    payload: SessionSaveRequest,
    name: str = Path(min_length=1, max_length=120),
    user: User = Depends(current_user),
) -> SessionDetail:
    messages = [m.model_dump() for m in payload.messages]
    scope = None
    if {"product_id", "version_id"} & payload.model_fields_set:
        with session_factory()() as db:
            validate_scope(db, payload.product_id, payload.version_id, user.id)
        scope = (payload.product_id, payload.version_id)
    try:
        saved = sessions.save_session(user.id, name, messages, scope=scope)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return SessionDetail(**saved)


@router.delete("/{name}")
def delete_session(name: str, user: User = Depends(current_user)) -> dict:
    if not sessions.delete_session(user.id, name):
        raise HTTPException(status_code=404, detail=f"会话不存在: {name}")
    return {"deleted": name}


@router.get("/{name}/export", response_class=PlainTextResponse)
def export_session(name: str, user: User = Depends(current_user)) -> PlainTextResponse:
    markdown = sessions.export_markdown(user.id, name)
    if markdown is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {name}")

    # HTTP 头只能承载 latin-1 字节，中文文件名直接塞进 filename= 会抛
    # UnicodeEncodeError 导致 500。这里同时给出 ASCII 回退名和
    # RFC 5987 的 filename*=UTF-8'' 编码名，现代浏览器会用后者。
    ascii_fallback = (
        "".join(ch if (ch.isascii() and (ch.isalnum() or ch in "-_")) else "_" for ch in name) or "session"
    )
    disposition = (
        f"attachment; filename=\"{ascii_fallback}.md\"; filename*=UTF-8''{quote(f'{name}.md', safe='')}"
    )

    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


class RenameSession(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^/\\\x00-\x1f]+$")


@router.patch("/{name}", response_model=SessionDetail)
def rename_session(name: str, payload: RenameSession, user: User = Depends(current_user)):
    return sessions.rename_session(user.id, name, payload.name)
