# SmartPay Demo (Flask + PostgreSQL)

This is a demo wallet/ledger app. It does **not** connect to real payment providers or move real money.

## Included
- Customer registration and admin approval/rejection with reason notification
- Admin, Agent, Customer login roles
- Agent cash-in (ledger transfer)
- Customer cash-out requests, admin approval/rejection/refund, completion status
- Agent work entries, Monday-Friday date validation
- Transaction history, notifications and read/unread state
- Admin agent creation, balance manager and operator list
- PIN change, Bengali/English toggle, dark/light theme
- PostgreSQL for persistent hosted data; SQLite fallback for local development

## Demo logins (change before public use)
- Admin: `admin` / `1234`
- Agent: `01700000001` / `1111`
- Customer: `01700000002` / `2222`

## Local run
1. Install Python 3.10+.
2. Run `pip install -r requirements.txt`.
3. Run `python app.py`.
4. Open http://127.0.0.1:5000

## Render
1. Push the project to a GitHub repository.
2. In Render, create a Web Service from the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Create a Render PostgreSQL database and set `DATABASE_URL` to its internal connection string.
6. Set a strong random `SECRET_KEY` environment variable.
7. Deploy and open the service URL.

`render.yaml` describes a web service and database; verify plan availability in Render before deploying.

## Security notes
- Demo seed credentials are created when the database is empty. Change/remove them before public deployment.
- Use HTTPS, strong secret, rate limiting, CSRF protection, backups, audit controls, and reviewed authorization before any production use.
- Cash-out approvals are administrative simulation only; the app does not send money.
