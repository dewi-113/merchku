import ipaddress
import re

from flask import request

# Pola mencurigakan (path traversal, SQLi, XSS, scan) untuk log suspicious_request
SUSPICIOUS_PATTERNS = [
    (re.compile(r'\.\./|\.\.\\|%2e%2e', re.I), 'path_traversal'),
    (re.compile(r"\bunion\b\s+(\ball\b\s+)?\bselect\b|\bselect\b.+\bfrom\b|\binformation_schema\b|\bbenchmark\s*\(|\bsleep\s*\(|\bOR\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+|\bconcat\s*\(\s*0x|\bextractvalue\s*\(", re.I), 'sqli'),
    (re.compile(r'<\s*script|\bonerror\s*=|\bonload\s*=|javascript:', re.I), 'xss'),
    (re.compile(r'/\.env|/wp-admin|/wp-login|/\.git/|/phpmyadmin|/admin\.php|/etc/passwd', re.I), 'scanning'),
]


def scan_request(path: str):
    """Kembalikan jenis pola mencurigakan (str) atau None."""
    target = path + ' ' + (request.query_string.decode('utf-8', 'ignore') if request.query_string else '')
    for pat, kind in SUSPICIOUS_PATTERNS:
        if pat.search(target):
            return kind
    return None


def _parse_networks(cidrs):
    nets = []
    for cidr in cidrs or []:
        try:
            nets.append(ipaddress.ip_network(cidr.strip(), strict=False))
        except ValueError:
            continue
    return nets


def get_client_ip(app_config_trusted=None):
    """IP asli pengunjung, tahan pemalsuan header.

    X-Forwarded-For dibaca dari KANAN: setiap proxy menambahkan IP pengirimnya
    di ujung kanan, sedangkan entri di kiri bisa ditulis bebas oleh penyerang.
    Lewati semua IP proxy tepercaya dari kanan; IP pertama yang bukan proxy
    adalah pengunjung. Header CF-Connecting-IP tidak dibaca di sini; biarkan
    nginx (modul real_ip, hanya untuk IP Cloudflare) yang menerjemahkannya.
    """
    trusted = _parse_networks(app_config_trusted)
    try:
        remote = ipaddress.ip_address(request.remote_addr)
    except Exception:  # nosec B110 - remote_addr selalu ada; fallback aman
        return request.remote_addr

    def is_trusted(ip):
        return any(ip in net for net in trusted)

    if not is_trusted(remote):
        return str(remote)

    xff = request.headers.get('X-Forwarded-For', '')
    for raw in reversed([part.strip() for part in xff.split(',') if part.strip()]):
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            break  # entri rusak: berhenti, jangan percaya sisanya
        if not is_trusted(ip):
            return str(ip)
    return str(remote)


def log_access_denied(resource: str, resource_id=None, reason: str = 'ownership'):
    """Log event access_denied (untuk pencegahan IDOR)."""
    from flask import current_app

    from app.security_logger import sec_log

    sec_log(
        event='access_denied',
        ip=get_client_ip(current_app.config.get('TRUSTED_PROXIES')),
        path=request.path,
        method=request.method,
        resource=resource,
        resource_id=resource_id,
        reason=reason,
    )

