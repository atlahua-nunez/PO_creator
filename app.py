import datetime
from calendar import *

from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap5
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Float, Date, func, ForeignKey
from forms import PurchaseOrderForm, POLineForm
import pandas as pd


class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class= Base)

app = Flask(__name__)
bootstrap = Bootstrap5(app)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///po_creation_project.db'

db.init_app(app)


class PurchaseOrder(db.Model):
    __tablename__= "purchase_order"
    id:Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    po_number:Mapped[str] = mapped_column(String, nullable=True)
    creation_date:Mapped[datetime.date] = mapped_column(Date)
    supplier:Mapped[str] = mapped_column(String)
    total_price:Mapped[float] = mapped_column(Float)
    status:Mapped[str] = mapped_column(String, default="open")

    lines:Mapped[list["POLines"]] = relationship('POLines', back_populates='po')

    def generate_po_number(self):
       self.po_number = f"PO-{self.id:04d}"

class POLines(db.Model):
    __tablename__= "po_lines"
    id:Mapped[int] = mapped_column(Integer, primary_key= True, unique=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id"), nullable=False)
    item:Mapped[int] =  mapped_column(Integer)
    part_number:Mapped[str] = mapped_column(String, nullable=True)
    description:Mapped[str]= mapped_column(String, nullable=True)
    quantity:Mapped[int] = mapped_column(Integer, nullable=True)
    req_date:Mapped[datetime.date] = mapped_column(Date, nullable=True)
    unit:Mapped[str] = mapped_column(String, nullable=True)
    unit_price:Mapped[float] = mapped_column(Float, nullable=True)
    line_total:Mapped[float] = mapped_column(Float, nullable=True)

    po:Mapped["PurchaseOrder"] = relationship('PurchaseOrder', back_populates='lines')

class PartDataBase(db.Model):
    __tablename__="part_numbers"
    id:Mapped[int] = mapped_column(Integer, primary_key= True, unique=True)
    part_number:Mapped[str] = mapped_column(String)
    moq:Mapped[int] = mapped_column(Integer)
    unit:Mapped[str] = mapped_column(String)
    unit_price:Mapped[float] = mapped_column(Float)
    supplier:Mapped[str] = mapped_column(String)
    lead_time:Mapped[int] = mapped_column(Integer)
    family:Mapped[str] = mapped_column(String)
    description:Mapped[str] = mapped_column(String)


with app.app_context():
    db.create_all()

def update_po_total(purchase_order):
    """Calculate and update PO total immediately"""
    new_total = db.session.execute(
        db.select(db.func.sum(POLines.line_total))
        .where(POLines.po_id == purchase_order.id)
    ).scalar() or 0.0

    purchase_order.total_price = new_total
    db.session.commit()
    return new_total

@app.route('/')
def home():
    all_po=db.session.execute(db.select(PurchaseOrder).order_by(PurchaseOrder.po_number)).scalars().all()
    return render_template('index.html', all_po=all_po)

@app.route('/add', methods=['GET','POST'])
def add():

    form = PurchaseOrderForm()

    for idx, line in enumerate(form.lines.entries, start=1):
        line.item.data = idx

    if form.validate_on_submit():
        #filtrar lineas no vacias
        valid_lines = []
        grand_total = 0

        for line in form.lines.entries:
            if line.item.data and line.quantity.data and line.req_date.data:
                line_total = 0
                if line.unit_price.data and line.quantity.data:
                    line_total = line.quantity.data * line.unit_price.data
                    line.line_total.data = line_total
                    grand_total += line_total
                valid_lines.append(line)

        if not valid_lines:
            flash("Each PO must have a least one line.", "danger")
            return render_template('/add.html', form=form)

        # Get the next ID to generate PO number
        next_id = db.session.execute(db.select(func.max(PurchaseOrder.id))).scalar()
        next_id = (next_id + 1) if next_id else 1
        po_number = f"PO-{next_id:04d}"


        po = PurchaseOrder(
            po_number=po_number,
            creation_date=form.creation_date.data,
            supplier=form.supplier.data,
            total_price=grand_total,
            status=form.status.data,
        )
        db.session.add(po)
        db.session.flush()



        for line_form in valid_lines:
                part_record = db.session.execute(db.select(PartDataBase).where(PartDataBase.part_number == line_form.part_number)).scalar()
                if not part_record:
                    flash(f"Part {line_form.part_number.data} does not exist", "error")
                    #return error

                final_qty = max(line_form.quantity.data, part_record.moq)

                line_item = POLines(
                    po_id=po.id,
                    item=line_form.item.data,
                    part_number=part_record.part_number,
                    description=part_record.description,
                    quantity=final_qty,
                    req_date=line_form.req_date.data,
                    unit=part_record.unit,
                    unit_price=part_record.unit_price,
                    line_total=final_qty * part_record.unit_price,
                )
                db.session.add(line_item)

        db.session.commit()

        flash("PO created correctly.", "success")

        return render_template('/add.html',
                               form=form,
                               po_number=po.po_number,
                               po_created=True)

    # if request.method == 'POST':
    #     print("Form errors:", form.errors)

    return render_template('/add.html', form=form, po_created=False)


@app.route('/view/<string:po_code>', methods=['GET'])
def view_po(po_code):
    purchase_order = db.session.execute(db.select(PurchaseOrder).where(PurchaseOrder.po_number.ilike(po_code))).scalar()

    if not purchase_order:
        flash('PO not found.', 'danger')
        return render_template('view.html', purchase_order=purchase_order)

    po_lines = db.session.execute(db.select(POLines).where(POLines.po_id == purchase_order.id).order_by(POLines.item)).scalars().all()
    return render_template('view.html', purchase_order=purchase_order, po_lines=po_lines)

@app.route('/search_po', methods=['GET'])
def search_po():
    po_code = request.args.get('po_code')
    current_po = request.args.get('current_po')

    if not po_code or not po_code.strip():
        flash('Please enter a PO number to search', 'warning')
        if current_po:
            return redirect(url_for('view_po', po_code=current_po))
        else:
            return render_template('view.html')

    search_po_code = po_code.strip()
    purchase_order = db.session.execute(db.select(PurchaseOrder).where(PurchaseOrder.po_number.ilike(search_po_code))).scalar()

    if purchase_order:
        return redirect(url_for('view_po', po_code=search_po_code))
    else:
        flash(f"PO '{search_po_code}' not found", 'warning')
        if current_po:
            return redirect(url_for('view_po', po_code=current_po))
        else:
            return redirect(url_for('home'))


@app.route('/po/<string:po_code>/delete_line/<int:line_id>')
def delete_line(po_code, line_id):
    # Get the PO first
    purchase_order = db.session.execute(
        db.select(PurchaseOrder).where(PurchaseOrder.po_number == po_code)
    ).scalar_one_or_none()

    if not purchase_order:
        flash('PO not found', 'error')
        return redirect(url_for('home'))


    line = db.session.execute(
        db.select(POLines).where(
            POLines.id == line_id,
            POLines.po_id == purchase_order.id
        )
    ).scalar_one_or_none()

    if not line:
        flash('Line not found', 'error')
        return redirect(url_for('view', po_code=po_code))

    db.session.delete(line)
    db.session.commit()

    # Immedately update PO total
    update_po_total(purchase_order)
    flash('Line deleted and total updated successfully', 'success')

    #Update lines for display
    po_lines = db.session.execute(
        db.select(POLines)
        .where(POLines.po_id == purchase_order.id)
    ).scalars().all()

    return render_template('view.html', purchase_order=purchase_order, po_lines=po_lines)


@app.route('/new_po')
def new_po():
    """Create a fresh new PO"""
    # Clear any potential session data
    return redirect(url_for('add'))

@app.route('/import', methods=['GET', 'POST'])
def import_csv():
    if request.method == 'POST':
        file = request.files.get('file')

        if not file or not file.filename.endswith('.csv'):
            flash('Not a valid file, please use a valid CSV file.', 'error')
            return redirect(url_for('home'))

        try:
            df = pd.read_csv(file)
            required_columns = {'part_number', 'moq', 'unit', 'unit_price', 'supplier',
                                'lead_time', 'family', 'description'}
            if not required_columns.issubset(df.columns):
                flash('File must have titles for each column: part_number, moq, unit, '
                      'unit_price, supplier, lead_time, family, description', 'error')
                return redirect(url_for('import.html'))
            added = 0
            for _,row in df.iterrows():
                try:
                    part_number = str(row['part_number']).strip()
                    moq = str(row['moq']).strip()
                    unit = str(row['unit']).strip()
                    unit_price = str(row['unit_price']).strip()
                    supplier = str(row['supplier']).strip()
                    lead_time = str(row['lead_time']).strip()
                    family = str(row['family']).strip()
                    description = str(row['description']).strip()

                    existing = PartDataBase.query.filter_by(part_number=part_number).first()
                    if not existing:
                        new_part = PartDataBase(
                            part_number=part_number,
                            moq = moq,
                            unit = unit,
                            unit_price = unit_price,
                            supplier = supplier,
                            lead_time = lead_time,
                            family = family,
                            description = description,
                        )
                        db.session.add(new_part)
                        added += 1
                except Exception as e:
                    flash(f"Error trying to process the row: {e}")
                    continue
            db.session.commit()
            flash(f"{added} succesfully imported articles.")
            return redirect(url_for('home'))
        except Exception as e:
            flash(f"Error trying to read the file: {e}")
            return redirect(url_for('home'))
    return render_template('import.html')

@app.route('/lookup_part/<string:part_number>')
def lookup_part(part_number):
    part_record = db.session.execute(db.select(PartDataBase).where(PartDataBase.part_number == part_number)).scalar()

    if part_record:
        return jsonify({
            'found': True,
            'supplier': part_record.supplier,
            'description': part_record.description,
            'unit_price': part_record.unit_price,
            'moq': part_record.moq,
            'unit': part_record.unit,
            'price': part_record.price,
        })
    else:
        return jsonify({'found': False})

if __name__ == '__main__':
    app.run(debug=True)