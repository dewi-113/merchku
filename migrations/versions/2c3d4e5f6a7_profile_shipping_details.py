"""store customer shipping details in profile

Revision ID: 2c3d4e5f6a7
Revises: 1b2c3d4e5f6
Create Date: 2026-10-22 12:50:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '2c3d4e5f6a7'
down_revision = '1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recipient_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('address', sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column('address_label', sa.String(length=20), nullable=False, server_default='rumah')
        )
        batch_op.add_column(sa.Column('district', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('city', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('postal_code', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('province', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('phone', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('delivery_note', sa.String(length=300), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('delivery_note')
        batch_op.drop_column('phone')
        batch_op.drop_column('province')
        batch_op.drop_column('postal_code')
        batch_op.drop_column('city')
        batch_op.drop_column('district')
        batch_op.drop_column('address_label')
        batch_op.drop_column('address')
        batch_op.drop_column('recipient_name')
