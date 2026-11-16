"""Buat gambar kartu QRIS DEMO: app/static/images/qris-demo.png

Gambar ini hanya untuk demo aplikasi. Pola QR-nya TIDAK dapat dipindai.

    python scripts/buat_qris_demo.py
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.pesanan.demo_payment import demo_qr_matrix  # noqa: E402

OUT = os.path.join(ROOT, 'app', 'static', 'images', 'qris-demo.png')
LOGO = os.path.join(ROOT, 'app', 'static', 'icons', 'merchku-512.png')

BLUE = '#2451d6'
BLUE_DARK = '#1a3fb0'
INK = '#14161c'
MUTED = '#6b6f7a'
LINE = '#e6e2d8'

W, H = 720, 1040
SCALE = 2  # gambar digambar 2x lalu diperkecil agar tepi halus


def font(names, size):
    for name in names:
        for folder in ('C:/Windows/Fonts', '/usr/share/fonts/truetype/dejavu', '/Library/Fonts'):
            path = os.path.join(folder, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size * SCALE)
    return ImageFont.load_default()


BOLD = ['segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf']
REGULAR = ['segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf']
MONO = ['consola.ttf', 'DejaVuSansMono.ttf']


def s(v):
    return v * SCALE


def center_text(draw, y, text, fnt, fill):
    w = draw.textlength(text, font=fnt)
    draw.text(((s(W) - w) / 2, s(y)), text, font=fnt, fill=fill)


def logo_tile(size):
    """Logo Merchku di atas kotak putih membulat."""
    tile = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill='white')
    if os.path.exists(LOGO):
        logo = Image.open(LOGO).convert('RGBA')
        # buang ruang kosong di sekitar logo (piksel putih/transparan)
        bg = Image.new('RGBA', logo.size, (255, 255, 255, 255))
        mask = Image.alpha_composite(bg, logo).convert('L').point(lambda v: 255 if v < 240 else 0)
        bbox = mask.getbbox()
        if bbox:
            logo = logo.crop(bbox)
        inner_w = int(size * 0.72)
        inner_h = int(inner_w * logo.height / logo.width)
        logo = logo.resize((inner_w, inner_h), Image.LANCZOS)
        tile.alpha_composite(logo, ((size - inner_w) // 2, (size - inner_h) // 2))
    return tile


def main():
    img = Image.new('RGBA', (s(W), s(H)), (0, 0, 0, 0))  # latar transparan
    d = ImageDraw.Draw(img)

    # kartu
    card = [s(32), s(32), s(W - 32), s(H - 32)]
    d.rounded_rectangle(card, radius=s(28), fill='white', outline=LINE, width=s(2))

    # header biru
    d.rounded_rectangle([card[0], card[1], card[2], s(200)], radius=s(28), fill=BLUE)
    d.rectangle([card[0], s(150), card[2], s(200)], fill=BLUE)
    img.paste(logo_tile(s(84)), (s(64), s(74)), logo_tile(s(84)))
    d.text((s(168), s(78)), 'MERCHKU', font=font(BOLD, 40), fill='white')
    d.text((s(170), s(130)), 'Pembayaran QRIS', font=font(REGULAR, 22), fill='#dbe4ff')

    # badge demo di header
    badge_f = font(BOLD, 18)
    label = 'MODE DEMO'
    bw = d.textlength(label, font=badge_f) + s(28)
    bx = card[2] - s(32) - bw
    d.rounded_rectangle([bx, s(96), bx + bw, s(134)], radius=s(19), fill='#fff4d6')
    d.text((bx + s(14), s(102)), label, font=badge_f, fill='#8a5a00')

    # identitas merchant
    center_text(d, 236, 'MERCHKU STORE', font(BOLD, 34), INK)
    center_text(d, 286, 'NMID : ID00DEMO0000001', font(MONO, 22), MUTED)

    # QR
    n = 29
    cells = demo_qr_matrix('merchku-qris-demo-poster', n)
    qr_px = 440
    mod = qr_px / n
    qx, qy = (W - qr_px) / 2, 340
    d.rounded_rectangle([s(qx - 20), s(qy - 20), s(qx + qr_px + 20), s(qy + qr_px + 20)],
                        radius=s(18), fill='white', outline=LINE, width=s(2))
    for r in range(n):
        for c in range(n):
            if cells[r][c]:
                x0, y0 = qx + c * mod, qy + r * mod
                d.rectangle([s(x0), s(y0), s(x0 + mod) - 1, s(y0 + mod) - 1], fill=INK)
    # logo di tengah QR
    tile = s(96)
    lt = logo_tile(tile)
    img.paste(lt, (int(s(W / 2) - tile / 2), int(s(qy + qr_px / 2) - tile / 2)), lt)

    # petunjuk
    center_text(d, 830, 'Pindai dengan aplikasi e-wallet atau m-banking', font(REGULAR, 22), INK)
    center_text(d, 864, 'lalu bayar sesuai total pesanan.', font(REGULAR, 22), INK)

    # catatan demo
    note_f = font(BOLD, 18)
    note = 'CONTOH UNTUK DEMO APLIKASI  ·  TIDAK DAPAT DIPINDAI'
    nw = d.textlength(note, font=note_f) + s(36)
    nx = (s(W) - nw) / 2
    d.rounded_rectangle([nx, s(920), nx + nw, s(962)], radius=s(21), fill='#fdecec')
    d.text((nx + s(18), s(928)), note, font=note_f, fill='#b42318')

    img = img.resize((W, H), Image.LANCZOS)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT, optimize=True)
    print(f'Tersimpan: {OUT}')


if __name__ == '__main__':
    main()
