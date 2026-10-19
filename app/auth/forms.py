from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Ingat saya')
    submit = SubmitField('Masuk')

class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=10)], render_kw={'minlength':10})
    password2 = PasswordField('Konfirmasi', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Daftar')
