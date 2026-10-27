"""产品目录。客服维护，登录用户读取。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..business_schemas import ActiveUpdate, ProductCreate, VersionCreate
from ..core.auth import current_user, require_staff
from ..core.database import get_db
from ..models import Product, ProductVersion, User
from ..services.catalog import product_visible

router = APIRouter(prefix="/api/products", tags=["products"])


def product_out(product, versions):
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "is_active": product.is_active,
        "versions": [{"id": v.id, "name": v.name, "is_active": v.is_active} for v in versions],
    }


def commit_unique(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "名称已存在") from None


@router.get("")
def list_products(user: User = Depends(current_user), db: Session = Depends(get_db)):
    products = db.scalars(select(Product).order_by(Product.created_at)).all()
    versions = db.scalars(select(ProductVersion).order_by(ProductVersion.created_at)).all()
    staff = user.role in {"admin", "staff"}
    return [
        product_out(p, [v for v in versions if v.product_id == p.id and (staff or v.is_active)])
        for p in products
        if (staff or p.is_active) and product_visible(db, p.id, user.id)
    ]


@router.post("", status_code=201)
def create_product(
    payload: ProductCreate, _staff: User = Depends(require_staff), db: Session = Depends(get_db)
):
    product = Product(**payload.model_dump())
    db.add(product)
    commit_unique(db)
    return product_out(product, [])


@router.patch("/{product_id}")
def update_product(
    product_id: str,
    payload: ActiveUpdate,
    _staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product or not product_visible(db, product_id, _staff.id):
        raise HTTPException(404, "产品不存在")
    product.is_active = payload.is_active
    db.commit()
    return {"id": product.id, "is_active": product.is_active}


@router.post("/{product_id}/versions", status_code=201)
def create_version(
    product_id: str,
    payload: VersionCreate,
    _staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product or not product.is_active or not product_visible(db, product_id, _staff.id):
        raise HTTPException(404, "产品不存在或已停用")
    version = ProductVersion(product_id=product_id, name=payload.name)
    db.add(version)
    commit_unique(db)
    return {"id": version.id, "name": version.name, "is_active": version.is_active}


@router.patch("/{product_id}/versions/{version_id}")
def update_version(
    product_id: str,
    version_id: str,
    payload: ActiveUpdate,
    _staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    version = db.get(ProductVersion, version_id)
    if not version or version.product_id != product_id or not product_visible(db, product_id, _staff.id):
        raise HTTPException(404, "版本不存在")
    version.is_active = payload.is_active
    db.commit()
    return {"id": version.id, "is_active": version.is_active}
