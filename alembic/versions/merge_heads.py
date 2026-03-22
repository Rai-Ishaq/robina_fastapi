"""merge heads

Revision ID: aabbcc112233
Revises: 47e6e8293eb0, f2f5c5f54db7
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa

revision = 'aabbcc112233'
down_revision = ('47e6e8293eb0', 'f2f5c5f54db7')
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
