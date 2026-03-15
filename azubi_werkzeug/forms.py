"""
Forms module.

Defines WTForms for the application.
"""
from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, SelectField, StringField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp


class AzubiForm(FlaskForm):
    """Form to add or edit an apprentice."""

    name = StringField(
        'Name',
        validators=[
            DataRequired(),
            Length(
                min=2,
                max=50,
                message="Name muss zwischen 2 und 50 Zeichen lang sein."),
            Regexp(
                r'^[\w\sÃ¤Ã¶Ã¼Ã„Ã–ÃœÃŸ\-\.]+$',
                message="Name enthÃ¤lt ungÃ¼ltige Zeichen.")])
    lehrjahr = IntegerField(
        'Lehrjahr',
        validators=[
            DataRequired(),
            NumberRange(
                min=1,
                max=4,
                message="Lehrjahr muss zwischen 1 und 4 liegen.")])


class ExaminerForm(FlaskForm):
    """Form to add or edit an examiner."""

    name = StringField(
        'Name',
        validators=[
            DataRequired(),
            Length(
                min=2,
                max=50,
                message="Name muss zwischen 2 und 50 Zeichen lang sein."),
            Regexp(
                r'^[\w\sÃ¤Ã¶Ã¼Ã„Ã–ÃœÃŸ\-\.]+$',
                message="Name enthÃ¤lt ungÃ¼ltige Zeichen.")])


class WerkzeugForm(FlaskForm):
    """Form to add or edit a tool."""

    name = StringField(
        'Bezeichnung',
        validators=[
            DataRequired(),
            Length(
                min=2,
                max=100,
                message="Bezeichnung muss zwischen 2 und 100 Zeichen lang sein.")])
    material_category = SelectField('Kategorie', validators=[Optional()], choices=[
        ('standard', 'Standard'),
        ('teilisoliert', 'Teilisoliert'),
        ('vollisoliert', 'Vollisoliert (1000V)'),
        ('isolierend', 'Vollkunststoff')
    ])
    tech_param_label = StringField('Zusatzinfo Label (Optional)', [
        Length(max=50),
        Optional()
    ])
    price = FloatField('Preis (â‚¬)', [
        Optional()
    ], default=0.0)
    tech_param_value = StringField('Tech. Parameter (Wert)', validators=[
        Optional(), Length(max=50)
    ])
