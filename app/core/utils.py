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


def get_client_ip(app_config_trusted=None):
    trusted = app_config_trusted or []
    try:
        remote = ipaddress.ip_address(request.remote_addr)
    except Exception:  # nosec B110 - remote_addr selalu ada; fallback aman
        remote = ipaddress.ip_address('127.0.0.1')
    if request.headers:
        for cidr in trusted:
            try:
                net = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            if remote in net:
                xff = request.headers.get('X-Forwarded-For', '')
                if xff:
                    ip = xff.split(',')[0].strip()
                    try:
                        return str(ipaddress.ip_address(ip))
                    except ValueError:
                        pass
                cf = request.headers.get('CF-Connecting-IP')
                if cf:
                    try:
                        return str(ipaddress.ip_address(cf.strip()))
                    except ValueError:
                        pass
                break
    return request.remote_addr


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

