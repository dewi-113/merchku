"""add shop profile to users

Revision ID: d4e5f6a7b8c9
Revises: 1bf3e246b670
Create Date: 2026-10-21 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = '1bf3e246b670'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shop_name', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('shop_description', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('shop_description')
        batch_op.drop_column('shop_name')
