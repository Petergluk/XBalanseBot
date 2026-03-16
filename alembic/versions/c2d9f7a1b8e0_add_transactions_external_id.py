"""add_transactions_external_id

Revision ID: c2d9f7a1b8e0
Revises: b4d2e3f5a6c7
Create Date: 2026-03-16 18:20:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c2d9f7a1b8e0"
down_revision: Union[str, Sequence[str], None] = "b4d2e3f5a6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS external_id TEXT;")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_type_external_id
        ON transactions (type, external_id)
        WHERE external_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_transactions_type_external_id;")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS external_id;")

