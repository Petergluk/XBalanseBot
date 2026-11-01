"""add unique active username partial index

Revision ID: h3c4d5e6f7a8
Revises: g2b3c4d5e6f7
Create Date: 2026-11-01 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'h3c4d5e6f7a8'
down_revision: Union[str, None] = 'g2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем устаревшие дубликаты перед созданием уникального индекса
    op.execute("""
        WITH ranked AS (
            SELECT id, LOWER(username) AS luser,
                   ROW_NUMBER() OVER(PARTITION BY LOWER(username) ORDER BY id DESC) as rn
            FROM users
            WHERE username IS NOT NULL
        )
        UPDATE users
        SET username = NULL
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_unique_active_username ON users (LOWER(username)) WHERE username IS NOT NULL;")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_unique_active_username;")
