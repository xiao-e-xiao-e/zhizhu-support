"""工单接口；所有变更通过服务层检查归属、角色和版本。"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..business_schemas import AssignmentUpdate, CommentCreate, StatusUpdate, TicketCreate, TicketStatus
from ..core.auth import current_user, require_staff
from ..core.database import get_db
from ..models import Ticket, TicketEvent, User, iso_utc
from ..services import support

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("/assignees")
def assignees(_staff: User = Depends(require_staff), db: Session = Depends(get_db)):
    users = db.scalars(
        select(User)
        .where(User.is_active.is_(True), User.role.in_(["admin", "staff"]))
        .order_by(User.username)
    ).all()
    return [{"id": u.id, "username": u.username} for u in users]


@router.post("", status_code=201)
def create(
    payload: TicketCreate,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    result, created = support.create_ticket(db, user, payload)
    response.status_code = 201 if created else 200
    return result


@router.get("")
def list_tickets(
    status: TicketStatus | None = None,
    product_id: str | None = None,
    mine: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conditions = []
    if not support.is_staff(user) or mine:
        conditions.append(Ticket.creator_id == user.id)
    if status:
        conditions.append(Ticket.status == status)
    if product_id:
        conditions.append(Ticket.product_id == product_id)
    total = db.scalar(select(func.count()).select_from(Ticket).where(*conditions))
    rows = db.scalars(
        select(Ticket)
        .where(*conditions)
        .order_by(Ticket.updated_at.desc(), Ticket.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": support.ticket_outputs(db, rows), "total": total, "page": page, "page_size": page_size}


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return support.ticket_output(db, support.visible_ticket(db, user, ticket_id))


@router.get("/{ticket_id}/events")
def events(
    ticket_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    support.visible_ticket(db, user, ticket_id)
    condition = TicketEvent.ticket_id == ticket_id
    total = db.scalar(select(func.count()).select_from(TicketEvent).where(condition))
    rows = db.scalars(
        select(TicketEvent)
        .where(condition)
        .order_by(TicketEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    actors = {
        u.id: u.username for u in db.scalars(select(User).where(User.id.in_({r.actor_id for r in rows})))
    }
    return {
        "items": [
            {
                "id": r.id,
                "kind": r.kind,
                "content": r.content,
                "details": r.details,
                "actor_name": actors[r.actor_id],
                "created_at": iso_utc(r.created_at),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{ticket_id}/status")
def change_status(
    ticket_id: str, payload: StatusUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return support.change_status(db, user, ticket_id, payload)


@router.post("/{ticket_id}/assignee")
def assign(
    ticket_id: str,
    payload: AssignmentUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return support.assign_ticket(db, user, ticket_id, payload)


@router.post("/{ticket_id}/comments", status_code=201)
def comment(
    ticket_id: str, payload: CommentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return support.add_comment(db, user, ticket_id, payload)
