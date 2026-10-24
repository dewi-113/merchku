"""add shipping and payment gateway data

Revision ID: 3d4e5f6a7b8
Revises: 2c3d4e5f6a7
Create Date: 2026-10-22 13:45:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '3d4e5f6a7b8'
down_revision = '2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    product_columns = {column['name'] for column in inspector.get_columns('products')}
    order_columns = {column['name'] for column in inspector.get_columns('orders')}
    with op.batch_alter_table('products') as batch_op:
        if 'weight_gram' not in product_columns:
            batch_op.add_column(
                sa.Column('weight_gram', sa.Integer(), nullable=False, server_default='500')
            )
    with op.batch_alter_table('orders') as batch_op:
        columns = {
            'shipping_service': sa.Column('shipping_service', sa.String(100), nullable=True),
            'shipping_cost': sa.Column(
                'shipping_cost', sa.Integer(), nullable=False, server_default='0'
            ),
            'payment_transaction_id': sa.Column(
                'payment_transaction_id', sa.String(100), nullable=True
            ),
            'payment_token': sa.Column('payment_token', sa.String(255), nullable=True),
            'payment_redirect_url': sa.Column(
                'payment_redirect_url', sa.String(500), nullable=True
            ),
        }
        for name, column in columns.items():
            if name not in order_columns:
                batch_op.add_column(column)
    if 'payment_transaction_id' not in order_columns:
        with op.batch_alter_table('orders') as batch_op:
            batch_op.create_unique_constraint(
                'uq_orders_payment_transaction_id', ['payment_transaction_id']
            )


def downgrade():
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_constraint('uq_orders_payment_transaction_id', type_='unique')
        batch_op.drop_column('payment_redirect_url')
        batch_op.drop_column('payment_token')
        batch_op.drop_column('payment_transaction_id')
        batch_op.drop_column('shipping_cost')
        batch_op.drop_column('shipping_service')
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('weight_gram')
