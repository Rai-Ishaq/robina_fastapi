"""add call logs

Revision ID: f2f5c5f54db7
Revises: 
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f2f5c5f54db7'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'call_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('caller_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('receiver_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('call_type', sa.String(), nullable=True, default='audio'),
        sa.Column('status', sa.String(), nullable=True, default='missed'),
        sa.Column('duration_seconds', sa.String(), nullable=True, default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('call_logs')
