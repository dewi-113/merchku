from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, Optional, Regexp


class ShippingAddressForm(FlaskForm):
    recipient_name = StringField(
        'Nama penerima',
        validators=[DataRequired(message='Nama penerima wajib diisi.'), Length(max=200)],
    )
    phone = StringField(
        'Nomor HP',
        validators=[
            DataRequired(message='Nomor HP wajib diisi.'),
            Length(max=30),
            Regexp(r'^[\d\+\-\s\(\)]+$', message='Format nomor HP tidak valid.'),
        ],
    )
    address = TextAreaField(
        'Alamat lengkap',
        validators=[DataRequired(message='Alamat wajib diisi.'), Length(max=1000)],
    )
    address_label = SelectField(
        'Label alamat',
        choices=[('rumah', 'Rumah'), ('kos', 'Kos'), ('kantor', 'Kantor')],
        validators=[DataRequired()],
    )
    district = StringField(
        'Kecamatan',
        validators=[DataRequired(message='Kecamatan wajib diisi.'), Length(max=100)],
    )
    city = StringField(
        'Kota / Kabupaten',
        validators=[DataRequired(message='Kota wajib diisi.'), Length(max=100)],
    )
    province = StringField(
        'Provinsi',
        validators=[DataRequired(message='Provinsi wajib diisi.'), Length(max=100)],
    )
    postal_code = StringField(
        'Kode pos',
        validators=[
            DataRequired(message='Kode pos wajib diisi.'),
            Length(min=5, max=10),
            Regexp(r'^\d{5,10}$', message='Kode pos hanya boleh angka (5-10 digit).'),
        ],
    )
    delivery_note = StringField(
        'Catatan untuk kurir (opsional)',
        validators=[Optional(), Length(max=300)],
    )
    submit = SubmitField('Simpan alamat')


class GantiPasswordForm(FlaskForm):
    password_lama = PasswordField(
        'Password Lama',
        validators=[DataRequired(message='Password lama wajib diisi.')],
    )
    password_baru = PasswordField(
        'Password Baru',
        validators=[
            DataRequired(message='Password baru wajib diisi.'),
            Length(min=10, message='Password minimal 10 karakter.'),
        ],
    )
    password_baru2 = PasswordField(
        'Konfirmasi Password Baru',
        validators=[
            DataRequired(),
            EqualTo('password_baru', message='Konfirmasi tidak cocok.'),
        ],
    )
    submit = SubmitField('Ganti Password')


class AvatarForm(FlaskForm):
    avatar = FileField(
        'Foto profil',
        validators=[
            FileAllowed(['jpg', 'jpeg', 'png'], 'Hanya JPG atau PNG.'),
        ],
    )
    submit = SubmitField('Upload Avatar')
