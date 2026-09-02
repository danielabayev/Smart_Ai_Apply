"""SQLAlchemy models mirroring the SQL migrations in `api&schema/`.

Covers both `001_user_schema.sql` (users, preferences, conversations,
messages, building_blocks, applications) and `002_company_schema.sql`
(companies, jobs, user_job_scan_cursor) - both schemas live in the
same physical database and are served by this single API process.
These models do not create/alter schema (`db.create_all()` is not
used) - the SQL migration files remain the single source of truth for
the database structure.
"""

import uuid

from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID
from sqlalchemy.sql import func

from api.extensions import db

work_arrangement_enum = ENUM(
    "remote", "hybrid", "onsite", name="work_arrangement_type", create_type=False
)
conversation_type_enum = ENUM(
    "profiling",
    "refinement",
    "application_edit",
    name="conversation_type",
    create_type=False,
)
conversation_status_enum = ENUM(
    "active", "finished", name="conversation_status", create_type=False
)
message_sender_enum = ENUM("user", "agent", name="message_sender", create_type=False)
building_block_category_enum = ENUM(
    "project",
    "technical_skills",
    "education",
    "about_user",
    "role",
    name="building_block_category",
    create_type=False,
)
application_status_enum = ENUM(
    "pending_tailoring",
    "pending_approval",
    "approved",
    "rejected",
    name="application_status",
    create_type=False,
)
company_status_enum = ENUM(
    "active", "flagged_for_review", name="company_status", create_type=False
)
employment_type_enum = ENUM(
    "full_time", "part_time", "contract", name="employment_type_type", create_type=False
)


class User(db.Model):
    """A platform user. MVP has a single mocked user (no real auth)."""

    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    phone_number = db.Column(db.String(50))
    linkedin_url = db.Column(db.String(512))
    github_url = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    preferences = db.relationship(
        "UserPreferences", backref="user", uselist=False, cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "full_name": self.full_name,
            "email": self.email,
            "phone_number": self.phone_number,
            "linkedin_url": self.linkedin_url,
            "github_url": self.github_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class UserPreferences(db.Model):
    """1:1 preferences row for a user, including the job match threshold."""

    __tablename__ = "user_preferences"

    user_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    match_threshold = db.Column(db.SmallInteger, nullable=False, default=70)
    min_salary = db.Column(db.Numeric(12, 2))
    salary_currency = db.Column(db.String(3), default="ILS")
    include_jobs_without_salary = db.Column(db.Boolean, nullable=False, default=True)
    location = db.Column(db.String(255))
    work_arrangement = db.Column(work_arrangement_enum)
    employment_types = db.Column(ARRAY(db.Text), nullable=False, default=list)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "match_threshold": self.match_threshold,
            "min_salary": float(self.min_salary) if self.min_salary is not None else None,
            "salary_currency": self.salary_currency,
            "include_jobs_without_salary": self.include_jobs_without_salary,
            "location": self.location,
            "work_arrangement": self.work_arrangement,
            "employment_types": self.employment_types,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Conversation(db.Model):
    """A conversation thread with Agent 1 (profiling/refinement/edit)."""

    __tablename__ = "conversations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type = db.Column(conversation_type_enum, nullable=False, default="profiling")
    building_block_id = db.Column(UUID(as_uuid=True), db.ForeignKey("building_blocks.id", ondelete="CASCADE"))
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey("applications.id", ondelete="CASCADE"))
    status = db.Column(conversation_status_enum, nullable=False, default="active")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    messages = db.relationship(
        "Message", backref="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )

    def to_dict(self, include_messages: bool = False, include_building_blocks: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "type": self.type,
            "building_block_id": str(self.building_block_id) if self.building_block_id else None,
            "application_id": str(self.application_id) if self.application_id else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_messages:
            data["messages"] = [m.to_dict() for m in self.messages]
        if include_building_blocks:
            blocks = BuildingBlock.query.filter_by(conversation_id=self.id).all()
            data["building_blocks"] = [b.to_dict() for b in blocks]
        return data


class Message(db.Model):
    """A single message within a conversation (user or agent)."""

    __tablename__ = "messages"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender = db.Column(message_sender_enum, nullable=False)
    content = db.Column(db.Text, nullable=False)
    model_used = db.Column(db.String(100))
    response_time_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "sender": self.sender,
            "content": self.content,
            "model_used": self.model_used,
            "response_time_ms": self.response_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BuildingBlock(db.Model):
    """A reusable resume building block (project, skill, education, ...)."""

    __tablename__ = "building_blocks"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    category = db.Column(building_block_category_enum, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    variants = db.Column(JSONB, nullable=False, default=list)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "conversation_id": str(self.conversation_id),
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "variants": self.variants or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Application(db.Model):
    """A tailored-resume application pending user approval."""

    __tablename__ = "applications"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id = db.Column(db.BigInteger, nullable=False)
    match_score = db.Column(db.SmallInteger, nullable=False)
    status = db.Column(application_status_enum, nullable=False, default="pending_tailoring")
    document_content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "job_id": self.job_id,
            "match_score": self.match_score,
            "status": self.status,
            "document_content": self.document_content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ApplicationBuildingBlock(db.Model):
    """Many-to-many link: which building blocks were used in an application."""

    __tablename__ = "application_building_blocks"

    application_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True
    )
    building_block_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("building_blocks.id", ondelete="CASCADE"), primary_key=True
    )


class Company(db.Model):
    """A discovered company, written by Agent 2 (Discovery)."""

    __tablename__ = "companies"

    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    website = db.Column(db.String(512), nullable=False)
    status = db.Column(company_status_enum, nullable=False, default="active")
    last_checked_at = db.Column(db.DateTime)
    last_job_found_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "website": self.website,
            "status": self.status,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "last_job_found_at": self.last_job_found_at.isoformat() if self.last_job_found_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Job(db.Model):
    """An extracted job posting, written by Agent 3 (Extractor).

    `id` is a sequential BIGINT (not a UUID) so Agent 4 can scan jobs
    in order using a simple per-user cursor (see UserJobScanCursor).
    """

    __tablename__ = "jobs"

    id = db.Column(db.BigInteger, primary_key=True)
    company_id = db.Column(db.BigInteger, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(ARRAY(db.Text), nullable=False, default=list)
    source_url = db.Column(db.String(1024), nullable=False)
    salary_min = db.Column(db.Numeric(12, 2))
    salary_max = db.Column(db.Numeric(12, 2))
    salary_currency = db.Column(db.String(3))
    employment_type = db.Column(employment_type_enum)
    work_arrangement = db.Column(work_arrangement_enum)
    location = db.Column(db.String(255))
    discovered_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "title": self.title,
            "description": self.description,
            "requirements": self.requirements,
            "source_url": self.source_url,
            "salary_min": float(self.salary_min) if self.salary_min is not None else None,
            "salary_max": float(self.salary_max) if self.salary_max is not None else None,
            "salary_currency": self.salary_currency,
            "employment_type": self.employment_type,
            "work_arrangement": self.work_arrangement,
            "location": self.location,
            "discovered_at": self.discovered_at.isoformat() if self.discovered_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class UserJobScanCursor(db.Model):
    """Agent 4's per-user scan cursor. Replaces a per-check matches table."""

    __tablename__ = "user_job_scan_cursor"

    user_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_checked_job_id = db.Column(db.BigInteger, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "last_checked_job_id": self.last_checked_job_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
