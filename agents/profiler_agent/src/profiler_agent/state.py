"""Typed shapes for the LangGraph state and the `/reply` wire contract.

Mirrors `agent-structure-en.md` section 3 (wire contract) and section 5
(conversation flow / phase values).
"""

from typing import Literal, TypedDict

Phase = Literal["intro", "background", "skills_and_education", "projects", "summary_and_confirm"]
ConversationType = Literal["profiling", "refinement", "application_edit"]
BuildingBlockCategory = Literal["project", "technical_skills", "education", "about_user", "role"]


class MessageIn(TypedDict, total=False):
    sender: str
    content: str
    created_at: str | None


class VariantDict(TypedDict):
    angle: str
    content: str


class BuildingBlockDict(TypedDict, total=False):
    id: str
    category: BuildingBlockCategory
    title: str
    content: str
    variants: list[VariantDict]


class JobCompanyDict(TypedDict, total=False):
    id: int
    name: str
    website: str


class JobDict(TypedDict, total=False):
    id: int
    title: str
    description: str
    requirements: list[str]
    source_url: str
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    employment_type: str | None
    work_arrangement: str | None
    location: str | None
    company: JobCompanyDict


class RequestContextDict(TypedDict, total=False):
    existing_building_blocks: list[BuildingBlockDict] | None
    target_building_block: BuildingBlockDict | None
    job: JobDict | None


class CreatedBlockDict(TypedDict):
    category: BuildingBlockCategory
    title: str
    content: str
    variants: list[VariantDict]


class UpdatedBlockDict(TypedDict):
    id: str
    category: BuildingBlockCategory
    title: str
    content: str
    variants: list[VariantDict]


class AgentState(TypedDict, total=False):
    """LangGraph state for one `/reply` turn.

    `phase` and `summary` are the only fields that persist across turns via
    the checkpointer (agent-structure-en.md section 4) - every other field is
    supplied fresh on each request.
    """

    conversation_id: str
    conversation_type: ConversationType
    user_id: str | None
    message_history: list[MessageIn]
    user_message: str
    building_block_id: str | None
    application_id: str | None
    context: RequestContextDict

    # Persisted across turns via the checkpointer.
    phase: Phase
    summary: str

    # Populated by the `generate` node.
    reply: str
    building_blocks_created: list[CreatedBlockDict]
    building_blocks_updated: list[UpdatedBlockDict]

    # Turn counter, used only for log_event's `message_id`.
    message_id: int
