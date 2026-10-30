"""本人助手运行与显式确认接口；工具不暴露为可任意调用的端点。"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..core.auth import current_user
from ..core.database import session_factory
from ..models import User
from ..services import agent
from ..workflow_schemas import ConfirmTicket, RetryRun, RunCreate
from .chat import SSE_HEADERS

router = APIRouter(prefix="/api/agent/runs", tags=["assistant"])


@router.post("", status_code=202)
def create(payload: RunCreate, user: User = Depends(current_user)):
    return agent.create_run(user, payload)


@router.get("")
def listing(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(current_user)
):
    return agent.list_runs(user, page, page_size)


@router.get("/{run_id}")
def get_run(run_id: str, user: User = Depends(current_user)):
    return agent.get_run(user, run_id)


def preflight(user, run_id):
    with session_factory()() as db:
        run = agent.visible_run(db, user, run_id)
        if run.owner_id != user.id or run.kind != "assistant":
            raise HTTPException(404, "助手任务不存在")


@router.post("/{run_id}/execute")
def execute(run_id: str, user: User = Depends(current_user)):
    preflight(user, run_id)
    for _ in agent.execute(user, run_id):
        pass
    return agent.get_run(user, run_id)


@router.post("/{run_id}/stream")
def stream(run_id: str, user: User = Depends(current_user)):
    preflight(user, run_id)

    def events():
        iterator = agent.execute(user, run_id)
        try:
            for event in iterator:
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except HTTPException as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc.detail)}, ensure_ascii=False)}\n\n"
        finally:
            iterator.close()

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/{run_id}/cancel")
def cancel(run_id: str, user: User = Depends(current_user)):
    return agent.cancel_run(user, run_id)


@router.post("/{run_id}/retry", status_code=202)
def retry(run_id: str, payload: RetryRun, user: User = Depends(current_user)):
    return agent.retry_run(user, run_id, payload.request_key)


@router.post("/{run_id}/confirm-ticket")
def confirm_ticket(run_id: str, payload: ConfirmTicket, user: User = Depends(current_user)):
    return agent.confirm_ticket(user, run_id, payload)
