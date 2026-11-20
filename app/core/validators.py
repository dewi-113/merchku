"""Validator teks bebas yang tampil ke publik (nama toko, nama produk, dst.)."""

import re

from wtforms.validators import ValidationError

# Nama toko: huruf (termasuk huruf beraksen), angka, spasi, dan tanda baca umum.
SHOP_NAME_RE = re.compile(r"^[^\W_][\w\s.,'&()\-]*$")

# Karakter yang tidak pernah wajar di nama/label publik: sintaks template,
# tag HTML, backtick, dan karakter kontrol.
_FORBIDDEN_RE = re.compile(r'[{}<>`$\\\x00-\x1f\x7f]')


def shop_name_valid(value):
    return bool(SHOP_NAME_RE.match(value))


class SafeShopName:
    """Nama toko hanya huruf, angka, spasi, dan . , ' & ( ) -"""

    message = "Nama toko hanya boleh berisi huruf, angka, spasi, dan tanda . , ' & ( ) -"

    def __call__(self, form, field):
        value = (field.data or '').strip()
        if value and not shop_name_valid(value):
            raise ValidationError(self.message)


class NoMarkup:
    """Tolak karakter { } < > ` $ \\ dan karakter kontrol."""

    message = 'Tidak boleh mengandung karakter { } < > ` $ \\'

    def __call__(self, form, field):
        if field.data and _FORBIDDEN_RE.search(field.data):
            raise ValidationError(self.message)
