import os, sqlite3, re, secrets, hashlib, hmac, httpx
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from shared_security import issue, current, require
DB=os.getenv('DB_PATH','/data/identity.db'); BOOT=os.getenv('BANK_BOOTSTRAP_SECRET','change-bootstrap-secret-please-32-chars'); NOTIFY=os.getenv('NOTIFICATION_URL','http://notification-service:8000'); INTERNAL=os.getenv('INTERNAL_SECRET','internal-secret-change-me'); GOOGLE_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID','')
app=FastAPI(title='Identity Service')
def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
@app.on_event('startup')
def init():
 os.makedirs(os.path.dirname(DB),exist_ok=True)
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,full_name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE',email_verified INTEGER NOT NULL DEFAULT 1,branch_name TEXT NOT NULL DEFAULT '',google_sub TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
  cols={r[1] for r in c.execute('PRAGMA table_info(users)')}
  for col,ddl in [('email_verified','INTEGER NOT NULL DEFAULT 1'),('branch_name',"TEXT NOT NULL DEFAULT ''"),('google_sub','TEXT')]:
   if col not in cols: c.execute(f'ALTER TABLE users ADD COLUMN {col} {ddl}')
  c.execute("UPDATE users SET branch_name='Main Branch' WHERE role IN ('EMPLOYEE','MANAGER') AND branch_name=''")
class Credentials(BaseModel): email: str; password: str
class Registration(BaseModel): fullName: str; email: str; password: str
class Bootstrap(Registration): bootstrapSecret: str
class Staff(Registration): role: str; branchName: str=''

def hashpw(p):
 salt=secrets.token_bytes(16); return salt.hex()+':'+hashlib.scrypt(p.encode(),salt=salt,n=2**14,r=8,p=1).hex()
def checkpw(p,h):
 try: s,d=h.split(':'); return hmac.compare_digest(hashlib.scrypt(p.encode(),salt=bytes.fromhex(s),n=2**14,r=8,p=1).hex(),d)
 except Exception: return False
def create(b,role,verified=True,branch_name=''):
 name=b.fullName.strip(); email=b.email.strip().lower(); pw=b.password
 if not name or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$',email): raise HTTPException(400,'Enter a valid name and email.')
 if len(pw)<10 or len(pw)>72 or not re.search('[A-Za-z]',pw) or not re.search('[0-9]',pw): raise HTTPException(400,'Password must be 10–72 characters and include letters and numbers.')
 try:
  with db() as c: cur=c.execute('INSERT INTO users(full_name,email,password_hash,role,email_verified,branch_name) VALUES(?,?,?,?,?,?)',(name,email,hashpw(pw),role,1 if verified else 0,branch_name)); uid=cur.lastrowid
 except sqlite3.IntegrityError: raise HTTPException(409,'An account with this email already exists.')
 return {'id':uid,'fullName':name,'email':email,'role':role,'status':'ACTIVE','emailVerified':verified,'branch':branch_name}
@app.post('/api/auth/register')
async def register(b:Registration):
 user=create(b,'CUSTOMER',verified=False)
 async with httpx.AsyncClient(timeout=10) as x:
  r=await x.post(NOTIFY+'/internal/email-otp',json={'email':user['email'],'purpose':'EMAIL_VERIFY','name':user['fullName']},headers={'X-Internal-Secret':INTERNAL})
  if r.status_code>=400: raise HTTPException(503,'Account created but verification email could not be sent. Check SMTP settings and request a new code.')
 return {'message':'Registration started. Enter the verification code sent to your email.','user':user,'verificationRequired':True}
class VerifyEmail(BaseModel): email:str; otp:str
@app.post('/api/auth/verify-email')
async def verify_email(b:VerifyEmail):
 async with httpx.AsyncClient(timeout=8) as x: r=await x.post(NOTIFY+'/internal/verify-otp',json={'email':b.email.strip().lower(),'purpose':'EMAIL_VERIFY','otp':b.otp},headers={'X-Internal-Secret':INTERNAL})
 if r.status_code>=400: raise HTTPException(400,'Verification code is invalid or expired.')
 with db() as c: cur=c.execute("UPDATE users SET email_verified=1 WHERE email=? AND role='CUSTOMER'",(b.email.strip().lower(),))
 if not cur.rowcount: raise HTTPException(404,'Customer registration not found.')
 return {'message':'Email verified. You can now sign in.'}
