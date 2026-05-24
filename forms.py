from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField
from wtforms.validators import DataRequired, Length

class ClienteForm(FlaskForm):
    nome_tutor = StringField('Nome do Tutor', validators=[DataRequired(), Length(min=3)])
    nome_pet = StringField('Nome do Pet', validators=[DataRequired()])
    telefone = StringField('Telefone', validators=[DataRequired(), Length(min=9)])
    raca_pet = StringField('Raça')
    submit = SubmitField('Salvar')