from email_validator import EmailNotValidError, validate_email
from flask import current_app
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError


def email_field(message=None):
    """Validator email yang mengizinkan domain khusus (.local/.test) di luar produksi
    agar akun demo tetap bisa dipakai, tetapi tetap ketat di production."""

    def _validate(form, field):
        allow_special = current_app.config.get('ENV', 'dev') != 'prod'
        try:
            validate_email(
                field.data,
                check_deliverability=False,
                test_environment=allow_special,
            )
        except EmailNotValidError as exc:
            raise ValidationError(message or str(exc)) from exc

    return _validate


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), email_field()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Ingat saya')
    submit = SubmitField('Masuk')


class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), email_field(), Length(max=255)])
    password = PasswordField(
        'Password',
        validators=[DataRequired(), Length(min=10)],
        render_kw={'minlength': 10},
    )
    password2 = PasswordField('Konfirmasi', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Daftar')
