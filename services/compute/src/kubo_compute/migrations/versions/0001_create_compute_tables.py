"""Create compute resources, operations, and transactional outbox.

Revision ID: 0001_compute
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_compute"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compute_resources",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("image_key", sa.String(64), nullable=False),
        sa.Column("image_reference", sa.String(512), nullable=False),
        sa.Column("profile_key", sa.String(64), nullable=False),
        sa.Column("cpu_millicores", sa.Integer(), nullable=False),
        sa.Column("memory_bytes", sa.BigInteger(), nullable=False),
        sa.Column("ephemeral_storage_bytes", sa.BigInteger(), nullable=False),
        sa.Column("ports", sa.JSON(), nullable=False),
        sa.Column("desired_state", sa.String(16), nullable=False),
        sa.Column("observed_state", sa.String(16), nullable=False),
        sa.Column("provider_resource_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "desired_state IN ('running', 'stopped', 'terminated')",
            name="ck_compute_resources_desired_state",
        ),
        sa.CheckConstraint(
            "observed_state IN ('requested', 'provisioning', 'running', 'stopping', "
            "'stopped', 'starting', 'terminating', 'terminated', 'failed')",
            name="ck_compute_resources_observed_state",
        ),
        sa.CheckConstraint("cpu_millicores > 0", name="ck_compute_resources_cpu_positive"),
        sa.CheckConstraint("memory_bytes > 0", name="ck_compute_resources_memory_positive"),
        sa.CheckConstraint(
            "ephemeral_storage_bytes > 0",
            name="ck_compute_resources_storage_positive",
        ),
    )
    op.create_index("ix_compute_resources_organization_id", "compute_resources", ["organization_id"])
    op.create_index(
        "ix_compute_resources_provider_resource_id",
        "compute_resources",
        ["provider_resource_id"],
        unique=True,
    )

    op.create_table(
        "compute_operations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("compute_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("initiated_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('create', 'start', 'stop', 'delete')",
            name="ck_compute_operations_action",
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'running', 'succeeded', 'failed')",
            name="ck_compute_operations_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_compute_operations_attempt_count"),
        sa.ForeignKeyConstraint(["compute_id"], ["compute_resources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id",
            "initiated_by",
            "idempotency_key",
            name="uq_compute_operations_idempotency",
        ),
    )
    op.create_index("ix_compute_operations_compute_id", "compute_operations", ["compute_id"])
    op.create_index("ix_compute_operations_initiated_by", "compute_operations", ["initiated_by"])
    op.create_index("ix_compute_operations_org_id", "compute_operations", ["organization_id"])
    op.create_index(
        "ix_compute_operations_due",
        "compute_operations",
        ["status", "next_attempt_at"],
    )

    op.create_table(
        "compute_outbox",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("operation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "publish_attempts >= 0",
            name="ck_compute_outbox_publish_attempts",
        ),
        sa.ForeignKeyConstraint(["operation_id"], ["compute_operations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("operation_id", name="uq_compute_outbox_operation"),
    )
    op.create_index(
        "ix_compute_outbox_due",
        "compute_outbox",
        ["published_at", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_compute_outbox_due", table_name="compute_outbox")
    op.drop_table("compute_outbox")
    op.drop_index("ix_compute_operations_due", table_name="compute_operations")
    op.drop_index("ix_compute_operations_org_id", table_name="compute_operations")
    op.drop_index("ix_compute_operations_initiated_by", table_name="compute_operations")
    op.drop_index("ix_compute_operations_compute_id", table_name="compute_operations")
    op.drop_table("compute_operations")
    op.drop_index("ix_compute_resources_provider_resource_id", table_name="compute_resources")
    op.drop_index("ix_compute_resources_organization_id", table_name="compute_resources")
    op.drop_table("compute_resources")
