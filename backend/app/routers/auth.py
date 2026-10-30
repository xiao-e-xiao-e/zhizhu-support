"""登录、退出、个人资料和管理员账号管理。"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.auth import (
    COOKIE_NAME,
    current_user,
    demo_login_allowed,
    issue_session,
    password_hasher,
    require_admin,
    token_digest,
    verify_password,
)
from ..core.config import get_settings
from ..core.database import get_db
from ..models import AuthSession, LoginFailure, Product, ProductGrant, User, utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=128)


class CreateUserRequest(LoginRequest):
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "staff", "user"] = "user"
    restrict_products: bool = False
    product_ids: list[str] = Field(default_factory=list)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    role: str
    is_active: bool
    restrict_products: bool = False
    product_ids: list[str] = Field(default_factory=list)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    username = payload.username.lower()
    # 不信任客户端传入的 X-Forwarded-For；代理部署由服务器受信任配置决定 client.host。
    ip_hash = token_digest(request.client.host if request.client else "unknown")
    username_hash = token_digest(username)
    since = utcnow() - timedelta(minutes=5)
    db.execute(delete(LoginFailure).where(LoginFailure.created_at < since))
    ip_failures = db.scalar(
        select(func.count())
        .select_from(LoginFailure)
        .where(
            LoginFailure.ip_hash == ip_hash,
            LoginFailure.created_at >= since,
        )
    )
    account_failures = db.scalar(
        select(func.count())
        .select_from(LoginFailure)
        .where(
            LoginFailure.username_hash == username_hash,
            LoginFailure.created_at >= since,
        )
    )
    if ip_failures >= 20 or account_failures >= 8:
        db.commit()
        raise HTTPException(429, "登录尝试过于频繁，请五分钟后重试", headers={"Retry-After": "300"})
    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(user.password_hash if user else None, payload.password)
    if not user or not valid or not user.is_active or not demo_login_allowed(db, user):
        db.add(LoginFailure(ip_hash=ip_hash, username_hash=username_hash))
        db.commit()
        raise HTTPException(401, "用户名或密码错误")
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(payload.password)
    token = issue_session(db, user)
    db.commit()
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api",
    )
    response.headers["Cache-Control"] = "no-store"
    return user


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(token)))
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/api")


@router.post("/password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stored = db.get(User, user.id)
    if not verify_password(stored.password_hash, payload.old_password):
        raise HTTPException(400, "原密码不正确")
    stored.password_hash = password_hasher.hash(payload.new_password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/api")


@router.get("/users", response_model=list[UserOut])
def list_users(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [user_out(db, u) for u in db.scalars(select(User).order_by(User.created_at))]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: CreateUserRequest, _admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    validate_products(db, payload.product_ids)
    user = User(
        restrict_products=payload.restrict_products,
        username=payload.username.lower(),
        password_hash=password_hasher.hash(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.flush()
        for product_id in set(payload.product_ids):
            db.add(ProductGrant(user_id=user.id, product_id=product_id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "用户名已存在") from None
    return user_out(db, user)


class UserStatusRequest(BaseModel):
    is_active: bool | None = None
    restrict_products: bool | None = None
    product_ids: list[str] | None = None


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user_status(
    user_id: str,
    payload: UserStatusRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(400, "不能停用当前登录账号")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.restrict_products is not None:
        user.restrict_products = payload.restrict_products
    if payload.product_ids is not None:
        validate_products(db, payload.product_ids)
        db.execute(delete(ProductGrant).where(ProductGrant.user_id == user.id))
        for product_id in set(payload.product_ids):
            db.add(ProductGrant(user_id=user.id, product_id=product_id))
    if payload.is_active is False:
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()
    return user_out(db, user)


def validate_products(db, product_ids):
    if set(product_ids) - set(db.scalars(select(Product.id))):
        raise HTTPException(400, "所选产品不存在")


def user_out(db, user):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "restrict_products": user.restrict_products,
        "product_ids": list(
            db.scalars(select(ProductGrant.product_id).where(ProductGrant.user_id == user.id))
        ),
    }
