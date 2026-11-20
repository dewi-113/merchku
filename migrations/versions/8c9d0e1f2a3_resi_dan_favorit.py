"""nomor resi pesanan & produk favorit

Revision ID: 8c9d0e1f2a3
Revises: 7b8c9d0e1f2
Create Date: 2026-11-20 12:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '8c9d0e1f2a3'
down_revision = '7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if 'tracking_number' not in {c['name'] for c in insp.get_columns('orders')}:
        op.add_column('orders', sa.Column('tracking_number', sa.String(60), nullable=True))
    if 'wishlists' not in insp.get_table_names():
        op.create_table(
            'wishlists',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('user_id', 'product_id', name='uq_wishlist_user_product'),
        )
        op.create_index('ix_wishlists_user_id', 'wishlists', ['user_id'])


def downgrade():
    op.drop_index('ix_wishlists_user_id', table_name='wishlists')
    op.drop_table('wishlists')
    op.drop_column('orders', 'tracking_number')
