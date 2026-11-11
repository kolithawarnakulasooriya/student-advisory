from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["student", "advisor", "secretary", "manager", "platform_admin", "super_admin"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(Input):
    email: str = Field(min_length=6, max_length=254)

    @field_validator("email")
    @classmethod
    def synthetic_email(cls, email: str) -> str:
        # Preserve local-part dots, plus signs and case. No provider-specific rewriting.
        local, separator, domain = email.strip().rpartition("@")
        if not separator or not local or not domain.lower().endswith(".test"):
            raise ValueError("Use a synthetic address ending in .test")
        if any(c.isspace() for c in local + domain) or "@" in local:
            raise ValueError("Invalid synthetic email")
        return local + "@" + domain.lower()


class RegisterInput(EmailInput):
    name: str = Field(min_length=1, max_length=100)


class VerifyInput(Input):
    challenge: str = Field(min_length=20, max_length=200)


class CsrfOut(BaseModel):
    csrf_token: str


class StatusOut(BaseModel):
    status: str


class RegistrationOut(BaseModel):
    status: Literal["verification_required"] = "verification_required"
    simulator_challenge: str


class GrantOut(BaseModel):
    id: UUID
    institution_id: UUID
    org_unit_id: UUID
    role: Role
    status: str


class ScopeOut(BaseModel):
    id: UUID
    institution_id: UUID
    name: str
    kind: str
    timezone: str


class MeOut(BaseModel):
    user_id: UUID
    email: str
    name: str
    verified: bool
    account_state: str
    membership_state: str
    mfa_required: bool
    recent_auth: bool
    grant_epoch: int
    active_scope: UUID | None
    active_grants: list[GrantOut]
    memberships: list[GrantOut]
    capabilities: list[str]
    scopes: list[ScopeOut]
    expires_at: datetime
    identity_mode: Literal["synthetic"] = "synthetic"


class ScopeInput(Input):
    org_unit_id: UUID


class ErrorOut(BaseModel):
    code: str
    message: str
    field_errors: list[str] = []
    correlation_id: str
