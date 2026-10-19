import os
import uuid

from PIL import Image, UnidentifiedImageError

MAX_AVATAR_BYTES = 1 * 1024 * 1024          # 1 MB
MAX_PRODUCT_BYTES = 1 * 1024 * 1024          # 1 MB
MAX_PAYMENT_BYTES = 2 * 1024 * 1024          # 2 MB

MAGIC = {
    'jpg': (b'\xff\xd8\xff',),
    'png': (b'\x89PNG\r\n\x1a\n',),
    'pdf': (b'%PDF-',),
}

# content-type yang diperbolehkan per jenis
ALLOWED_CT = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'application/pdf': 'pdf',
}

ALLOWED_EXT = {
    'jpg': {'.jpg', '.jpeg'},
    'png': {'.png'},
    'pdf': {'.pdf'},
}


class UploadRejected(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _check_magic(data: bytes, kind: str):
    for prefix in MAGIC[kind]:
        if data.startswith(prefix):
            return True
    return False


def validate_image_upload(file, kind='produk', max_bytes=MAX_PRODUCT_BYTES):
    """Validasi ekstensi + content-type + magic bytes. Return (filename_baru, pil_image)
    tanpa menyimpan; caller yang menulis setelah re-encode.

    kind: avatar | produk | bukti_bayar (bukti_bayar bisa pdf)
    raise UploadRejected jika tidak valid.
    """
    original = getattr(file, 'filename', '') or ''
    ext = os.path.splitext(original)[1].lower()
    if not ext:
        raise UploadRejected('nama file tanpa ekstensi')
    ct = (file.mimetype or '').lower()

    if kind == 'bukti_bayar':
        # jpg/png/pdf
        if not any(ext in ALLOWED_EXT[k] for k in ('jpg', 'png', 'pdf')):
            raise UploadRejected('ekstensi harus jpg/png/pdf')
        kind_map = {'.jpg': 'jpg', '.jpeg': 'jpg', '.png': 'png', '.pdf': 'pdf'}
        expect = kind_map[ext]
        if ALLOWED_CT.get(ct) != expect:
            raise UploadRejected('content-type tidak sesuai ekstensi')
        data = file.stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise UploadRejected('ukuran melebihi batas')
        if not _check_magic(data, expect):
            raise UploadRejected('magic bytes tidak valid')
        # simpan ulang stream agar bisa dibaca lagi
        file.stream.seek(0)
        if expect == 'pdf':
            return data  # pdf tidak dire-encode, simpan mentah
        # jpg/png: re-encode lewat Pillow
        try:
            file.stream.seek(0)
            img = Image.open(file.stream)
            img.verify()
            file.stream.seek(0)
            img = Image.open(file.stream)
            img.load()
        except (UnidentifiedImageError, OSError):
            raise UploadRejected('gambar rusak/tidak terbaca Pillow')
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        return data, img

    # avatar / produk: gambar saja
    if ext not in ALLOWED_EXT['jpg'] | ALLOWED_EXT['png']:
        raise UploadRejected('ekstensi harus jpg/png')
    expect = 'jpg' if ext in ALLOWED_EXT['jpg'] else 'png'
    if ALLOWED_CT.get(ct) != expect:
        raise UploadRejected('content-type tidak sesuai ekstensi')
    data = file.stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadRejected('ukuran melebihi batas')
    if not _check_magic(data, expect):
        raise UploadRejected('magic bytes tidak valid')
    file.stream.seek(0)
    try:
        img = Image.open(file.stream)
        img.verify()
        file.stream.seek(0)
        img = Image.open(file.stream)
        img.load()
    except (UnidentifiedImageError, OSError):
        raise UploadRejected('gambar rusak/tidak terbaca Pillow')
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    return data, img


def reencode_and_save(img, directory: str) -> str:
    """Re-encode aman via Pillow dan simpan dengan nama UUID.jpg. Return nama file."""
    os.makedirs(directory, exist_ok=True)
    name = uuid.uuid4().hex + '.jpg'
    path = os.path.join(directory, name)
    img.save(path, format='JPEG', quality=88)
    return name


def save_bytes(data: bytes, directory: str, ext: str) -> str:
    """Simpan bytes (pdf/tanpa re-encode) dengan nama UUID."""
    os.makedirs(directory, exist_ok=True)
    name = uuid.uuid4().hex + ext
    with open(os.path.join(directory, name), 'wb') as f:
        f.write(data)
    return name
