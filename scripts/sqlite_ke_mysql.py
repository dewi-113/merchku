"""Salin seluruh data dari database SQLite lama ke MySQL/MariaDB.

Langkah:
  1. Set DB_ENGINE=mysql (+ DB_USER, DB_PASSWORD, DB_NAME) di .env
  2. flask db upgrade                       (membuat tabel kosong di MySQL)
  3. python scripts/sqlite_ke_mysql.py       (menyalin isi tabel)

Opsi: --sqlite PATH (default instance/merchku.db), --kosongkan (hapus isi tabel
MySQL dulu, untuk mengulang penyalinan).
"""
import argparse
import os
import sys

from sqlalchemy import MetaData, create_engine, select, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sqlite', default=os.path.join(ROOT, 'instance', 'merchku.db'))
    parser.add_argument('--kosongkan', action='store_true', help='hapus isi tabel MySQL sebelum menyalin')
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
    from config import _database_uri

    target_uri = _database_uri()
    if not str(getattr(target_uri, 'drivername', target_uri)).startswith('mysql'):
        sys.exit('DB_ENGINE di .env belum mysql. Ubah dulu, lalu jalankan flask db upgrade.')
    if not os.path.isfile(args.sqlite):
        sys.exit(f'File SQLite tidak ditemukan: {args.sqlite}')

    source = create_engine(f'sqlite:///{args.sqlite}')
    target = create_engine(target_uri)
    src_meta, dst_meta = MetaData(), MetaData()
    src_meta.reflect(source)
    dst_meta.reflect(target)

    # Urutan sesuai foreign key (tabel induk dulu)
    tables = [t for t in dst_meta.sorted_tables if t.name != 'alembic_version' and t.name in src_meta.tables]
    missing = sorted(set(src_meta.tables) - set(dst_meta.tables) - {'alembic_version'})
    if missing:
        print('Peringatan, tabel ini tidak ada di MySQL (lewati):', ', '.join(missing))

    with source.connect() as src, target.begin() as dst:
        dst.execute(text('SET FOREIGN_KEY_CHECKS=0'))
        if args.kosongkan:
            for table in reversed(tables):
                dst.execute(table.delete())
        for table in tables:
            if not args.kosongkan and dst.execute(select(table).limit(1)).first():
                sys.exit(f'Tabel {table.name} di MySQL sudah berisi data. Pakai --kosongkan untuk mengulang.')
            columns = [c.name for c in table.columns if c.name in src_meta.tables[table.name].columns]
            rows = [dict(r._mapping) for r in src.execute(select(*[src_meta.tables[table.name].c[c] for c in columns]))]
            for start in range(0, len(rows), 500):
                dst.execute(table.insert(), rows[start:start + 500])
            print(f'  {table.name:<22} {len(rows):>6} baris')
        dst.execute(text('SET FOREIGN_KEY_CHECKS=1'))
    print('Selesai. Data SQLite sudah tersalin ke MySQL.')


if __name__ == '__main__':
    main()
