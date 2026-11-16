CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'self'"
)


def register_security_headers(app):
    @app.after_request
    def add_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        resp.headers.setdefault(
            'Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()'
        )
        resp.headers.setdefault('Content-Security-Policy', CSP)
        # HSTS hanya bila situs memang dilayani lewat HTTPS (SECURE_COOKIES=1)
        if app.config.get('SECURE_COOKIES') and app.config.get('HSTS_MAX_AGE'):
            resp.headers.setdefault(
                'Strict-Transport-Security',
                f"max-age={app.config['HSTS_MAX_AGE']}; includeSubDomains",
            )
        # Halaman pribadi jangan disimpan di cache (tombol Back setelah logout
        # di komputer bersama tidak boleh menampilkan data akun)
        from flask_login import current_user
        if (
            'Cache-Control' not in resp.headers
            and resp.mimetype == 'text/html'
            and current_user
            and current_user.is_authenticated
        ):
            resp.headers['Cache-Control'] = 'no-store'
            resp.headers['Pragma'] = 'no-cache'
        # Jangan beri tahu versi server ke penyerang
        resp.headers.pop('Server', None)
        return resp
