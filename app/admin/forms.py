from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    FileField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    NumberRange,
    Optional,
)

from app.core.validators import NoMarkup
from app.katalog.models import CATEGORIES


class ProductForm(FlaskForm):
    name = StringField('Nama', validators=[DataRequired(), Length(max=200), NoMarkup()])
    description = TextAreaField('Deskripsi', validators=[Optional(), Length(max=5000)])
    product_type = StringField('Jenis produk / potongan', validators=[Optional(), Length(max=100), NoMarkup()])
    color = StringField('Warna', validators=[Optional(), Length(max=80), NoMarkup()])
    category = SelectField('Kategori', choices=[(c, c) for c in CATEGORIES])
    price = IntegerField('Harga (Rp)', validators=[DataRequired(), NumberRange(min=100, max=100_000_000)])
    original_price = IntegerField(
        'Harga sebelum diskon (Rp, opsional)',
        validators=[Optional(), NumberRange(min=100, max=100_000_000)],
    )
    weight_gram = IntegerField(
        'Berat per produk (gram)',
        validators=[Optional(), NumberRange(min=1, max=100_000)],
        default=500,
    )
    is_active = BooleanField('Aktif dijual', default=True)
    is_fragile = BooleanField('Barang rawan pecah (mis. kaca/keramik)')
    use_sizes = BooleanField('Pakai ukuran', default=False)
    stock = IntegerField('Stok (tanpa ukuran)', validators=[Optional(), NumberRange(min=0, max=1_000_000)])
    # stok per ukuran
    stock_S = IntegerField('Stok S', validators=[Optional(), NumberRange(min=0, max=1_000_000)])
    stock_M = IntegerField('Stok M', validators=[Optional(), NumberRange(min=0, max=1_000_000)])
    stock_L = IntegerField('Stok L', validators=[Optional(), NumberRange(min=0, max=1_000_000)])
    stock_XL = IntegerField('Stok XL', validators=[Optional(), NumberRange(min=0, max=1_000_000)])
    stock_XXL = IntegerField('Stok XXL', validators=[Optional(), NumberRange(min=0, max=1_000_000)])
    image = FileField('Gambar (JPG/PNG, maks 1 MB)')
    submit = SubmitField('Simpan')

    def validate(self, extra_validators=None):
        """
        Validasi tingkat form.

        Aturan "stok wajib diisi jika tidak pakai ukuran" TIDAK bisa pakai
        validator inline `validate_stock`: validator `Optional()` pada field
        `stock` menghentikan rantai validasi (StopValidation) saat field
        kosong, sehingga validator inline tidak pernah dijalankan.
        Karena itu aturannya dicek di sini, yang selalu dijalankan.
        """
        success = super().validate(extra_validators)
        if not success:
            return False
        if not self.use_sizes.data and self.stock.data is None:
            self.stock.errors.append('wajib diisi jika tidak pakai ukuran')
            return False
        if self.original_price.data and self.original_price.data <= (self.price.data or 0):
            self.original_price.errors.append('harus lebih besar dari harga jual agar terhitung diskon')
            return False
        return True


class RoleChangeForm(FlaskForm):
    role = SelectField(
        'Role Baru',
        choices=[('customer', 'Customer'), ('seller', 'Seller'), ('admin', 'Admin')],
        validators=[DataRequired()],
    )
    confirm = StringField('Ketik email pengguna untuk konfirmasi', validators=[DataRequired()])
    submit = SubmitField('Ubah Role')


class OrderNoteForm(FlaskForm):
    """Form catatan admin saat approve/reject pesanan."""
    admin_note = TextAreaField('Catatan (opsional)', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Konfirmasi')
