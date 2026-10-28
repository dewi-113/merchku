#!/usr/bin/env bash
# Perintah start di Render (lihat render.yaml). Dijalankan setiap server menyala:
# paket gratis Render menidurkan server saat sepi dan disknya tidak permanen,
# jadi migrasi + seed (idempoten) dijalankan ulang setiap start.
set -euo pipefail
export FLASK_APP=run.py

flask db upgrade

if [ "${SEED_DEMO:-0}" = "1" ]; then
  # Password akun demo di repo bersifat publik: wajib diganti sebelum web dibuka
  if [ -z "${DEMO_PASSWORD:-}" ]; then
    echo "SEED_DEMO=1 tapi DEMO_PASSWORD kosong. Isi DEMO_PASSWORD di Environment Render." >&2
    exit 1
  fi
  flask seed-demo --force
  flask seed-toko --force
  flask sesuaikan-produk
  flask seed-promo --force
  flask seed-sosial --force
  flask kunci-akun-demo
fi

exec gunicorn run:app \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers 2 \
  --timeout 120 \
  --access-logfile -
