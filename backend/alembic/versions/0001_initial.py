"""Initial coaching platform schema.

Revision ID: 0001_initial
Revises: None
"""
from alembic import op
from app.database import Base
from app import models  # noqa: F401


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Intentionally non-destructive. Production rollback restores the prior app
    # image while preserving data; a human must approve any schema deletion.
    pass
