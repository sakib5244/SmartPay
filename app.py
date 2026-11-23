import os
from datetime import datetime, date
from functools import wraps
from flask import Flask, request, jsonify, session, render_template
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-change-this-secret')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('RENDER', '') == 'true'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
url = os.environ.get('DATABASE_URL', 'sqlite:///smartpay.db')
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(30), unique=True, nullable=False)
    pin_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='customer', nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    balance = db.Column(db.Float, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    actor_id = db.Column(db.Integer)
    type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default='completed')
    description = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(150), default='')
    message = db.Column(db.String(500), default='')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WorkEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, nullable=False)
    customer_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255), default='')
    work_date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Operator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    number = db.Column(db.String(30), default='')
    active = db.Column(db.Boolean, default=True)

class CashoutMeta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, unique=True, nullable=False)
    operator = db.Column(db.String(100), default='')
    number = db.Column(db.String(30), default='')


def notify(uid, title, message):
    db.session.add(Notification(user_id=uid, title=title, message=message))

def me():
    return db.session.get(User, session.get('uid')) if session.get('uid') else None

def user_json(u):
    return {'id':u.id,'name':u.name,'mobile':u.mobile,'role':u.role,'status':u.status,'balance':round(u.balance,2)}

def auth(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not me(): return jsonify(error='Login required'), 401
        return f(*args, **kwargs)
    return inner

def roles(*allowed):
    def deco(f):
        @wraps(f)
        def inner(*args, **kwargs):
            u=me()
            if not u: return jsonify(error='Login required'), 401
            if u.role not in allowed: return jsonify(error='Permission denied'), 403
            return f(*args, **kwargs)
        return inner
    return deco

def amount_ok(v):
    try:
        n=float(v)
        return 0 < n <= 1000000
    except (TypeError, ValueError): return False

@app.route('/')
def index(): return render_template('index.html')

@app.post('/api/register')
def register():
    d=request.get_json(silent=True) or {}
    name=str(d.get('name','')).strip(); mobile=str(d.get('mobile','')).strip(); pin=str(d.get('pin',''))
    if not name or not mobile or len(pin)!=4 or not pin.isdigit(): return jsonify(error='Name, mobile and 4 digit PIN required'),400
    if User.query.filter_by(mobile=mobile).first(): return jsonify(error='Mobile already registered'),409
    u=User(name=name,mobile=mobile,pin_hash=generate_password_hash(pin),role='customer',status='pending',balance=0)
    db.session.add(u); db.session.flush()
    for a in User.query.filter_by(role='admin').all(): notify(a.id,'New Registration',f'{name} ({mobile}) needs approval')
    db.session.commit(); return jsonify(message='Registration submitted. Wait for Admin approval.')

@app.post('/api/login')
def login():
    d=request.get_json(silent=True) or {}; mobile=str(d.get('mobile','')).strip(); pin=str(d.get('pin',''))
    u=User.query.filter_by(mobile=mobile).first()
    if not u or not check_password_hash(u.pin_hash,pin): return jsonify(error='Invalid mobile or PIN'),401
    if u.status!='approved': return jsonify(error='Account '+u.status),403
    session.clear(); session['uid']=u.id; return jsonify(user=user_json(u))

@app.post('/api/logout')
@auth
def logout(): session.clear(); return jsonify(message='Logged out')

@app.get('/api/me')
@auth
def get_me(): return jsonify(user=user_json(me()))

@app.post('/api/change-pin')
@auth
def change_pin():
    d=request.get_json(silent=True) or {}; u=me(); old=str(d.get('old_pin','')); new=str(d.get('new_pin',''))
    if not check_password_hash(u.pin_hash,old): return jsonify(error='Current PIN incorrect'),400
    if len(new)!=4 or not new.isdigit(): return jsonify(error='New PIN must be 4 digits'),400
    u.pin_hash=generate_password_hash(new); db.session.commit(); return jsonify(message='PIN changed')

@app.get('/api/notifications')
@auth
def get_notifications():
    items=Notification.query.filter_by(user_id=me().id).order_by(Notification.id.desc()).limit(100).all()
    return jsonify([{'id':x.id,'title':x.title,'message':x.message,'read':x.is_read,'date':x.created_at.strftime('%Y-%m-%d %H:%M')} for x in items])

@app.post('/api/notifications/read')
@auth
def mark_read():
    d=request.get_json(silent=True) or {}; q=Notification.query.filter_by(user_id=me().id)
    if d.get('all'): q.filter_by(is_read=False).update({'is_read':True})
    else:
        for i in d.get('ids',[]):
            n=q.filter_by(id=i).first()
            if n: n.is_read=True
    db.session.commit(); return jsonify(message='Updated')

@app.get('/api/history')
@auth
def history():
    items=Transaction.query.filter_by(user_id=me().id).order_by(Transaction.id.desc()).limit(150).all()
    return jsonify([{'id':t.id,'type':t.type,'amount':t.amount,'status':t.status,'description':t.description,'date':t.created_at.strftime('%Y-%m-%d %H:%M')} for t in items])

@app.post('/api/cashin')
@roles('agent')
def cashin():
    d=request.get_json(silent=True) or {}; customer=User.query.filter_by(mobile=str(d.get('mobile','')).strip(),role='customer',status='approved').first()
    if not customer: return jsonify(error='Approved customer not found'),404
    if not amount_ok(d.get('amount')): return jsonify(error='Invalid amount'),400
    n=float(d['amount']); agent=me()
    if agent.balance<n: return jsonify(error='Agent balance insufficient'),400
    agent.balance-=n; customer.balance+=n
    db.session.add(Transaction(user_id=customer.id,actor_id=agent.id,type='cashin',amount=n,description=f'Cash In by {agent.mobile}'))
    db.session.add(Transaction(user_id=agent.id,actor_id=agent.id,type='cashin',amount=n,status='completed',description=f'Cash In to {customer.mobile}'))
    notify(customer.id,'Cash In Successful',f'{n:.2f} credited to your account'); db.session.commit()
    return jsonify(message='Cash In successful')

@app.post('/api/cashout')
@auth
def cashout():
    d=request.get_json(silent=True) or {}; u=me(); pin=str(d.get('pin','')); number=str(d.get('number','')).strip(); operator=str(d.get('operator','')).strip()
    if not check_password_hash(u.pin_hash,pin): return jsonify(error='Incorrect PIN'),401
    if not number or not operator or not amount_ok(d.get('amount')): return jsonify(error='Enter operator, number and valid amount'),400
    n=float(d['amount'])
    if u.balance<n: return jsonify(error='Insufficient balance'),400
    u.balance-=n; t=Transaction(user_id=u.id,actor_id=u.id,type='cashout',amount=n,status='pending',description=f'{operator} | {number}')
    db.session.add(t); db.session.flush(); db.session.add(CashoutMeta(transaction_id=t.id,operator=operator,number=number))
    for a in User.query.filter_by(role='admin').all(): notify(a.id,'Cash Out Request',f'{u.mobile} requested {n:.2f}')
    notify(u.id,'Cash Out Pending','Request submitted; waiting for admin review'); db.session.commit()
    return jsonify(message='Cash Out request submitted',receipt={'id':t.id,'amount':n,'operator':operator,'number':number,'status':'pending'})

@app.get('/api/operators')
@auth
def operators(): return jsonify([{'id':o.id,'name':o.name,'number':o.number} for o in Operator.query.filter_by(active=True).all()])

@app.get('/api/work')
@auth
def work_list():
    u=me(); q=WorkEntry.query
    if u.role=='agent': q=q.filter_by(agent_id=u.id)
    elif u.role=='customer': q=q.filter_by(customer_id=u.id)
    rows=q.order_by(WorkEntry.id.desc()).limit(200).all(); out=[]
    for w in rows:
        c=db.session.get(User,w.customer_id); a=db.session.get(User,w.agent_id)
        out.append({'id':w.id,'agent':a.mobile if a else '', 'customer':c.mobile if c else '', 'customer_name':c.name if c else '', 'amount':w.amount,'description':w.description,'date':w.work_date.isoformat()})
    return jsonify(out)

@app.post('/api/work')
@roles('agent')
def add_work():
    d=request.get_json(silent=True) or {}; c=User.query.filter_by(mobile=str(d.get('mobile','')).strip(),role='customer',status='approved').first()
    if not c: return jsonify(error='Approved customer not found'),404
    if not amount_ok(d.get('amount')): return jsonify(error='Invalid amount'),400
    try: wd=date.fromisoformat(str(d.get('date') or date.today().isoformat()))
    except ValueError: return jsonify(error='Invalid date'),400
    if wd.weekday()>4: return jsonify(error='Workday must be Monday to Friday'),400
    n=float(d['amount']); c.balance+=n; a=me()
    db.session.add(WorkEntry(agent_id=a.id,customer_id=c.id,amount=n,description=str(d.get('description',''))[:255],work_date=wd))
    db.session.add(Transaction(user_id=c.id,actor_id=a.id,type='work',amount=n,description='Work List Credit'))
    db.session.add(Transaction(user_id=a.id,actor_id=a.id,type='work',amount=n,description=f'Work credited to {c.mobile}'))
    notify(c.id,'Work Payment',f'{n:.2f} added to your balance'); db.session.commit(); return jsonify(message='Work added')

@app.get('/api/admin/users')
@roles('admin')
def admin_users(): return jsonify([user_json(u) for u in User.query.order_by(User.id.desc()).all()])

@app.post('/api/admin/approve/<int:uid>')
@roles('admin')
def approve(uid):
    u=db.session.get(User,uid)
    if not u or u.role!='customer': return jsonify(error='Customer not found'),404
    u.status='approved'; notify(u.id,'Account Approved','Your SmartPay account is approved'); db.session.commit(); return jsonify(message='Approved')

@app.post('/api/admin/reject/<int:uid>')
@roles('admin')
def reject(uid):
    d=request.get_json(silent=True) or {}; u=db.session.get(User,uid)
    if not u or u.role!='customer': return jsonify(error='Customer not found'),404
    u.status='rejected'; notify(u.id,'Registration Rejected',str(d.get('reason','Registration rejected'))[:500]); db.session.commit(); return jsonify(message='Rejected')

@app.post('/api/admin/create-agent')
@roles('admin')
def create_agent():
    d=request.get_json(silent=True) or {}; name=str(d.get('name','')).strip(); mobile=str(d.get('mobile','')).strip(); pin=str(d.get('pin',''))
    if not name or not mobile or len(pin)!=4 or not pin.isdigit(): return jsonify(error='Enter name, mobile and 4-digit PIN'),400
    if User.query.filter_by(mobile=mobile).first(): return jsonify(error='Mobile already exists'),409
    db.session.add(User(name=name,mobile=mobile,pin_hash=generate_password_hash(pin),role='agent',status='approved',balance=0)); db.session.commit(); return jsonify(message='Agent created')

@app.post('/api/admin/balance')
@roles('admin')
def balance_manager():
    d=request.get_json(silent=True) or {}; u=User.query.filter_by(mobile=str(d.get('mobile','')).strip()).first()
    if not u: return jsonify(error='User not found'),404
    if not amount_ok(d.get('amount')): return jsonify(error='Invalid amount'),400
    n=float(d['amount']); action=d.get('action')
    if action=='add': u.balance+=n
    elif action=='subtract':
        if u.balance<n: return jsonify(error='Insufficient balance'),400
        u.balance-=n
    else: return jsonify(error='Invalid action'),400
    db.session.add(Transaction(user_id=u.id,actor_id=me().id,type='adjustment',amount=n,description=f'Admin {action} balance'))
    notify(u.id,'Balance Updated',f'Admin updated balance by {n:.2f}'); db.session.commit(); return jsonify(message='Balance updated')

@app.get('/api/admin/cashouts')
@roles('admin')
def admin_cashouts():
    ts=Transaction.query.filter_by(type='cashout').order_by(Transaction.id.desc()).all(); out=[]
    for t in ts:
        u=db.session.get(User,t.user_id); m=CashoutMeta.query.filter_by(transaction_id=t.id).first()
        out.append({'id':t.id,'mobile':u.mobile if u else '', 'name':u.name if u else '', 'amount':t.amount,'status':t.status,'description':t.description,'operator':m.operator if m else '', 'number':m.number if m else '', 'date':t.created_at.strftime('%Y-%m-%d %H:%M')})
    return jsonify(out)

@app.post('/api/admin/cashout/<int:tid>')
@roles('admin')
def decide_cashout(tid):
    d=request.get_json(silent=True) or {}; t=db.session.get(Transaction,tid)
    if not t or t.type!='cashout': return jsonify(error='Request not found'),404
    if t.status!='pending': return jsonify(error='Already processed'),400
    u=db.session.get(User,t.user_id); action=d.get('action')
    if action=='approve': t.status='approved'; notify(u.id,'Cash Out Approved',f'Cash out {t.amount:.2f} approved')
    elif action=='reject': t.status='rejected'; u.balance+=t.amount; notify(u.id,'Cash Out Rejected',f'{t.amount:.2f} refunded to your balance')
    elif action=='complete':
        if t.status!='approved': return jsonify(error='Approve first'),400
        t.status='completed'; notify(u.id,'Cash Out Completed','Your cash out is completed')
    else: return jsonify(error='Invalid action'),400
    db.session.commit(); return jsonify(message='Updated')

@app.post('/api/admin/operator')
@roles('admin')
def add_operator():
    d=request.get_json(silent=True) or {}; name=str(d.get('name','')).strip(); number=str(d.get('number','')).strip()
    if not name: return jsonify(error='Operator name required'),400
    db.session.add(Operator(name=name,number=number)); db.session.commit(); return jsonify(message='Operator added')

@app.post('/api/admin/operator/<int:oid>/delete')
@roles('admin')
def delete_operator(oid):
    o=db.session.get(Operator,oid)
    if o: o.active=False; db.session.commit()
    return jsonify(message='Deleted')

@app.get('/health')
def health(): return jsonify(status='ok')

with app.app_context():
    db.create_all()
    if not User.query.filter_by(mobile='admin').first(): db.session.add(User(name='Administrator',mobile='admin',pin_hash=generate_password_hash('1234'),role='admin',status='approved',balance=0))
    if not User.query.filter_by(mobile='01700000001').first(): db.session.add(User(name='Demo Agent',mobile='01700000001',pin_hash=generate_password_hash('1111'),role='agent',status='approved',balance=10000))
    if not User.query.filter_by(mobile='01700000002').first(): db.session.add(User(name='Demo Customer',mobile='01700000002',pin_hash=generate_password_hash('2222'),role='customer',status='approved',balance=500))
    if not Operator.query.first():
        db.session.add_all([Operator(name='Bkash'),Operator(name='Nagad'),Operator(name='Rocket')])
    db.session.commit()

if __name__=='__main__': app.run(host='0.0.0.0',port=5000,debug=False)
