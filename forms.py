from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, FloatField, FieldList, FormField
from wtforms.fields.datetime import DateField
from wtforms.validators import DataRequired, URL, Email, NumberRange, Optional
from datetime import date

class POLineForm(FlaskForm):
    class Meta:
        csrf = False #desactiva el CSFR token para los subformularios
    item = IntegerField('Item', render_kw={"readonly": True})  # ahora solo muestra el número
    part_number = StringField('Part Number', validators=[Optional()])
    description = StringField('Description', render_kw={"readonly": True})
    quantity = FloatField('Quantity', validators=[Optional(), NumberRange(min=1.0)])
    req_date = DateField('Req Date', format='%Y-%m-%d', validators=[Optional()])
    unit = StringField('Unit', validators=[Optional()])
    unit_price = FloatField('Unit Price', validators=[Optional(), NumberRange(min=0.1)])
    line_total= FloatField('Total', validators=[Optional()], render_kw={"readonly": True})



class PurchaseOrderForm(FlaskForm):
    creation_date = DateField('Date', default=date.today, format='%Y-%m-%d', render_kw={"readonly": True})
    lines = FieldList(FormField(POLineForm), min_entries=5)
    supplier = StringField('Supplier', validators=[DataRequired()])
    total_price = FloatField('Total', validators=[Optional()], render_kw={"readonly": True})
    #status = StringField('Status', validators=[DataRequired()])
    submit = SubmitField('Create PO')