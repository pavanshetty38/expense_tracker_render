import os
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import datetime
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')
# SQLite for simplicity; on Render you can switch to Postgres by changing SQLALCHEMY_DATABASE_URI env var.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    budget = db.Column(db.Float, default=0.0)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))
    note = db.Column(db.String(200))
    date = db.Column(db.Date, default=datetime.date.today)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def create_tables():
    db.create_all()

def send_email(to_email, subject, body):
    # Simple SMTP email sender. Configure these env vars on Render:
    # MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS (true/false)
    mail_server = os.environ.get('MAIL_SERVER')
    if not mail_server:
        print('MAIL_SERVER not configured; skipping email.')
        return False
    port = int(os.environ.get('MAIL_PORT', 587))
    username = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    use_tls = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = username
    msg['To'] = to_email
    try:
        server = smtplib.SMTP(mail_server, port, timeout=10)
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.sendmail(username, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print('Error sending email:', e)
        return False

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        user = User(email=email, password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('Account created — please log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard', methods=['GET','POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        # add expense
        amount = float(request.form['amount'])
        category = request.form.get('category', 'Other')
        note = request.form.get('note', '')
        expense = Expense(user_id=current_user.id, amount=amount, category=category, note=note)
        db.session.add(expense)
        db.session.commit()
        # check budget and potentially send email
        if current_user.budget and current_user.budget > 0:
            total_spent = db.session.query(db.func.sum(Expense.amount)).filter_by(user_id=current_user.id).scalar() or 0
            remaining = current_user.budget - total_spent
            if remaining / current_user.budget <= 0.20:
                # send warning email
                send_email(current_user.email,
                           'Budget Alert — less than 20% remaining',
                           f'Hi, your remaining budget is ₹{remaining:.2f} which is ≤20% of your original budget.')
        return redirect(url_for('dashboard'))
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    # prepare data for chart: category totals
    from collections import defaultdict
    cat = defaultdict(float)
    for e in expenses:
        cat[e.category] += e.amount
    categories = list(cat.keys()) or ['No expenses']
    values = [round(cat[k],2) for k in categories]
    total_spent = sum(values)
    budget = current_user.budget or 0
    remaining = budget - total_spent
    percent_used = (total_spent / budget * 100) if budget>0 else 0
    return render_template('dashboard.html',
                           expenses=expenses,
                           categories=categories,
                           values=values,
                           total_spent=total_spent,
                           budget=budget,
                           remaining=remaining,
                           percent_used=round(percent_used,1))

@app.route('/set_budget', methods=['POST'])
@login_required
def set_budget():
    b = float(request.form.get('budget',0))
    current_user.budget = b
    db.session.commit()
    flash('Budget updated', 'success')
    return redirect(url_for('dashboard'))

@app.route('/export_pdf')
@login_required
def export_pdf():
    # Simple PDF summary using reportlab
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont('Helvetica', 12)
    y = 750
    p.drawString(50, y, f'Expense Report for {current_user.email}')
    y -= 30
    p.drawString(50, y, f'Date: {datetime.date.today().isoformat()}')
    y -= 30
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).limit(50).all()
    for e in expenses:
        line = f'{e.date.isoformat()} | {e.category} | ₹{e.amount:.2f} | {e.note}'
        p.drawString(50, y, line[:90])
        y -= 20
        if y < 50:
            p.showPage()
            y = 750
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='expense_report.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
