"""Bounded inputs; provenance, identities and authority are always server-owned."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Short = Annotated[str, Field(min_length=1, max_length=160)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Question(Input):
    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,59}$")]
    label: Short
    kind: Literal["text", "choice", "courses", "number"] = "text"
    required: bool = False
    choices: list[Short] = Field(default_factory=list, max_length=100)


class Definition(Input):
    fields: list[Question] = Field(min_length=1, max_length=40)
    terms: list[Short] = Field(min_length=1, max_length=100)
    program_tracks: dict[str, list[Short]] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def valid(self) -> "Definition":
        keys = [q.key for q in self.fields]
        if len(keys) != len(set(keys)) or "catalog_year" not in keys or "program" not in keys:
            raise ValueError("Unique questions including program and catalog_year are required")
        reserved = {
            "college",
            "department",
            "institution",
            "verification",
            "ssn",
            "password",
            "health",
            "bank_account",
        }
        for q in self.fields:
            if q.key in reserved or (q.kind == "choice" and not q.choices):
                raise ValueError("Invalid question")
            expected = (
                "choice"
                if q.key in {"program", "track", "catalog_year", "degree_level"}
                else "courses"
                if q.key in {"completed_courses", "current_courses"}
                else "number"
                if q.key == "transfer_credits"
                else "text"
            )
            if q.key in STANDARD and q.kind != expected:
                raise ValueError("Invalid academic field type")
            if q.key in {"program", "catalog_year"} and not q.required:
                raise ValueError("Program and catalog confirmation are required")
        return self


STANDARD = [
    "degree_level",
    "program",
    "track",
    "catalog_year",
    "entry_term",
    "current_term",
    "graduation_term",
    "academic_goals",
    "completed_courses",
    "current_courses",
    "transfer_credits",
    "workload_preferences",
]


def synthetic_definition() -> Definition:
    fields = []
    for key in STANDARD:
        kind: Literal["text", "choice", "courses", "number"] = "text"
        choices: list[str] = []
        if key in {"program", "track", "catalog_year", "degree_level"}:
            kind = "choice"
            choices = {
                "program": ["Synthetic Program"],
                "track": ["Synthetic Track"],
                "catalog_year": ["2026"],
                "degree_level": ["Undergraduate", "Graduate"],
            }[key]
        elif key.endswith("_courses"):
            kind = "courses"
        elif key == "transfer_credits":
            kind = "number"
        fields.append(
            Question(
                key=key,
                label=key.replace("_", " ").title(),
                kind=kind,
                required=key in {"program", "catalog_year"},
                choices=choices,
            )
        )
    return Definition(
        fields=fields,
        terms=["2026 Fall", "2027 Spring"],
        program_tracks={"Synthetic Program": ["Synthetic Track"]},
    )


class SchemaInput(Input):
    definition: Definition
    activate: bool = True


class SchemaOut(BaseModel):
    id: UUID
    version: int
    definition: Definition


class ConfigOut(BaseModel):
    version: int
    active_schema_id: UUID | None
    schemas: list[SchemaOut]


class FactInput(Input):
    value: JsonValue
    effective_term: Short | None = None
    last_confirmed: date | None = None


class ProfileInput(Input):
    schema_id: UUID
    status: Literal["draft", "complete"] = "draft"
    facts: dict[str, FactInput] = Field(max_length=40)
    catalog_confirmed: bool = False


class ReviewInput(Input):
    field: Short
    decision: Literal["confirmed", "disputed"]
    reason: Annotated[str, Field(min_length=1, max_length=1000)]


class FactOut(BaseModel):
    value: JsonValue
    effective_term: str | None = None
    last_confirmed: date | None = None
    source: Literal["student_entered"]
    verification: Literal["self_reported"]
    author_id: UUID
    recorded_at: datetime


class ReviewOut(BaseModel):
    field: str
    decision: Literal["confirmed", "disputed"]
    reason: str
    author_id: UUID
    created_at: datetime


class ProfileOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    student_membership_id: UUID
    institution_id: UUID
    org_unit_id: UUID
    version: int
    context_version: str
    status: str
    profile_schema: SchemaOut | None = Field(alias="schema")
    active_schema_id: UUID | None
    schema_update_available: bool
    missing_fields: list[str]
    facts: dict[str, FactOut]
    reviews: list[ReviewOut]
    created_at: datetime | None = None


class ContextOut(BaseModel):
    context_version: str
    stale: bool


class SourceMetadata(Input):
    title: Short
    program: Short | None = None
    track: Short | None = None
    catalog_start: int | None = Field(default=None, ge=1900, le=2200)
    catalog_end: int | None = Field(default=None, ge=1900, le=2200)
    effective_from: date | None = None
    effective_until: date | None = None
    document_class: Literal["student_evidence", "catalog", "policy", "other"] = "other"
    authority_rank: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def ranges(self) -> "SourceMetadata":
        if self.catalog_start and self.catalog_end and self.catalog_start > self.catalog_end:
            raise ValueError("Invalid catalog range")
        if (
            self.effective_from
            and self.effective_until
            and self.effective_from > self.effective_until
        ):
            raise ValueError("Invalid effective range")
        return self


class SourceTarget(Input):
    institution_id: UUID
    org_unit_id: UUID | None = None
    student_membership_id: UUID | None = None
    visibility: Literal["student", "department", "college", "institution"]
    metadata: SourceMetadata
    source_id: UUID | None = None


class TextInput(SourceTarget):
    text: Annotated[str, Field(min_length=1, max_length=2_000_000)]


class SourceOut(BaseModel):
    id: UUID
    institution_id: UUID
    org_unit_id: UUID | None
    student_membership_id: UUID | None
    visibility: str
    version: int
    source_version_id: UUID
    filename: str
    metadata: SourceMetadata
    state: str
    attempt: int
    error_code: str | None
    archived: bool
    download_available: bool
    artifact_available: bool
    ocr: bool
    created_at: datetime
