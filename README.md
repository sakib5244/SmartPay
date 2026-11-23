# SmartPay Render project (PostgreSQL driver fix)

## Files
- `app.py` Flask backend
- `templates/index.html` frontend
- `requirements.txt` dependencies
- `render.yaml` Render Blueprint config

## Render settings
Build command: `pip install -r requirements.txt`
Start command: `gunicorn app:app`
Environment variables: `DATABASE_URL` (Postgres Internal URL), `SECRET_KEY` (random secret)

The database URL is normalized to `postgresql+psycopg2://` to use the installed `psycopg2-binary` driver and avoid `ModuleNotFoundError: psycopg`.

Demo accounts (change/remove before production):
- Admin: `admin` / `1234`
- Agent: `01700000001` / `1111`
- Customer: `01700000002` / `2222`

Demo only. No real payment processing. Review security, permissions, and business rules before production use.
