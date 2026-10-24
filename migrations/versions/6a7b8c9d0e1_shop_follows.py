"""shop follows (pengikut toko)

Revision ID: 6a7b8c9d0e1
Revises: 5f6a7b8c9d0
Create Date: 2026-10-24 20:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '6a7b8c9d0e1'
down_revision = '5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    if 'shop_follows' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'shop_follows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('seller_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('follower_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('seller_id', 'follower_id', name='uq_shop_follow'),
    )
    op.create_index('ix_shop_follows_seller_id', 'shop_follows', ['seller_id'])
    op.create_index('ix_shop_follows_follower_id', 'shop_follows', ['follower_id'])


def downgrade():
    op.drop_index('ix_shop_follows_follower_id', table_name='shop_follows')
    op.drop_index('ix_shop_follows_seller_id', table_name='shop_follows')
    op.drop_table('shop_follows')
