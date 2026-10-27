"""工作流的外部请求及工具参数；身份、权限和范围不能由模型指定。"""

from typing import Literal

from pydantic import Field

from .business_schemas import BusinessRequest, KnowledgeScope, Priority


class RunCreate(KnowledgeScope):
    question: str = Field(min_length=1, max_length=4000)
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    session: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[^/\\\x00-\x1f]+$")
    top_k: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0, le=2)
    similarity_threshold: float | None = Field(default=None, ge=0, le=1)


class RetryRun(BusinessRequest):
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class TicketProposal(BusinessRequest):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=8000)
    priority: Priority = "normal"


class ConfirmTicket(TicketProposal):
    confirmed: Literal[True]


class ClarifyQuestion(BusinessRequest):
    question: str = Field(min_length=1, max_length=1000)


class ConversationTool(BusinessRequest):
    """No user-supplied identity, configuration or authorization fields."""


class QueryTool(BusinessRequest):
    query: str = Field(min_length=1, max_length=512)
    top_k: int = Field(default=3, ge=1, le=5)


class TicketStatusTool(BusinessRequest):
    ticket_id: str = Field(min_length=36, max_length=36, pattern=r"^[a-fA-F0-9-]{36}$")


class FAQCreate(BusinessRequest):
    ticket_id: str = Field(min_length=1, max_length=36)
    mode: Literal["model", "manual"] = "model"
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class FAQEdit(BusinessRequest):
    revision: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=240)
    answer: str = Field(min_length=1, max_length=8000)


class FAQAction(BusinessRequest):
    revision: int = Field(ge=1)
    note: str = Field(default="", max_length=1000)


class FAQReview(FAQAction):
    decision: Literal["approve", "reject"]
    reviewed_no_sensitive_data: bool = False


class FAQRegenerate(FAQAction):
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
