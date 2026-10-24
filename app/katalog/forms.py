from flask_wtf import FlaskForm
from wtforms import RadioField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class ReviewForm(FlaskForm):
    rating = RadioField(
        'Rating',
        choices=[('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')],
        coerce=int,
        validators=[DataRequired(), NumberRange(min=1, max=5)],
    )
    comment = TextAreaField('Komentar', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('Kirim Ulasan')

