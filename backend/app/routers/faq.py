"""FAQ 编辑审核与知识发布。"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, select

from ..core.auth import require_staff
from ..core.database import session_factory
from ..models import Feedback, User, iso_utc
from ..services import faq
from ..workflow_schemas import FAQAction, FAQCreate, FAQEdit, FAQRegenerate, FAQReview

router = APIRouter(prefix="/api/faqs", tags=["faq"], dependencies=[Depends(require_staff)])


@router.get("/gaps")
def gaps():
    with session_factory()() as db:
        question = func.lower(func.trim(Feedback.question))
        rows = db.execute(
            select(
                question.label("question"),
                func.count().label("count"),
                func.max(Feedback.updated_at).label("latest"),
                func.sum(case((Feedback.ticket_id.is_not(None), 1), else_=0)).label("tickets"),
            )
            .where(Feedback.rating == "unresolved", question != "")
            .group_by(question)
            .order_by(func.count().desc(), func.max(Feedback.updated_at).desc())
            .limit(20)
        )
        return [
            {
                "question": r.question,
                "count": r.count,
                "linked_tickets": r.tickets,
                "updated_at": iso_utc(r.latest),
            }
            for r in rows
        ]


@router.post("", status_code=201)
def create(payload: FAQCreate, response: Response, user: User = Depends(require_staff)):
    result, created = faq.create(user, payload)
    response.status_code = 202 if created and result["state"] == "generating" else 201 if created else 200
    return result


@router.get("")
def listing(
    state: str | None = Query(None, pattern="^(generating|failed|draft|review|rejected|indexing|published)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_staff),
):
    return faq.listing(user, state, page, page_size)


@router.get("/{faq_id}")
def read(faq_id: str, user: User = Depends(require_staff)):
    return faq.read(user, faq_id)


@router.patch("/{faq_id}")
def edit(faq_id: str, payload: FAQEdit, user: User = Depends(require_staff)):
    return faq.edit(user, faq_id, payload)


@router.post("/{faq_id}/generate")
def generate(faq_id: str, user: User = Depends(require_staff)):
    return faq.generate(user, faq_id)


@router.post("/{faq_id}/regenerate", status_code=202)
def regenerate(faq_id: str, payload: FAQRegenerate, user: User = Depends(require_staff)):
    return faq.regenerate(user, faq_id, payload)


@router.post("/{faq_id}/review")
def review(faq_id: str, payload: FAQReview, user: User = Depends(require_staff)):
    return faq.action(user, faq_id, "review", payload)


@router.post("/{faq_id}/{action}")
def action(faq_id: str, action: str, payload: FAQAction, user: User = Depends(require_staff)):
    if action not in {"submit", "publish", "revise"}:
        raise HTTPException(404, "操作不存在")
    return faq.action(user, faq_id, action, payload)