@app.post('/api/auth/resend-verification')
async def resend_verification(b:Credentials):
 with db() as c: u=c.execute('SELECT full_name,email,email_verified,password_hash FROM users WHERE email=?',(b.email.strip().lower(),)).fetchone()
 if not u or not checkpw(b.password,u['password_hash']): raise HTTPException(401,'Email or password is incorrect.')
 if u['email_verified']: return {'message':'Email is already verified.'}
 async with httpx.AsyncClient(timeout=8) as x: r=await x.post(NOTIFY+'/internal/email-otp',json={'email':u['email'],'purpose':'EMAIL_VERIFY','name':u['full_name']},headers={'X-Internal-Secret':INTERNAL})
 if r.status_code>=400: raise HTTPException(503,'Could not send verification email.')
 return {'message':'Verification code sent.'}
@app.post('/api/auth/bootstrap-admin')
def bootstrap(b:Bootstrap):
 if not hmac.compare_digest(BOOT,b.bootstrapSecret): raise HTTPException(403,'Invalid bootstrap secret.')
 with db() as c:
  if c.execute("SELECT count(*) FROM users WHERE role='ADMIN'").fetchone()[0]: raise HTTPException(409,'Administrator bootstrap already completed.')
 return {'message':'Initial administrator created. Sign in now.','user':create(b,'ADMIN')}
@app.post('/api/auth/login')
def login(b:Credentials):
 with db() as c: u=c.execute("SELECT * FROM users WHERE email=? AND status='ACTIVE'",(b.email.strip().lower(),)).fetchone()
 if not u or not checkpw(b.password,u['password_hash']): raise HTTPException(401,'Email or password is incorrect.')
 if not u['email_verified']: raise HTTPException(403,'Verify your email before signing in.')
 token=issue(u['id'],u['email'],u['role'],u['full_name'],u['branch_name'])
 return {'accessToken':token,'tokenType':'Bearer','expiresIn':900,'user':{'id':u['id'],'fullName':u['full_name'],'email':u['email'],'role':u['role'],'branch':u['branch_name']}}
@app.post('/api/auth/users')
def staff(b:Staff,user=Depends(current)):
 require(user,'ADMIN')
 if b.role not in ('EMPLOYEE','MANAGER'): raise HTTPException(400,'Role must be EMPLOYEE or MANAGER.')
 if not b.branchName.strip(): raise HTTPException(400,'Branch is required for all staff accounts.')
 if b.branchName.strip() not in ('Main Branch','Guntur Branch','Vijayawada Branch','Amaravati Branch','Visakhapatnam Branch','Hyderabad Branch'): raise HTTPException(400,'Choose a valid branch.')
 return {'user':create(b,b.role,verified=True,branch_name=b.branchName.strip())}
@app.get('/api/auth/me')
def me(user=Depends(current)): return user
@app.get('/health')
def health(): return {'status':'UP','service':'identity-service'}

class GoogleCredential(BaseModel): credential:str
@app.post('/api/auth/google')
async def google_login(b:GoogleCredential):
 if not GOOGLE_CLIENT_ID: raise HTTPException(503,'Google sign-in is not configured. Set GOOGLE_CLIENT_ID and rebuild the frontend.')
 async with httpx.AsyncClient(timeout=8) as x:
  r=await x.get('https://oauth2.googleapis.com/tokeninfo',params={'id_token':b.credential})
 if r.status_code!=200: raise HTTPException(401,'Google credential is invalid or expired.')
 g=r.json()
 if g.get('aud')!=GOOGLE_CLIENT_ID or g.get('email_verified')!='true': raise HTTPException(401,'Google account is not verified for this application.')
 email=g.get('email','').lower(); name=g.get('name') or email.split('@')[0]; sub=g.get('sub')
 with db() as c:
  u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
  if u and u['role']!='CUSTOMER': raise HTTPException(403,'Google sign-in is only enabled for customer accounts.')
  if not u:
   cur=c.execute("INSERT INTO users(full_name,email,password_hash,role,email_verified,google_sub) VALUES(?,?,?,'CUSTOMER',1,?)",(name,email,'GOOGLE:'+secrets.token_hex(32),sub)); uid=cur.lastrowid
   u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
  elif u['google_sub'] and u['google_sub']!=sub: raise HTTPException(403,'Google identity does not match this account.')
  else: c.execute('UPDATE users SET google_sub=?,email_verified=1 WHERE id=?',(sub,u['id']))
 token=issue(u['id'],u['email'],u['role'],u['full_name'],u['branch_name'])
 return {'accessToken':token,'tokenType':'Bearer','expiresIn':900,'user':{'id':u['id'],'fullName':u['full_name'],'email':u['email'],'role':u['role'],'branch':u['branch_name']}}
