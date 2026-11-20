"""notifikasi (ikon lonceng)

Revision ID: 9d0e1f2a3b4
Revises: 8c9d0e1f2a3
Create Date: 2026-11-20 13:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '9d0e1f2a3b4'
down_revision = '8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    if 'notifications' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message', sa.String(300), nullable=False),
        sa.Column('link', sa.String(255), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_is_read', 'notifications', ['is_read'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])


def downgrade():
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_notifications_is_read', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')
