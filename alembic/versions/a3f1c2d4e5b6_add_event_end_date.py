"""add_event_end_date

Revision ID: a3f1c2d4e5b6
Revises: 8178e9c42814
Create Date: 2026-03-05 19:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a3f1c2d4e5b6'
down_revision: Union[str, Sequence[str], None] = '8178e9c42814'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add end_date column to events table."""
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS end_date DATE;")


def downgrade() -> None:
    """Remove end_date column from events table."""
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS end_date;")
