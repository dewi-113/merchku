import ipaddress

from flask import request


def get_client_ip(app_config_trusted=None):
    trusted = app_config_trusted or []
    try:
        remote = ipaddress.ip_address(request.remote_addr)
    except Exception:
        remote = ipaddress.ip_address('127.0.0.1')
    # cek proxy trusted
    if request.headers:
        # CF-Connecting-IP first? spec says CF-Connecting-IP / X-Forwarded-For; but only trust if from trusted proxy
        # simple: if remote in trusted, ambil leftmost dari X-Forwarded-For
        for cidr in trusted:
            try:
                if remote in ipaddress.ip_network(cidr, strict=False):
                    xff = request.headers.get('X-Forwarded-For','')
                    if xff:
                        ip = xff.split(',')[0].strip()
                        try:
                            return str(ipaddress.ip_address(ip))
                        except Exception:
                            pass
                    # Cloudflare
                    cf = request.headers.get('CF-Connecting-IP')
                    if cf:
                        try:
                            return str(ipaddress.ip_address(cf.strip()))
                        except Exception:
                            pass
                    break
            except Exception:
                continue
    return request.remote_addr

def is_trusted_proxy(ip):
    # not used directly
    pass
