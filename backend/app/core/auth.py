"""服务端 Cookie 会话、密码散列与角色授权。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select

from ..models import AuthSession, DemoResource, User, utcnow
from .config import get_settings
from .database import session_factory

COOKIE_NAME = "support_session"
password_hasher = PasswordHasher()
_DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def demo_login_allowed(db, user):
    return get_settings().demo_mode or not db.scalar(
        select(DemoResource.key).where(DemoResource.kind == "user", DemoResource.resource_id == user.id)
    )


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(encoded: str | None, password: str) -> bool:
    try:
        matched = password_hasher.verify(encoded or _DUMMY_HASH, password)
        return bool(encoded and matched)
    except (VerificationError, InvalidHashError):
        return False


def issue_session(db, user: User) -> str:
    token = secrets.token_urlsafe(48)
    now = utcnow()
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    db.add(
        AuthSession(
            token_hash=token_digest(token),
            user_id=user.id,
            expires_at=now + timedelta(hours=get_settings().session_hours),
        )
    )
    return token


def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 256:
        raise HTTPException(401, "请先登录")
    with session_factory()() as db:
        user = db.scalar(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.token_hash == token_digest(token),
                AuthSession.expires_at > utcnow(),
                User.is_active.is_(True),
            )
        )
        if user is None or not demo_login_allowed(db, user):
            raise HTTPException(401, "登录已过期，请重新登录")
        return user


def require_staff(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "staff"}:
        raise HTTPException(403, "此操作需要客服或管理员权限")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "此操作需要管理员权限")
    return user
