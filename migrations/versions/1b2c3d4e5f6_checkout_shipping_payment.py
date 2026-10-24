"""add checkout shipping and payment choices

Revision ID: 1b2c3d4e5f6
Revises: 0a1b2c3d4e5f
Create Date: 2026-10-22 05:35:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '1b2c3d4e5f6'
down_revision = '0a1b2c3d4e5f'
branch_labels = None
depends_on = None


def upgrade():
    existing_columns = {
        column['name']
        for column in sa.inspect(op.get_bind()).get_columns('orders')
    }
    with op.batch_alter_table('orders', schema=None) as batch_op:
        columns = {
            'address_label': sa.Column(
                'address_label', sa.String(length=20), nullable=False, server_default='rumah'
            ),
            'district': sa.Column('district', sa.String(length=100), nullable=True),
            'city': sa.Column('city', sa.String(length=100), nullable=True),
            'postal_code': sa.Column('postal_code', sa.String(length=10), nullable=True),
            'province': sa.Column('province', sa.String(length=100), nullable=True),
            'delivery_note': sa.Column('delivery_note', sa.String(length=300), nullable=True),
            'courier': sa.Column(
                'courier', sa.String(length=20), nullable=False, server_default='jne'
            ),
            'payment_method': sa.Column(
                'payment_method', sa.String(length=30), nullable=False, server_default='bank_transfer'
            ),
        }
        for name, column in columns.items():
            if name not in existing_columns:
                batch_op.add_column(column)


def downgrade():
    existing_columns = {
        column['name']
        for column in sa.inspect(op.get_bind()).get_columns('orders')
    }
    with op.batch_alter_table('orders', schema=None) as batch_op:
        for name in (
            'payment_method',
            'courier',
            'delivery_note',
            'province',
            'postal_code',
            'city',
            'district',
            'address_label',
        ):
            if name in existing_columns:
                batch_op.drop_column(name)
