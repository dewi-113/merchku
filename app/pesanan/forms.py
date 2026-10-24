from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, RadioField, SelectField
from wtforms.validators import DataRequired


class CheckoutForm(FlaskForm):
    courier = SelectField(
        'Pilih kurir',
        choices=[
            ('jne', 'JNE'),
            ('jnt', 'J&T Express'),
            ('sicepat', 'SiCepat'),
            ('anteraja', 'AnterAja'),
            ('pos', 'Pos Indonesia'),
        ],
        validators=[DataRequired()],
        default='jne',
    )
    payment_method = RadioField(
        'Metode pembayaran',
        choices=[
            ('bank_transfer', 'Transfer Bank'),
            ('qris', 'QRIS'),
            ('ewallet', 'E-Wallet'),
            ('cod', 'Tunai saat pesanan diterima (COD)'),
            ('midtrans', 'Pembayaran online (QRIS, transfer bank, e-wallet)'),
        ],
        default='bank_transfer',
        validators=[DataRequired()],
    )
    fragile_protection = BooleanField('Gunakan perlindungan kemasan barang rawan pecah')


class BuktiBayarForm(FlaskForm):
    bukti = FileField(
        'Bukti Pembayaran',
        validators=[
            FileRequired(message='Pilih file bukti bayar.'),
            FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Hanya JPG, PNG, atau PDF.'),
        ],
    )
