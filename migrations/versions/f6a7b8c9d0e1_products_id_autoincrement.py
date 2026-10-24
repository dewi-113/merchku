"""products id autoincrement

Ganti primary key produk dari ID acak (random 31-bit, diisi di sisi Python)
menjadi AUTO_INCREMENT basis data. ID acak berisiko tabrakan dan membuat
lookup produk tidak urut.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-22 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    """
    MySQL/MariaDB: ubah kolom id menjadi AUTO_INCREMENT.
    Nilai id yang sudah ada tidak berubah, penomoran lanjutan dimulai dari
    nilai terbesar + 1.

    SQLite: kolom `INTEGER PRIMARY KEY` sudah menjadi alias rowid sehingga
    SQLite otomatis mengisi id yang kosong. Tidak perlu perubahan skema.
    """
    if op.get_bind().dialect.name == 'mysql':
        op.alter_column(
            'products',
            'id',
            existing_type=sa.Integer(),
            autoincrement=True,
            existing_nullable=False,
        )


def downgrade():
    """
    Kembalikan ke ID acak sisi-Python. Skema kolom tidak berubah pada
    MySQL maupun SQLite, jadi tidak ada aksi DDL yang perlu dijalankan.
    """
    return
