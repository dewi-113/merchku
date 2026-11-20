"""buku alamat (banyak alamat per akun)

Revision ID: 7b8c9d0e1f2
Revises: 6a7b8c9d0e1
Create Date: 2026-11-20 11:00:00.000000

Alamat lama di tabel users dipindahkan otomatis ke tabel ini saat pengguna
pertama kali membuka profil/checkout (lihat app/profil/models.py).
"""
import sqlalchemy as sa
from alembic import op

revision = '7b8c9d0e1f2'
down_revision = '6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    if 'addresses' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'addresses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recipient_name', sa.String(200), nullable=False),
        sa.Column('phone', sa.String(30), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('address_label', sa.String(20), nullable=False, server_default='rumah'),
        sa.Column('district', sa.String(100), nullable=False),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('province', sa.String(100), nullable=False),
        sa.Column('postal_code', sa.String(10), nullable=False),
        sa.Column('delivery_note', sa.String(300), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_addresses_user_id', 'addresses', ['user_id'])


def downgrade():
    op.drop_index('ix_addresses_user_id', table_name='addresses')
    op.drop_table('addresses')
