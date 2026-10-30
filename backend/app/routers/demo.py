"""仅在显式本地演示模式提供公开体验账号。"""

from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import current_user
from ..core.config import get_settings
from ..models import User
from ..services import demo

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("")
def info():
    return demo.public_info()


@router.get("/guide")
def guide(user: User = Depends(current_user)):
    if not get_settings().demo_mode:
        raise HTTPException(404, "演示模式未开启")
    return demo.guide(user)
