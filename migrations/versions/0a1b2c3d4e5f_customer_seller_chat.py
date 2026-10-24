"""add customer and seller chat

Revision ID: 0a1b2c3d4e5f
Revises: f6a7b8c9d0e1
Create Date: 2026-10-22 04:22:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '0a1b2c3d4e5f'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('chat_threads'):
        op.create_table(
            'chat_threads',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=False),
            sa.Column('seller_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['customer_id'], ['users.id']),
            sa.ForeignKeyConstraint(['seller_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('customer_id', 'seller_id', name='uq_chat_customer_seller'),
        )

    for index_name, column in (
        ('ix_chat_threads_customer_id', 'customer_id'),
        ('ix_chat_threads_seller_id', 'seller_id'),
    ):
        indexes = {
            index['name'] for index in sa.inspect(op.get_bind()).get_indexes('chat_threads')
        }
        if index_name not in indexes:
            op.create_index(index_name, 'chat_threads', [column], unique=False)

    if not sa.inspect(op.get_bind()).has_table('chat_messages'):
        op.create_table(
            'chat_messages',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('thread_id', sa.Integer(), nullable=False),
            sa.Column('sender_id', sa.Integer(), nullable=False),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['sender_id'], ['users.id']),
            sa.ForeignKeyConstraint(['thread_id'], ['chat_threads.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    for index_name, column in (
        ('ix_chat_messages_sender_id', 'sender_id'),
        ('ix_chat_messages_thread_id', 'thread_id'),
    ):
        indexes = {
            index['name'] for index in sa.inspect(op.get_bind()).get_indexes('chat_messages')
        }
        if index_name not in indexes:
            op.create_index(index_name, 'chat_messages', [column], unique=False)


def downgrade():
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chat_messages_thread_id'))
        batch_op.drop_index(batch_op.f('ix_chat_messages_sender_id'))
    op.drop_table('chat_messages')
    with op.batch_alter_table('chat_threads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chat_threads_seller_id'))
        batch_op.drop_index(batch_op.f('ix_chat_threads_customer_id'))
    op.drop_table('chat_threads')
