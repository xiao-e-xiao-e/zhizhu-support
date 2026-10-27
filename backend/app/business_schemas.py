"""客服业务请求契约。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TicketStatus = Literal["new", "in_progress", "resolved", "closed"]
Priority = Literal["low", "normal", "high"]
Rating = Literal["helpful", "unresolved"]


class BusinessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProductCreate(BusinessRequest):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)


class VersionCreate(BusinessRequest):
    name: str = Field(min_length=1, max_length=80)


class ActiveUpdate(BusinessRequest):
    is_active: bool


class KnowledgeScope(BusinessRequest):
    product_id: str | None = Field(default=None, min_length=1, max_length=36)
    version_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def version_requires_product(self):
        if self.version_id and not self.product_id:
            raise ValueError("选择版本时必须选择产品")
        return self


class TicketCreate(KnowledgeScope):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=8000)
    priority: Priority = "normal"
    conversation_name: str | None = Field(default=None, min_length=1, max_length=120)
    message_id: int | None = Field(default=None, gt=0)
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")

    @model_validator(mode="after")
    def message_requires_conversation(self):
        if self.message_id and not self.conversation_name:
            raise ValueError("关联回答时必须提供所属会话")
        return self


class TicketRevision(BusinessRequest):
    expected_revision: int = Field(ge=1)


class StatusUpdate(TicketRevision):
    status: TicketStatus
    note: str = Field(default="", max_length=4000)


class AssignmentUpdate(TicketRevision):
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)


class CommentCreate(TicketRevision):
    content: str = Field(min_length=1, max_length=4000)


class FeedbackUpdate(BusinessRequest):
    rating: Rating
    reason: str = Field(default="", max_length=1000)
