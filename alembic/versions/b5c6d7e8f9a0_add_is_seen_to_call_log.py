"""add is_seen to call_log

Revision ID: b5c6d7e8f9a0
Revises: 202fbbf89f08
Create Date: 2026-03-29 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b5c6d7e8f9a0'
down_revision = '202fbbf89f08'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('call_logs', sa.Column('is_seen', sa.Boolean(), server_default='false', nullable=True))

def downgrade():
    op.drop_column('call_logs', 'is_seen')
