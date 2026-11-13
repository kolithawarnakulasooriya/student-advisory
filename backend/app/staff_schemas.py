from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas import EmailInput, Input

RequestedRole = Literal["student", "advisor", "manager"]
StaffRole = Literal["student", "advisor", "secretary", "manager", "platform_admin"]
Purpose = Literal["administration", "support_review", "access_investigation"]


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None
    total: int


class OptionOut(BaseModel):
    id: UUID
    institution_id: UUID
    name: str


class RequestInput(Input):
    org_unit_id: UUID
    requested_role: RequestedRole
    justification: str = Field(min_length=1, max_length=1000)


class DecisionInput(Input):
    reason: str = Field(min_length=1, max_length=500)
    advisor_grant_id: UUID | None = None


class InviteInput(EmailInput):
    org_unit_id: UUID
    role: Literal["student", "advisor", "secretary", "manager"]
    advisor_grant_id: UUID | None = None
    capabilities: list[str] = Field(default_factory=list, max_length=20)


class AcceptInput(Input):
    token: str = Field(min_length=40, max_length=200)


class ReasonInput(Input):
    reason: str = Field(min_length=1, max_length=500)


class LifecycleInput(ReasonInput):
    status: Literal["active", "suspended", "revoked"]
    advisor_grant_id: UUID | None = None


class AccountInput(ReasonInput):
    status: Literal["active", "suspended"]
    approved_grant_ids: list[UUID] = Field(default_factory=list, max_length=100)


class AssignmentInput(ReasonInput):
    advisor_grant_id: UUID


class GrantInput(ReasonInput):
    user_id: UUID
    org_unit_id: UUID
    role: StaffRole
    capabilities: list[str] = Field(default_factory=list, max_length=25)
    ceiling: Literal["student", "advisor", "manager"] = "advisor"
    capacity: int | None = Field(default=None, ge=1)
    advisor_grant_id: UUID | None = None


class DelegationInput(ReasonInput):
    capabilities: list[str] = Field(default_factory=list, max_length=25)
    ceiling: Literal["student", "advisor", "manager"] = "advisor"
    capacity: int | None = Field(default=None, ge=1)


class PlatformInput(ReasonInput):
    user_id: UUID


class MemberOut(BaseModel):
    account_state: str
    id: UUID
    student_membership_id: UUID | None
    user_id: UUID
    institution_id: UUID
    org_unit_id: UUID
    name: str
    email: str
    role: str
    status: str
    version: int
    capabilities: list[str]
    ceiling: str
    capacity: int | None
    advisor_grant_id: UUID | None
    advisor_name: str | None
    relationship_epoch: int


class StudentOut(BaseModel):
    id: UUID
    user_id: UUID
    institution_id: UUID
    org_unit_id: UUID
    name: str
    email: str
    status: str
    advisor_grant_id: UUID | None
    advisor_name: str | None
    relationship_epoch: int
    version: int


class AdvisorOut(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str
    capacity: int | None
    assigned_count: int


class RequestOut(BaseModel):
    id: UUID
    user_id: UUID
    org_unit_id: UUID
    requested_role: str
    justification: str
    status: str
    decision_reason: str | None
    version: int
    name: str
    email: str


class InviteOut(BaseModel):
    id: UUID
    org_unit_id: UUID
    email: str
    role: str
    status: str
    version: int
    expires_at: datetime
    advisor_grant_id: UUID | None
    capabilities: list[str]


class AuditOut(BaseModel):
    id: int
    actor_id: UUID | None
    action: str
    object_type: str
    object_id: str | None
    org_unit_id: UUID | None
    result: str
    reason_code: str
    correlation_id: str
    reason: str | None = None
    occurred_at: datetime


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    status: str
    verified: bool
    grant_epoch: int


class PlatformOut(BaseModel):
    id: UUID
    user_id: UUID
    status: str
    version: int


class Outcome(BaseModel):
    status: str
    id: UUID | None = None


class AssignmentState(BaseModel):
    id: UUID
    version: int
    relationship_epoch: int
