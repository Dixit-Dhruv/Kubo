"""Add a database-enforced one-time initial-admin bootstrap claim.

Revision ID: 0002_bootstrap_claim
Revises: 0001_iam
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_bootstrap_claim"
down_revision = "0001_iam"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_claims",
        sa.Column("name", sa.String(64), primary_key=True, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bootstrap_claims")
