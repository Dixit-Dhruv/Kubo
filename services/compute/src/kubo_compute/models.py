from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kubo_compute.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class DesiredState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"


class ObservedState(StrEnum):
    REQUESTED = "requested"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    STARTING = "starting"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"


class OperationAction(StrEnum):
    CREATE = "create"
    START = "start"
    STOP = "stop"
    DELETE = "delete"


class OperationStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ComputeResource(Base):
    __tablename__ = "compute_resources"
    __table_args__ = (
        CheckConstraint(
            "desired_state IN ('running', 'stopped', 'terminated')",
            name="ck_compute_resources_desired_state",
        ),
        CheckConstraint(
            "observed_state IN ('requested', 'provisioning', 'running', 'stopping', "
            "'stopped', 'starting', 'terminating', 'terminated', 'failed')",
            name="ck_compute_resources_observed_state",
        ),
        CheckConstraint("cpu_millicores > 0", name="ck_compute_resources_cpu_positive"),
        CheckConstraint("memory_bytes > 0", name="ck_compute_resources_memory_positive"),
        CheckConstraint(
            "ephemeral_storage_bytes > 0",
            name="ck_compute_resources_storage_positive",
        ),
        Index(
            "ix_compute_resources_provider_resource_id",
            "provider_resource_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    image_key: Mapped[str] = mapped_column(String(64), nullable=False)
    image_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(64), nullable=False)
    cpu_millicores: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ephemeral_storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ports: Mapped[list[dict[str, int | str]]] = mapped_column(JSON, nullable=False, default=list)
    desired_state: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_state: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_resource_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    operations: Mapped[list["ComputeOperation"]] = relationship(back_populates="resource")


class ComputeOperation(Base):
    __tablename__ = "compute_operations"
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'start', 'stop', 'delete')",
            name="ck_compute_operations_action",
        ),
        CheckConstraint(
            "status IN ('accepted', 'running', 'succeeded', 'failed')",
            name="ck_compute_operations_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_compute_operations_attempt_count"),
        UniqueConstraint(
            "organization_id",
            "initiated_by",
            "idempotency_key",
            name="uq_compute_operations_idempotency",
        ),
        Index("ix_compute_operations_org_id", "organization_id"),
        Index("ix_compute_operations_due", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    compute_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("compute_resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    initiated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    resource: Mapped[ComputeResource] = relationship(back_populates="operations")
    outbox_event: Mapped["OutboxEvent | None"] = relationship(back_populates="operation", uselist=False)


class OutboxEvent(Base):
    __tablename__ = "compute_outbox"
    __table_args__ = (
        CheckConstraint("publish_attempts >= 0", name="ck_compute_outbox_publish_attempts"),
        UniqueConstraint("operation_id", name="uq_compute_outbox_operation"),
        Index("ix_compute_outbox_due", "published_at", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("compute_operations.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    operation: Mapped[ComputeOperation] = relationship(back_populates="outbox_event")
