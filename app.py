import os
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, session, render_template
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'replace-this-secret-before-production')
url = os.environ.get('DATABASE_URL', 'sqlite:///smartpay.db')
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql+psycopg2://', 1)
elif url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg2://', 1)
elif url.startswith('postgresql+psycopg://'):
    url = url.replace('postgresql+psycopg://', 'postgresql+psycopg2://', 1)
app.config.update(SQLALCHEMY_DATABASE_URI=url, SQLALCHEMY_TRACK_MODIFICATIONS=False,
                 SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Lax')
db = SQLAlchemy(app)

class User(db.Model):
    id=db.Column(db.Integer, primary_key=True); name=db.Column(db.String(100), default=''); mobile=db.Column(db.String(30), unique=True, nullable=False); pin_hash=db.Column(db.String(255), nullable=False); role=db.Column(db.String(20), default='customer'); status=db.Column(db.String(20), default='pending'); balance=db.Column(db.Float, default=0)
class Transaction(db.Model):
    id=db.Column(db.Integer, primary_key=True); user_id=db.Column(db.Integer, nullable=False); actor_id=db.Column(db.Integer); type=db.Column(db.String(30), nullable=False); amount=db.Column(db.Float, nullable=False); status=db.Column(db.String(30), default='completed'); description=db.Column(db.String(255), default=''); created_at=db.Column(db.DateTime, default=datetime.utcnow)
class Notification(db.Model):
    id=db.Column(db.Integer, primary_key=True); user_id=db.Column(db.Integer, nullable=False); title=db.Column(db.String(150), default=''); message=db.Column(db.String(500), default=''); is_read=db.Column(db.Boolean, default=False); created_at=db.Column(db.DateTime, default=datetime.utcnow)
class WorkEntry(db.Model):
    id=db.Column(db.Integer, primary_key=True); agent_id=db.Column(db.Integer, nullable=False); customer_id=db.Column(db.Integer, nullable=False); amount=db.Column(db.Float, nullable=False); description=db.Column(db.String(255), default=''); week=db.Column(db.String(20), default=''); created_at=db.Column(db.DateTime, default=datetime.utcnow)
class Operator(db.Model):
    id=db.Column(db.Integer, primary_key=True); name=db.Column(db.String(100), nullable=False); number=db.Column(db.String(30), default=''); active=db.Column(db.Boolean, default=True)

def notify(uid,title,msg): db.session.add(Notification(user_id=uid,title=title,message=msg))
def current():
 u=db.session.get(User, session.get('uid')) if session.get('uid') else None
 return u if u and u.status=='approved' else None
def user_json(u): return {'id':u.id,'name':u.name,'mobile':u.mobile,'role':u.role,'status':u.status,'balance':round(u.balance or 0,2)}
def login_required(fn):
 @wraps(fn)
 def wrapper(*a,**kw):
  if not current(): return jsonify(error='Login required'),401
  return fn(*a,**kw)
 return wrapper
def roles(*allowed):
 def deco(fn):
  @wraps(fn)
  def wrapper(*a,**kw):
   u=current()
   if not u: return jsonify(error='Login required'),401
   if u.role not in allowed: return jsonify(error='Permission denied'),403
   return fn(*a,**kw)
  return wrapper
 return deco
def amount_ok(v):
 try: x=float(v); return 0<x<=1000000
 except (ValueError,TypeError): return False

with app.app_context():
 db.create_all()
 if not User.query.filter_by(mobile='admin').first(): db.session.add(User(name='Administrator',mobile='admin',pin_hash=generate_password_hash('1234'),role='admin',status='approved',balance=0))
 if not User.query.filter_by(mobile='01700000001').first(): db.session.add(User(name='Demo Agent',mobile='01700000001',pin_hash=generate_password_hash('1111'),role='agent',status='approved',balance=10000))
 if not User.query.filter_by(mobile='01700000002').first(): db.session.add(User(name='Demo Customer',mobile='01700000002',pin_hash=generate_password_hash('2222'),role='customer',status='approved',balance=500))
 db.session.commit()

@app.get('/')
def home(): return render_template('index.html')
@app.get('/health')
def health(): return jsonify(status='ok')
@app.post('/api/register')
def register():
 d=request.get_json(silent=True) or {}; name=str(d.get('name','')).strip(); mobile=str(d.get('mobile','')).strip(); pin=str(d.get('pin',''))
 if not name or not mobile or len(pin)!=4 or not pin.isdigit(): return jsonify(error='Enter name, mobile and 4-digit PIN'),400
 if User.query.filter_by(mobile=mobile).first(): return jsonify(error='Mobile already registered'),409
 u=User(name=name,mobile=mobile,pin_hash=generate_password_hash(pin),role='customer',status='pending',balance=0); db.session.add(u); db.session.flush()
 for admin in User.query.filter_by(role='admin'): notify(admin.id,'New Registration',f'{name} ({mobile}) requires approval.')
 db.session.commit(); return jsonify(message='Registration submitted. Wait for admin approval.')
@app.post('/api/login')
def login():
 d=request.get_json(silent=True) or {}; u=User.query.filter_by(mobile=str(d.get('mobile','')).strip()).first()
 if not u or not check_password_hash(u.pin_hash,str(d.get('pin',''))): return jsonify(error='Invalid mobile or PIN'),401
 if u.status!='approved': return jsonify(error='Account status: '+u.status),403
 session.clear();session['uid']=u.id;return jsonify(user=user_json(u))
@app.post('/api/logout')
@login_required
def logout(): session.clear();return jsonify(message='Logged out')
@app.get('/api/me')
@login_required
def me(): return jsonify(user=user_json(current()))
@app.post('/api/pin')
@login_required
def pin_change():
 d=request.get_json(silent=True) or {};u=current()
 if not check_password_hash(u.pin_hash,str(d.get('old',''))):return jsonify(error='Current PIN incorrect'),400
 new=str(d.get('new',''))
 if len(new)!=4 or not new.isdigit():return jsonify(error='PIN must be 4 digits'),400
 u.pin_hash=generate_password_hash(new);db.session.commit();return jsonify(message='PIN changed')
@app.post('/api/account/delete')
@login_required
def deactivate_account():
 d=request.get_json(silent=True) or {};u=current()
 if u.role=='admin': return jsonify(error='Admin account cannot be deactivated here'),403
 if not check_password_hash(u.pin_hash,str(d.get('pin',''))): return jsonify(error='Incorrect PIN'),401
 u.status='deactivated'
 notify(u.id,'অ্যাকাউন্ট নিষ্ক্রিয়','আপনার অ্যাকাউন্ট নিষ্ক্রিয় করা হয়েছে। সহায়তার জন্য অ্যাডমিনের সাথে যোগাযোগ করুন।')
 db.session.commit();session.clear()
 return jsonify(message='অ্যাকাউন্ট নিষ্ক্রিয় করা হয়েছে')

@app.get('/api/notifications')
@login_required
def notifications():
 return jsonify([{'id':n.id,'title':n.title,'message':n.message,'read':n.is_read,'date':n.created_at.strftime('%Y-%m-%d %H:%M')} for n in Notification.query.filter_by(user_id=current().id).order_by(Notification.id.desc()).all()])
@app.post('/api/notifications/read')
@login_required
def read_notifications():
 d=request.get_json(silent=True) or {};q=Notification.query.filter_by(user_id=current().id)
 if d.get('all'):q.filter_by(is_read=False).update({'is_read':True})
 else:
  for nid in d.get('ids',[]):
   n=q.filter_by(id=nid).first()
   if n:n.is_read=True
 db.session.commit();return jsonify(message='Updated')
@app.get('/api/admin/users')
@roles('admin')
def admin_users():return jsonify([user_json(u) for u in User.query.order_by(User.id.desc()).all()])
@app.post('/api/admin/approve/<int:uid>')
@roles('admin')
def approve(uid):
 u=db.session.get(User,uid)
 if not u:return jsonify(error='User not found'),404
 u.status='approved';notify(u.id,'Account Approved','Your SmartPay account is approved.');db.session.commit();return jsonify(message='Approved')
@app.post('/api/admin/reject/<int:uid>')
@roles('admin')
def reject(uid):
 d=request.get_json(silent=True) or {};u=db.session.get(User,uid)
 if not u:return jsonify(error='User not found'),404
 u.status='rejected';notify(u.id,'Registration Rejected',str(d.get('reason','Registration rejected')));db.session.commit();return jsonify(message='Rejected')
@app.post('/api/admin/create-agent')
@roles('admin')
def create_agent():
 d=request.get_json(silent=True) or {};name=str(d.get('name','')).strip();mobile=str(d.get('mobile','')).strip();pin=str(d.get('pin',''))
 if not name or not mobile or len(pin)!=4 or not pin.isdigit():return jsonify(error='Invalid information'),400
 if User.query.filter_by(mobile=mobile).first():return jsonify(error='Mobile exists'),409
 db.session.add(User(name=name,mobile=mobile,pin_hash=generate_password_hash(pin),role='agent',status='approved',balance=0));db.session.commit();return jsonify(message='Agent created')
@app.post('/api/admin/balance')
@roles('admin')
def balance_manager():
 d=request.get_json(silent=True) or {};u=User.query.filter_by(mobile=d.get('mobile')).first();v=d.get('amount')
 if not u:return jsonify(error='User not found'),404
 if not amount_ok(v):return jsonify(error='Invalid amount'),400
 v=float(v)
 if d.get('action')=='subtract' and u.balance<v:return jsonify(error='Insufficient balance'),400
 if d.get('action')=='add':u.balance+=v
 elif d.get('action')=='subtract':u.balance-=v
 else:return jsonify(error='Invalid action'),400
 db.session.add(Transaction(user_id=u.id,actor_id=current().id,type='adjustment',amount=v,description='Admin balance '+d['action']));notify(u.id,'Balance Updated',f'Balance adjustment: {v}');db.session.commit();return jsonify(message='Balance updated')
@app.post('/api/cashin')
@roles('agent')
def cashin():
 d=request.get_json(silent=True) or {};c=User.query.filter_by(mobile=str(d.get('mobile','')).strip(),role='customer',status='approved').first();v=d.get('amount');a=current()
 if not c:return jsonify(error='Approved customer not found'),404
 if not amount_ok(v):return jsonify(error='Invalid amount'),400
 v=float(v)
 if a.balance<v:return jsonify(error='Agent balance insufficient'),400
 a.balance-=v;c.balance+=v;db.session.add(Transaction(user_id=c.id,actor_id=a.id,type='cashin',amount=v,description=f'Cash In by {a.mobile}'));notify(c.id,'Cash In Successful',f'{v} credited');db.session.commit();return jsonify(message='Cash In successful')
@app.post('/api/cashout')
@login_required
def cashout():
 d=request.get_json(silent=True) or {};u=current();v=d.get('amount');pin=str(d.get('pin',''))
 if not check_password_hash(u.pin_hash,pin):return jsonify(error='Incorrect PIN'),401
 if not amount_ok(v):return jsonify(error='Invalid amount'),400
 v=float(v)
 if u.balance<v:return jsonify(error='Insufficient balance'),400
 u.balance-=v;t=Transaction(user_id=u.id,actor_id=u.id,type='cashout',amount=v,status='pending',description=f"{d.get('operator','')} | {d.get('number','')}");db.session.add(t);db.session.flush()
 for a in User.query.filter_by(role='admin'):notify(a.id,'Cash Out Request',f'{u.mobile} requested {v}')
 notify(u.id,'Cash Out Pending','Request submitted');db.session.commit();return jsonify(message='Cash Out request submitted',invoice={'id':t.id,'amount':round(v,2),'operator':str(d.get('operator','')),'number':str(d.get('number','')),'date':t.created_at.strftime('%Y-%m-%d %H:%M:%S'),'status':t.status,'mobile':u.mobile,'name':u.name})
@app.get('/api/admin/cashouts')
@roles('admin')
def admin_cashouts():
 out=[]
 for t in Transaction.query.filter_by(type='cashout').order_by(Transaction.id.desc()).all():
  u=db.session.get(User,t.user_id);out.append({'id':t.id,'mobile':u.mobile if u else '', 'name':u.name if u else '', 'amount':t.amount,'status':t.status,'description':t.description,'date':t.created_at.strftime('%Y-%m-%d %H:%M')})
 return jsonify(out)
@app.post('/api/admin/cashout/<int:tid>')
@roles('admin')
def cashout_decision(tid):
 d=request.get_json(silent=True) or {};t=db.session.get(Transaction,tid)
 if not t or t.type!='cashout':return jsonify(error='Not found'),404
 if t.status!='pending':return jsonify(error='Already processed'),400
 u=db.session.get(User,t.user_id)
 if d.get('action')=='approve':t.status='approved';notify(u.id,'Cash Out Approved','Cash out approved')
 elif d.get('action')=='reject':t.status='rejected';u.balance+=t.amount;notify(u.id,'Cash Out Rejected','Amount refunded')
 else:return jsonify(error='Invalid action'),400
 db.session.commit();return jsonify(message='Updated')
@app.get('/api/work')
@login_required
def get_work():
 u=current();q=WorkEntry.query
 if u.role=='agent':q=q.filter_by(agent_id=u.id)
 elif u.role=='customer':q=q.filter_by(customer_id=u.id)
 out=[]
 for w in q.order_by(WorkEntry.id.desc()).all():
  c=db.session.get(User,w.customer_id);a=db.session.get(User,w.agent_id);out.append({'id':w.id,'agent':a.mobile if a else '', 'customer':c.mobile if c else '', 'customer_name':c.name if c else '', 'amount':w.amount,'description':w.description,'week':w.week,'date':w.created_at.strftime('%Y-%m-%d')})
 return jsonify(out)
@app.get('/api/customer/<mobile>')
@roles('agent')
def lookup_customer(mobile):
 c=User.query.filter_by(mobile=str(mobile).strip(),role='customer',status='approved').first()
 if not c:return jsonify(error='অনুমোদিত কাস্টমার পাওয়া যায়নি'),404
 return jsonify(id=c.id,name=c.name,mobile=c.mobile)

@app.post('/api/work')
@roles('agent')
def add_work():
 d=request.get_json(silent=True) or {};c=User.query.filter_by(mobile=str(d.get('mobile','')).strip(),role='customer',status='approved').first();v=d.get('amount')
 if not c:return jsonify(error='Approved customer not found'),404
 if not amount_ok(v):return jsonify(error='Invalid amount'),400
 cutoff=datetime.utcnow()-timedelta(hours=12)
 recent=WorkEntry.query.filter(WorkEntry.customer_id==c.id,WorkEntry.created_at>=cutoff).first()
 if recent:return jsonify(error='এই অ্যাকাউন্টে সর্বশেষ কাজ দেওয়ার ১২ ঘণ্টা পূর্ণ হয়নি।'),429
 v=float(v);c.balance+=v;w=WorkEntry(agent_id=current().id,customer_id=c.id,amount=v,description=str(d.get('description','')),week=datetime.utcnow().strftime('%G-W%V'));db.session.add(w);db.session.add(Transaction(user_id=c.id,actor_id=current().id,type='work',amount=v,description='Work List Credit'));notify(c.id,'নতুন কাজ যুক্ত হয়েছে',f'আপনার জন্য {v:.2f} টাকা পরিমাণের নতুন কাজ যুক্ত হয়েছে। বিস্তারিত জানতে আপনার Work List দেখুন।');db.session.commit();return jsonify(message='কাজ সফলভাবে যুক্ত হয়েছে।')
@app.get('/api/history')
@login_required
def history():
 return jsonify([{'id':t.id,'type':t.type,'amount':t.amount,'status':t.status,'description':t.description,'date':t.created_at.strftime('%Y-%m-%d %H:%M')} for t in Transaction.query.filter_by(user_id=current().id).order_by(Transaction.id.desc()).limit(200).all()])
@app.get('/api/operators')
@login_required
def operators():return jsonify([{'id':o.id,'name':o.name,'number':o.number} for o in Operator.query.filter_by(active=True).all()])
@app.post('/api/admin/operator')
@roles('admin')
def add_operator():
 d=request.get_json(silent=True) or {};n=str(d.get('name','')).strip()
 if not n:return jsonify(error='Name required'),400
 db.session.add(Operator(name=n,number=str(d.get('number',''))));db.session.commit();return jsonify(message='Added')
@app.post('/api/admin/operator/<int:oid>/delete')
@roles('admin')
def delete_operator(oid):
 o=db.session.get(Operator,oid)
 if o:o.active=False;db.session.commit()
 return jsonify(message='Deleted')
if __name__=='__main__':app.run(debug=False)
