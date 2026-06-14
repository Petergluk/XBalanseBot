"""add_offers_table

Revision ID: 286e30f35273
Revises: e694a49f88ea
Create Date: 2026-06-14 17:25:50.708018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '286e30f35273'
down_revision: Union[str, Sequence[str], None] = 'e694a49f88ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id SERIAL PRIMARY KEY,
            seller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            price NUMERIC(18, 4) NOT NULL,
            photo_id TEXT,
            status VARCHAR(20) DEFAULT 'active',
            buyer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            message_id BIGINT,
            chat_id BIGINT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS offers CASCADE")
