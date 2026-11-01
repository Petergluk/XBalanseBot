"""add scheduled_broadcasts table with RLS and bonus_source_mode setting

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'g2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.scheduled_broadcasts (
            id SERIAL PRIMARY KEY,
            activity_id INTEGER NOT NULL REFERENCES public.activities(id) ON DELETE CASCADE,
            source_chat_id BIGINT NOT NULL,
            source_message_id BIGINT NOT NULL,
            admin_chat_id BIGINT NOT NULL,
            scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_scheduled_broadcasts_pending
        ON public.scheduled_broadcasts (scheduled_at)
        WHERE status = 'pending';
    """)
    op.execute("ALTER TABLE IF EXISTS public.scheduled_broadcasts ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON TABLE public.scheduled_broadcasts FROM anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON TABLE public.scheduled_broadcasts FROM authenticated';
            END IF;
        END
        $$;
    """)
    op.execute("""
        INSERT INTO public.settings (key, value)
        VALUES ('bonus_source_mode', 'stepwise')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.scheduled_broadcasts CASCADE;")
    op.execute("DELETE FROM public.settings WHERE key = 'bonus_source_mode';")
