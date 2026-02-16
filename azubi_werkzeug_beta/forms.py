"""
Forms module.

Defines WTForms for the application.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField
from wtforms.validators import DataRequired, Length, Regexp, Optional, NumberRange

class AzubiForm(FlaskForm):
    """Form to add or edit an apprentice."""
    name = StringField('Name', validators=[
        DataRequired(),
        Length(min=2, max=50, message="Name muss zwischen 2 und 50 Zeichen lang sein."),
        Regexp(r'^[\w\säöüÄÖÜß\-\.]+$', message="Name enthält ungültige Zeichen.")
    ])
    lehrjahr = IntegerField('Lehrjahr', validators=[
        DataRequired(),
        NumberRange(min=1, max=4, message="Lehrjahr muss zwischen 1 und 4 liegen.")
    ])

class ExaminerForm(FlaskForm):
    """Form to add or edit an examiner."""
    name = StringField('Name', validators=[
        DataRequired(),
        Length(min=2, max=50, message="Name muss zwischen 2 und 50 Zeichen lang sein."),
        Regexp(r'^[\w\säöüÄÖÜß\-\.]+$', message="Name enthält ungültige Zeichen.")
    ])

class WerkzeugForm(FlaskForm):
    """Form to add or edit a tool."""
    name = StringField('Bezeichnung', validators=[
        DataRequired(),
        Length(min=2, max=100, message="Bezeichnung muss zwischen 2 und 100 Zeichen lang sein.")
    ])
    material_category = SelectField('Kategorie', validators=[Optional()], choices=[
        ('standard', 'Standard'),
        ('teilisoliert', 'Teilisoliert'),
        ('vollisoliert', 'Vollisoliert (1000V)'),
        ('isolierend', 'Vollkunststoff')
    ])
    tech_param_label = StringField('Tech. Parameter (Name)', validators=[
        Optional(), Length(max=50)
    ])
    tech_param_value = StringField('Tech. Parameter (Wert)', validators=[
        Optional(), Length(max=50)
    ])
