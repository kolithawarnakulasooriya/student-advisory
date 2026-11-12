from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas import Input
from app.staff_schemas import ReasonInput


class OrganizationMetadata(ReasonInput):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=80)
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid timezone") from None
        return value


class OrganizationCreate(OrganizationMetadata):
    institution_id: UUID
    kind: Literal["college", "department"]
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def hierarchy(self) -> "OrganizationCreate":
        if (self.kind == "college") != (self.parent_id is None):
            raise ValueError("Departments require a college parent; colleges are roots")
        return self


class EnrollmentInput(ReasonInput):
    enabled: bool


class OrganizationOut(BaseModel):
    id: UUID
    institution_id: UUID
    parent_id: UUID | None
    name: str
    code: str
    kind: str
    timezone: str
    status: str
    version: int
    enrollment_enabled: bool


class InstitutionOut(BaseModel):
    id: UUID
    code: str
    name: str
    organization_epoch: int


class OrganizationGrantInput(ReasonInput):
    user_id: UUID
    institution_id: UUID
    scope_kind: Literal["institution", "college"]
    root_org_unit_id: UUID | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def root(self) -> "OrganizationGrantInput":
        if (self.scope_kind == "institution") != (self.root_org_unit_id is None):
            raise ValueError("Select an explicit institution or college root")
        if self.valid_until and self.valid_until.utcoffset() is None:
            raise ValueError("Expiry requires a timezone")
        return self


class OrganizationGrantOut(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    user_id: UUID
    institution_id: UUID
    scope_kind: str
    root_org_unit_id: UUID | None
    status: str
    version: int
    valid_until: datetime | None


class OrganizationGrantState(Input):
    status: Literal["active", "suspended", "revoked"]
    reason: str = Field(min_length=1, max_length=500)
