"""Add opaque service credentials and scope grants.

Revision ID: 0003_service_credentials
Revises: 0002_bootstrap_claim
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_service_credentials"
down_revision = "0002_bootstrap_claim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_credentials",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_service_credentials_service_id", "service_credentials", ["service_id"])
    op.create_index(
        "ix_service_credentials_token_hash",
        "service_credentials",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_service_credentials_token_hash", table_name="service_credentials")
    op.drop_index("ix_service_credentials_service_id", table_name="service_credentials")
    op.drop_table("service_credentials")
