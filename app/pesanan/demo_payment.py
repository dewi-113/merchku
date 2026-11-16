"""Data pembayaran DEMO untuk metode QRIS dan transfer bank (konfirmasi manual).

Semua informasi di sini fiktif dan hanya untuk demonstrasi aplikasi:
- QRIS: gambar berpola mirip QR, TIDAK bisa dipindai dan tidak berisi payload QRIS.
- Transfer: "Bank Demo Merchku" dengan kode bank 999 (tidak dipakai bank mana pun)
  dan nomor Virtual Account yang diturunkan dari nomor pesanan.
"""
import hashlib

from markupsafe import Markup

DEMO_BANK_NAME = 'Bank Demo Merchku'
DEMO_BANK_CODE = '999'
DEMO_ACCOUNT_HOLDER = 'Merchku (Akun Demo)'
_VA_PREFIX = '8808'

_QR_SIZE = 25  # ukuran modul, setara QR versi 2


def demo_va_number(order):
    """Nomor Virtual Account fiktif (16 digit): prefix + 12 digit nomor pesanan."""
    return f'{_VA_PREFIX}{order.id:012d}'


def format_va(number):
    """Kelompokkan per 4 digit agar mudah dibaca: 8808 0000 0000 0012."""
    return ' '.join(number[i:i + 4] for i in range(0, len(number), 4))


def demo_qris_reference(order):
    return f'MERCHKU-QRIS-{order.id:06d}'


def _finder(cells, top, left):
    for r in range(7):
        for c in range(7):
            edge = r in (0, 6) or c in (0, 6)
            core = 2 <= r <= 4 and 2 <= c <= 4
            cells[top + r][left + c] = edge or core


def _reserved(r, c, n):
    """Area finder pattern + garis pemisahnya."""
    return (r < 8 and c < 8) or (r < 8 and c >= n - 8) or (r >= n - 8 and c < 8)


def demo_qris_svg(order, size_px=200):
    """SVG berpola QR yang konsisten per pesanan, tetapi tidak dapat dipindai."""
    n = _QR_SIZE
    cells = [[False] * n for _ in range(n)]
    _finder(cells, 0, 0)
    _finder(cells, 0, n - 7)
    _finder(cells, n - 7, 0)

    seed = hashlib.sha256(f'merchku-demo-qris-{order.id}-{order.total_price}'.encode()).digest()
    bits = ''.join(f'{b:08b}' for b in (seed * ((n * n) // (len(seed) * 8) + 1)))
    i = 0
    for r in range(n):
        for c in range(n):
            if _reserved(r, c, n):
                continue
            cells[r][c] = bits[i] == '1'
            i += 1
    # pola "timing" seperti QR asli
    for k in range(8, n - 8):
        cells[6][k] = cells[k][6] = k % 2 == 0

    quiet = 2
    total = n + quiet * 2
    rects = ''.join(
        f'<rect x="{c + quiet}" y="{r + quiet}" width="1" height="1"/>'
        for r in range(n) for c in range(n) if cells[r][c]
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}" '
        f'width="{size_px}" height="{size_px}" shape-rendering="crispEdges" '
        f'role="img" aria-label="QRIS demo, tidak dapat dipindai">'
        f'<rect width="{total}" height="{total}" fill="#fff"/>'
        f'<g fill="#111827">{rects}</g></svg>'
    )
    return Markup(svg)


def demo_payment_context(order):
    """Data yang dipakai template untuk menampilkan instruksi pembayaran demo."""
    return {
        'bank_name': DEMO_BANK_NAME,
        'bank_code': DEMO_BANK_CODE,
        'account_holder': DEMO_ACCOUNT_HOLDER,
        'va_number': format_va(demo_va_number(order)),
        'qris_reference': demo_qris_reference(order),
        'qris_svg': demo_qris_svg(order),
    }
