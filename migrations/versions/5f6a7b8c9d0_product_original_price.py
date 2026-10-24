"""add original_price (harga coret) to products

Revision ID: 5f6a7b8c9d0
Revises: 4e5f6a7b8c9
Create Date: 2026-10-24 18:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '5f6a7b8c9d0'
down_revision = '4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('products')}
    if 'original_price' not in existing:
        with op.batch_alter_table('products') as batch_op:
            batch_op.add_column(sa.Column('original_price', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('original_price')
