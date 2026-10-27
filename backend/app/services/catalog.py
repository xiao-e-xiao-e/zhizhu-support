"""产品和版本校验。资料范围在检索前限定。"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, ProductGrant, ProductVersion, User


def allowed_products(db, user_id=None):
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return set()
    if not user.restrict_products:
        return None
    return set(db.scalars(select(ProductGrant.product_id).where(ProductGrant.user_id == user_id)))


def product_visible(db, product_id, user_id=None):
    allowed = allowed_products(db, user_id)
    return allowed is None or product_id in allowed


def validate_scope(db: Session, product_id: str | None, version_id: str | None, user_id=None) -> None:
    if version_id and not product_id:
        raise HTTPException(422, "选择版本时必须选择产品")
    if product_id:
        if not product_visible(db, product_id, user_id):
            raise HTTPException(404, "产品不存在或无访问权限")
        product = db.get(Product, product_id)
        if not product or not product.is_active:
            raise HTTPException(422, "产品不存在或已停用")
    if version_id:
        version = db.get(ProductVersion, version_id)
        if not version or version.product_id != product_id or not version.is_active:
            raise HTTPException(422, "版本不属于该产品或已停用")
