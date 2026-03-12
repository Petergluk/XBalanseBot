"""alter_events_weekday_to_varchar

Revision ID: 8178e9c42814
Revises: af1c06b2d712
Create Date: 2026-03-04 18:18:21.644918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8178e9c42814'
down_revision: Union[str, Sequence[str], None] = 'af1c06b2d712'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE events ALTER COLUMN weekday TYPE VARCHAR(255);")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE events ALTER COLUMN weekday TYPE INTEGER USING weekday::integer;")
