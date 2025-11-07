# Expense Tracker (Flask)

Features:
- User registration & login (Flask-Login)
- Add expenses (category, amount, note)
- Dashboard with Chart.js pie chart and percentage used
- Email notifications when remaining budget <= 20% (configure SMTP env vars)
- PDF export (reportlab)
- Ready for deploy to Render.com

Render notes:
- Set environment variables in Render dashboard:
  - SECRET_KEY
  - DATABASE_URL (optional; defaults to sqlite:///data.db)
  - MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS
  - PYTHON_VERSION if you want to override (or keep .python-version)
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

