# Panduan Deploy Merchku ke PythonAnywhere

Penanggung jawab: Bram Lumazato Manao
Tanggal: 20 November 2026
Bagian: Internetworking (Deployment & Jaringan)

## 1. Alur Jaringan

    Pengguna (browser)
          │  HTTPS (port 443)
          ▼
    Server web PythonAnywhere  ──  sertifikat SSL/HTTPS
          │  WSGI
          ▼
    Aplikasi Flask Merchku (run.py → create_app())
          │  SQLAlchemy
          ▼
    Database

- Pengguna mengakses website lewat HTTPS, jadi data login terenkripsi.
- PythonAnywhere meneruskan request ke aplikasi Flask melalui file WSGI.
- Flask membaca/menulis data ke database melalui SQLAlchemy.
- Kode diambil dari GitHub (`github.com/dewi-113/merchku`) dengan `git pull`.

## 2. Setup Pertama Kali
1. Buka **Consoles → Bash**, lalu clone repo:

       git clone https://github.com/dewi-113/merchku.git
       cd merchku

2. Buat virtualenv dan install library:

       python3 -m venv venv
       source venv/bin/activate
       pip install -r requirements.txt

3. Buat file `.env` dari contoh, lalu isi `SECRET_KEY` dan pengaturan database:

       cp .env.example .env
       python -c "import secrets; print(secrets.token_hex(32))"

4. Siapkan tabel database dengan migration:

       flask db upgrade

5. Di tab **Web**:
   - **Source code:** `/home/<username>/merchku`
   - **Virtualenv:** `/home/<username>/merchku/venv`
   - Edit **WSGI configuration file**, isi:

         import sys
         path = '/home/<username>/merchku'
         if path not in sys.path:
             sys.path.insert(0, path)
         from run import app as application

   - Aktifkan **Force HTTPS**.
6. Klik **Reload**.

## 3. Update Setelah Ada Perubahan di GitHub

    cd ~/merchku
    source venv/bin/activate
    git pull origin main
    flask db upgrade        # hanya jika ada migration baru

Lalu buka tab **Web** → klik **Reload**.

Contoh nyata: update validasi nama toko (commit `1a90133`) di-deploy dengan
`git pull`, lalu data lama dibersihkan dengan:

    flask bersihkan-nama-toko --terapkan

## 4. Cek Website Berjalan
- Buka `https://<username>.pythonanywhere.com/healthz` → harus merespons OK.
- Jika error, lihat **Error log** dan **Server log** di tab **Web**.

## 5. Keamanan Jaringan
- **HTTPS wajib** (Force HTTPS) agar password dan cookie tidak bisa disadap.
- File `.env` (berisi SECRET_KEY & password database) **tidak di-push ke GitHub**
  (sudah ada di `.gitignore`).
- Untuk server VM sendiri tersedia contoh konfigurasi reverse proxy
  `nginx-merchku.conf.example` dan service `gunicorn-merchku.service.example`.
