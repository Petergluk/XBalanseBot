"""add_offers_quantity_and_expiry

Revision ID: 794583b4ba0c
Revises: 286e30f35273
Create Date: 2026-06-14 19:44:13.391654

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '794583b4ba0c'
down_revision: Union[str, Sequence[str], None] = '286e30f35273'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE offers ADD COLUMN quantity INTEGER DEFAULT 1 NOT NULL")
    op.execute("ALTER TABLE offers ADD COLUMN expires_at TIMESTAMP WITH TIME ZONE")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE offers DROP COLUMN IF EXISTS expires_at")
    op.execute("ALTER TABLE offers DROP COLUMN IF EXISTS quantity")
