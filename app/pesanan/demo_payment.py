"""Data pembayaran DEMO untuk metode QRIS dan transfer bank (konfirmasi manual).

Semua informasi di sini fiktif dan hanya untuk demonstrasi aplikasi:
- QRIS: kartu app/static/images/qris-demo.png (dibuat scripts/buat_qris_demo.py);
  pola QR-nya TIDAK bisa dipindai dan tidak berisi payload QRIS.
- Transfer: "Bank Demo Merchku" dengan kode bank 999 (tidak dipakai bank mana pun)
  dan nomor Virtual Account yang diturunkan dari nomor pesanan.
"""
import hashlib

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


def demo_qr_matrix(seed_text, n=_QR_SIZE):
    """Matriks n x n berpola QR (finder + timing + modul acak dari seed).

    Pola selalu sama untuk seed yang sama, tetapi bukan kode QR yang valid.
    """
    cells = [[False] * n for _ in range(n)]
    _finder(cells, 0, 0)
    _finder(cells, 0, n - 7)
    _finder(cells, n - 7, 0)

    # bit acak deterministik: sha256(seed + nomor blok), tidak berulang
    bits = ''
    block = 0
    while len(bits) < n * n:
        digest = hashlib.sha256(f'{seed_text}:{block}'.encode()).digest()
        bits += ''.join(f'{b:08b}' for b in digest)
        block += 1
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
    return cells


def demo_payment_context(order):
    """Data yang dipakai template untuk menampilkan instruksi pembayaran demo."""
    return {
        'bank_name': DEMO_BANK_NAME,
        'bank_code': DEMO_BANK_CODE,
        'account_holder': DEMO_ACCOUNT_HOLDER,
        'va_number': format_va(demo_va_number(order)),
        'qris_reference': demo_qris_reference(order),
    }
