"""add seller reply to reviews

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-21 00:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.add_column(sa.Column('seller_reply', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('replied_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_column('replied_at')
        batch_op.drop_column('seller_reply')
