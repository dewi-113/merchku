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
    ValidationError,
)

from app.katalog.models import CATEGORIES


class ProductForm(FlaskForm):
    name = StringField('Nama', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Deskripsi', validators=[Optional(), Length(max=5000)])
    category = SelectField('Kategori', choices=[(c, c) for c in CATEGORIES])
    price = IntegerField('Harga (Rp)', validators=[DataRequired(), NumberRange(min=100, max=100_000_000)])
    is_active = BooleanField('Aktif dijual', default=True)
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

    def validate_stock(self, field):
        if not self.use_sizes.data and field.data is None:
            raise ValidationError('wajib diisi jika tidak pakai ukuran')


class UserStatusForm(FlaskForm):
    submit = SubmitField('Konfirmasi')


class RoleChangeForm(FlaskForm):
    confirm = StringField('Ketik email pengguna untuk konfirmasi', validators=[DataRequired()])
    submit = SubmitField('Ubah Role')
