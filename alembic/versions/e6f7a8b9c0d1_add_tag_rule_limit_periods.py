"""add tag rule limit periods

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-03-26 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Переименовываем daily_limit в limit_amount
    op.alter_column('tag_rules', 'daily_limit', new_column_name='limit_amount')
    # Добавляем limit_period_days
    op.add_column('tag_rules', sa.Column('limit_period_days', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('tag_rules', 'limit_period_days')
    op.alter_column('tag_rules', 'limit_amount', new_column_name='daily_limit')
