# Pengerasan Server Merchku (VM + Cloudflare)

Alur: **Pengunjung → Cloudflare (HTTPS, WAF) → nginx (VM) → gunicorn 127.0.0.1:8000 → Flask**.

Perlindungan di kode aplikasi sudah ada (CSRF, argon2, cek IDOR, validasi upload,
rate limit, cookie aman, HSTS, CSP). Daftar di bawah menutup celah di **server**.
Kerjakan berurutan; centang yang sudah.

## 1. Paling penting: VM jangan bisa diakses langsung

Kalau IP VM ketahuan, penyerang bisa melewati Cloudflare (dan WAF-nya) sama sekali.

**Pilihan A — Cloudflare Tunnel (paling aman, disarankan).** VM tidak membuka port
web sama sekali; `cloudflared` yang menghubungi Cloudflare dari dalam.

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH          # atau hanya dari IP kamu: sudo ufw allow from <IP-kamu> to any port 22
sudo ufw enable                 # port 80/443 TIDAK dibuka
```

Arahkan tunnel ke `http://localhost:80` (nginx), lalu di nginx aktifkan
`set_real_ip_from 127.0.0.1;` (lihat `nginx-merchku.conf.example`).

**Pilihan B — DNS proxied (awan oranye).** Buka port 80/443 hanya untuk IP Cloudflare:

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH
for ip in $(curl -s https://www.cloudflare.com/ips-v4) $(curl -s https://www.cloudflare.com/ips-v6); do
  sudo ufw allow proto tcp from "$ip" to any port 80,443
done
sudo ufw enable
```

Cek dari luar: `curl -m 5 http://<IP-VM>/` harus **gagal/timeout**.
Jika VM di cloud (GCP/AWS/Azure), atur juga firewall/security group penyedianya.

## 2. Konfigurasi aplikasi produksi (`/opt/merchku/.env`)

```
ENV=prod
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=<acak 64 karakter: python -c "import secrets; print(secrets.token_hex(32))">
SECURE_COOKIES=1
PROXY_FIX_X_FOR=1
METRICS_TOKEN=<acak panjang>
```

- **Jangan pernah** menjalankan `python run.py` / `flask run` di server (debugger
  Werkzeug = eksekusi kode jarak jauh). Pakai gunicorn lewat systemd
  (`gunicorn-merchku.service.example`).
- `chmod 600 /opt/merchku/.env` dan pemiliknya `www-data`.
- Ganti password akun demo: `flask kunci-akun-demo`. Jangan pakai akun `.test`
  dengan password dari repo.
- Gunicorn 4 worker + limiter memori = setiap worker menghitung sendiri. Untuk batas
  yang tepat: `sudo apt install redis-server`, `pip install redis`, lalu isi
  `RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0`.

## 3. Pengaturan Cloudflare (dashboard)

| Menu | Pengaturan |
|---|---|
| SSL/TLS → Overview | **Full (strict)** (pasang Origin Certificate di nginx), minimal **Full** |
| SSL/TLS → Edge Certificates | Always Use HTTPS: **On**, Minimum TLS: **1.2** |
| Security → WAF → Managed rules | Aktifkan Cloudflare Managed Ruleset (paket gratis: Free Managed Ruleset) |
| Security → WAF → Rate limiting rules | `URI Path equals /auth/login` dan metode POST, per IP → Block (paket gratis: periode 10 detik, mis. 5 permintaan/10 detik) |
| Security → Bots | Bot Fight Mode: **On** |
| Security → WAF → Custom rules | Blokir path `/.env`, `/.git`, `/wp-admin`, `/phpmyadmin`; Managed Challenge untuk `/admin` dari luar negara target |
| Security → Settings | Security Level: Medium; Browser Integrity Check: On |

## 4. Mengamankan VM

```bash
# Update otomatis
sudo apt update && sudo apt upgrade -y
sudo apt install -y unattended-upgrades fail2ban
sudo dpkg-reconfigure -plow unattended-upgrades

# SSH: hanya kunci, tanpa root
sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/; s/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh      # uji dulu login pakai kunci di terminal lain!
```

- Database (MySQL/PostgreSQL) hanya mendengar di `127.0.0.1`, user DB khusus
  dengan hak minimal, password kuat.
- Backup database harian ke tempat lain (bukan di VM yang sama).
- Pantau `logs/security.json`: lonjakan `login_failed`, `access_denied`,
  `suspicious_request`.

## 5. Uji cepat setelah deploy

```bash
curl -sI https://<domain>/ | grep -iE 'strict-transport|content-security|x-frame|set-cookie'
# set-cookie harus memuat: Secure; HttpOnly; SameSite=Lax
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/.env        # 404/403
curl -m 5 http://<IP-VM>/                                              # harus gagal
```
