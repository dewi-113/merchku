
def register_security_headers(app):
    @app.after_request
    def add_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options','nosniff')
        resp.headers.setdefault('X-Frame-Options','SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy','strict-origin-when-cross-origin')
        # CSP dasar (fleksibel)
        resp.headers.setdefault('Content-Security-Policy',"default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' https://cdn.jsdelivr.net; font-src 'self' https://cdn.jsdelivr.net")
        return resp
