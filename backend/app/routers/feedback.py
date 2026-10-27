from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..business_schemas import FeedbackUpdate, Rating
from ..core.auth import current_user
from ..core.database import get_db
from ..models import User
from ..services import support

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.put("/messages/{message_id}")
def rate(
    message_id: int,
    payload: FeedbackUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return support.save_feedback(db, user, message_id, payload)


@router.get("")
def list_feedback(
    rating: Rating | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return support.list_feedback(db, user, rating, page, page_size)
