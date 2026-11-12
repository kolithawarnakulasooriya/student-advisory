"""Public typed advising actions. No endpoint, role, or model authority in user inputs."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.intake_schemas import Input, Short

Reason = Annotated[str, Field(min_length=1, max_length=1000)]


class ReviewSource(Input):
    source_version_id: UUID
    reason: Reason


class PublishSource(Input):
    build_id: UUID
    reason: Reason


class BuildOut(BaseModel):
    id: UUID
    source_version_id: UUID
    config_id: UUID
    state: str
    error_code: str | None
    chunk_count: int
    reviewed_by: UUID
    review_reason: str


class PublicationOut(BaseModel):
    source_id: UUID
    version: int
    build_id: UUID | None
    status: str
    builds: list[BuildOut]


class KnowledgeOut(BaseModel):
    version: int
    config_id: UUID | None


class RebuildInput(Input):
    institution_id: UUID
    build_ids: list[UUID] = Field(max_length=1000)
    reason: Reason


class Rule(Input):
    course_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
    kind: Literal["prerequisite", "course_limit"]
    requires: list[Short] = Field(default_factory=list, max_length=30)
    maximum: int | None = Field(default=None, ge=1, le=20)
    evidence_id: UUID

    @model_validator(mode="after")
    def shape(self) -> "Rule":
        if (
            self.kind == "prerequisite"
            and not self.requires
            or self.kind == "course_limit"
            and self.maximum is None
        ):
            raise ValueError("Supply a complete reviewed rule")
        return self


class GovernanceDefinition(Input):
    rules: list[Rule] = Field(default_factory=list, max_length=100)
    terminology: dict[Literal["advisor", "program", "term"], Short] = Field(default_factory=dict)
    clarification_fields: list[
        Literal["program", "catalog_year", "completed_courses", "current_term"]
    ] = Field(default_factory=list, max_length=4)
    style: Literal["concise", "expanded"] = "concise"


class GovernanceInput(Input):
    institution_id: UUID
    org_unit_id: UUID | None = None
    kind: Literal["rules", "preferences", "prompt"]
    definition: GovernanceDefinition

    @model_validator(mode="after")
    def scope(self) -> "GovernanceInput":
        if (self.kind == "prompt") != (self.org_unit_id is None):
            raise ValueError("Only global prompt releases have institution scope")
        if self.kind == "prompt" and (
            self.definition.rules
            or self.definition.terminology
            or self.definition.clarification_fields
        ):
            raise ValueError("Global releases change style only; platform controls are fixed")
        if self.kind == "preferences" and self.definition.rules:
            raise ValueError("Academic rules require their own reviewed release")
        return self


class GovernanceOut(BaseModel):
    id: UUID
    institution_id: UUID
    org_unit_id: UUID | None
    kind: str
    definition: GovernanceDefinition
    active: bool
    evaluation_id: UUID | None
    evaluation_passed: bool
    created_at: datetime


class ActivateInput(Input):
    evaluation_id: UUID
    reason: Reason


class ConversationInput(Input):
    student_membership_id: UUID
    title: Short = "Academic advising"


class ConversationOut(BaseModel):
    id: UUID
    student_membership_id: UUID
    institution_id: UUID
    org_unit_id: UUID
    version: int
    guidance_epoch: int
    title: str
    created_at: datetime


class QuestionInput(Input):
    type: Literal["student_question"] = "student_question"
    text: Annotated[str, Field(min_length=1, max_length=4000)]


class GuidancePreferences(Input):
    max_courses: int | None = Field(default=None, ge=1, le=20)
    prioritize_courses: list[Short] = Field(default_factory=list, max_length=10)
    requested_exception: bool = False


class GuidanceInput(Input):
    type: Literal["student_visible_guidance"] = "student_visible_guidance"
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    supersedes_id: UUID | None = None
    preferences: GuidancePreferences = Field(default_factory=GuidancePreferences)

    @model_validator(mode="after")
    def dates(self) -> "GuidanceInput":
        if any(v and v.tzinfo is None for v in (self.effective_from, self.effective_until)):
            raise ValueError("Timezone is required")
        if (
            self.effective_from
            and self.effective_until
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("Invalid guidance validity")
        return self


class NoteInput(Input):
    type: Literal["staff_only_note"] = "staff_only_note"
    text: Annotated[str, Field(min_length=1, max_length=4000)]


class DraftInput(Input):
    message_id: UUID


class PublishDraft(Input):
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    reviewed: Literal[True]
    effective_until: datetime | None = None


class JobOut(BaseModel):
    id: UUID
    kind: str
    target_id: UUID
    message_id: UUID | None
    conversation_id: UUID | None
    version: int
    attempt: int
    state: str
    error_code: str | None
    created_at: datetime


class AnswerOut(BaseModel):
    id: UUID
    message_id: UUID
    disposition: str
    payload: dict[str, Any]
    created_at: datetime


class MessageOut(BaseModel):
    id: UUID
    author_id: UUID
    author_name: str
    type: Literal["student_question", "student_visible_guidance"]
    text: str
    created_at: datetime
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    supersedes_id: UUID | None = None
    active: bool = True
    preferences: dict[str, Any] = Field(default_factory=dict)
    jobs: list[JobOut] = Field(default_factory=list)
    answers: list[AnswerOut] = Field(default_factory=list)


class NoteOut(BaseModel):
    id: UUID
    author_id: UUID
    text: str
    created_at: datetime


class DraftOut(BaseModel):
    id: UUID
    conversation_id: UUID
    payload: dict[str, Any]
    created_at: datetime


class CitationOut(BaseModel):
    id: UUID
    source_id: UUID
    source_version_id: UUID
    title: str
    locator: dict[str, Any]
    text: str | None
    status: Literal["published", "superseded", "withdrawn"]
    published_at: datetime | None


class CaseInput(Input):
    student_membership_id: UUID
    conversation_id: UUID | None = None
    reason: Reason


class CaseTransition(Input):
    status: Literal[
        "assigned", "in_progress", "waiting_for_student", "resolved", "cancelled", "open"
    ]
    text: Reason


class CaseOut(BaseModel):
    id: UUID
    student_membership_id: UUID
    conversation_id: UUID | None
    institution_id: UUID
    org_unit_id: UUID
    status: str
    version: int
    reason: str
    assigned_advisor_id: UUID | None
    route: Literal["advisor", "manager_queue"]
    created_at: datetime


class CaseEventOut(BaseModel):
    id: UUID
    actor_id: UUID
    status: str
    text: str
    created_at: datetime


class IndexedExcerptOut(BaseModel):
    id: UUID
    source_id: UUID
    source_version_id: UUID
    build_id: UUID
    ordinal: int
    title: str
    text: str
    locator: dict[str, Any]
    published: bool


class PublishedSourceOut(BaseModel):
    source_id: UUID
    source_version_id: UUID
    title: str
    published_at: datetime
