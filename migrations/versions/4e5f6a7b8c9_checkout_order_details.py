"""add checkout breakdown and product details

Revision ID: 4e5f6a7b8c9
Revises: 3d4e5f6a7b8
Create Date: 2026-10-22 21:05:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '4e5f6a7b8c9'
down_revision = '3d4e5f6a7b8'
branch_labels = None
depends_on = None


def _add_missing_columns(table_name, columns):
    existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table_name)}
    missing = [(name, column) for name, column in columns.items() if name not in existing]
    if missing:
        with op.batch_alter_table(table_name) as batch_op:
            for _name, column in missing:
                batch_op.add_column(column)


def upgrade():
    _add_missing_columns('products', {
        'product_type': sa.Column('product_type', sa.String(length=100), nullable=True),
        'color': sa.Column('color', sa.String(length=80), nullable=True),
        'is_fragile': sa.Column(
            'is_fragile', sa.Boolean(), nullable=False, server_default=sa.false(),
        ),
    })
    _add_missing_columns('orders', {
        'shipping_duration': sa.Column('shipping_duration', sa.String(length=100), nullable=True),
        'shipping_discount': sa.Column(
            'shipping_discount', sa.Integer(), nullable=False, server_default='0',
        ),
        'service_fee': sa.Column(
            'service_fee', sa.Integer(), nullable=False, server_default='0',
        ),
        'fragile_protection': sa.Column(
            'fragile_protection', sa.Boolean(), nullable=False, server_default=sa.false(),
        ),
        'fragile_fee': sa.Column(
            'fragile_fee', sa.Integer(), nullable=False, server_default='0',
        ),
    })
    _add_missing_columns('order_items', {
        'product_description': sa.Column('product_description', sa.Text(), nullable=True),
        'product_type': sa.Column('product_type', sa.String(length=100), nullable=True),
        'product_color': sa.Column('product_color', sa.String(length=80), nullable=True),
    })


def downgrade():
    with op.batch_alter_table('order_items') as batch_op:
        batch_op.drop_column('product_color')
        batch_op.drop_column('product_type')
        batch_op.drop_column('product_description')
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_column('fragile_fee')
        batch_op.drop_column('fragile_protection')
        batch_op.drop_column('service_fee')
        batch_op.drop_column('shipping_discount')
        batch_op.drop_column('shipping_duration')
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('is_fragile')
        batch_op.drop_column('color')
        batch_op.drop_column('product_type')
