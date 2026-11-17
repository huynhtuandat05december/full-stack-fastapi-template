"""add deleted_at soft delete

Revision ID: a1b2c3d4e5f6
Revises: fe56fa70289e
Create Date: 2026-11-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'fe56fa70289e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('item', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_item_deleted_at'), 'item', ['deleted_at'])
    op.create_index(op.f('ix_user_deleted_at'), 'user', ['deleted_at'])


def downgrade():
    op.drop_index(op.f('ix_user_deleted_at'), table_name='user')
    op.drop_index(op.f('ix_item_deleted_at'), table_name='item')
    op.drop_column('user', 'deleted_at')
    op.drop_column('item', 'deleted_at')
