"""add google_uid to users

Revision ID: 202fbbf89f08
Revises: ddeeff334455
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa

revision = '202fbbf89f08'
down_revision = 'ddeeff334455'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('google_uid', sa.String(128), nullable=True))
    op.alter_column('users', 'phone', nullable=True)
    op.alter_column('users', 'gender', nullable=True)

def downgrade():
    op.drop_column('users', 'google_uid')
