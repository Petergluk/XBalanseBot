"""add_welcome_bonus_unique_index

Revision ID: a4541b05fb21
Revises: 794583b4ba0c
Create Date: 2026-06-15 14:57:12.279653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4541b05fb21'
down_revision: Union[str, Sequence[str], None] = '794583b4ba0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_welcome_bonus "
        "ON transactions (to_user_id) "
        "WHERE type = 'welcome_bonus';"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS uq_transactions_welcome_bonus;")
