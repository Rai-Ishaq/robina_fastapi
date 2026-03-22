"""add fcm token

Revision ID: ddeeff334455
Revises: aabbcc112233
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa

revision = 'ddeeff334455'
down_revision = 'aabbcc112233'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('fcm_token', sa.String(500), nullable=True))

def downgrade():
    op.drop_column('users', 'fcm_token')
