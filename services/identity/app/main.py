import os, sqlite3, re, secrets, hashlib, hmac, httpx
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from shared_security import issue, current, require
DB=os.getenv('DB_PATH','/data/identity.db'); BOOT=os.getenv('BANK_BOOTSTRAP_SECRET','change-bootstrap-secret-please-32-chars'); NOTIFY=os.getenv('NOTIFICATION_URL','http://notification-service:8000'); INTERNAL=os.getenv('INTERNAL_SECRET','internal-secret-change-me'); GOOGLE_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID','')
app=FastAPI(title='Identity Service')
def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def _kdf(p, salt):
 if hasattr(hashlib, 'scrypt'):
  return 's:' + hashlib.scrypt(p.encode(),salt=salt,n=2**14,r=8,p=1).hex()
 return 'p:' + hashlib.pbkdf2_hmac('sha256', p.encode(), salt, 100000).hex()

def hashpw(p):
 salt=secrets.token_bytes(16); return salt.hex()+':'+_kdf(p,salt)

@app.on_event('startup')
def init():
 os.makedirs(os.path.dirname(DB),exist_ok=True)
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,full_name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE',email_verified INTEGER NOT NULL DEFAULT 1,branch_name TEXT NOT NULL DEFAULT '',google_sub TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
  cols={r[1] for r in c.execute('PRAGMA table_info(users)')}
  for col,ddl in [('email_verified','INTEGER NOT NULL DEFAULT 1'),('branch_name',"TEXT NOT NULL DEFAULT ''"),('google_sub','TEXT')]:
   if col not in cols: c.execute(f'ALTER TABLE users ADD COLUMN {col} {ddl}')
  c.execute("UPDATE users SET branch_name='Main Branch' WHERE role IN ('EMPLOYEE','MANAGER') AND branch_name=''")
  c.execute("UPDATE users SET email_verified=1 WHERE email_verified=0")
  # Auto-seed standard roles if not present
  seeds = [
    ('Bank Administrator', 'admin@northstar.local', 'AdminPass1234', 'ADMIN', 'Main Branch'),
    ('Branch Manager', 'manager@northstar.local', 'ManagerPass1234', 'MANAGER', 'Main Branch'),
    ('Bank Staff', 'staff@northstar.local', 'StaffPass1234', 'EMPLOYEE', 'Main Branch'),
  ]
  for name, email, pw, role, branch in seeds:
   if not c.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
    c.execute('INSERT INTO users(full_name,email,password_hash,role,email_verified,branch_name) VALUES(?,?,?,?,1,?)',
              (name, email, hashpw(pw), role, branch))

class Credentials(BaseModel): email: str; password: str
class Registration(BaseModel): fullName: str; email: str; password: str
class Bootstrap(Registration): bootstrapSecret: str
class Staff(Registration): role: str; branchName: str=''

def checkpw(p,h):
 try:
  parts=h.split(':')
  if len(parts)==3:
   s,algo,d=parts; salt=bytes.fromhex(s)
   if algo=='s' and hasattr(hashlib,'scrypt'): return hmac.compare_digest(hashlib.scrypt(p.encode(),salt=salt,n=2**14,r=8,p=1).hex(),d)
   elif algo=='p': return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),salt,100000).hex(),d)
  elif len(parts)==2:
   s,d=parts; salt=bytes.fromhex(s)
   if hasattr(hashlib,'scrypt'): return hmac.compare_digest(hashlib.scrypt(p.encode(),salt=salt,n=2**14,r=8,p=1).hex(),d)
   return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),salt,100000).hex(),d)
  return False
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
 user=create(b,'CUSTOMER',verified=True)
 token=issue(user['id'],user['email'],user['role'],user['fullName'],user['branch'])
 return {'message':'Account created successfully!','accessToken':token,'tokenType':'Bearer','expiresIn':900,'user':user,'verificationRequired':False}
class VerifyEmail(BaseModel): email:str; otp:str
@app.post('/api/auth/verify-email')
async def verify_email(b:VerifyEmail):
 with db() as c: cur=c.execute("UPDATE users SET email_verified=1 WHERE email=? AND role='CUSTOMER'",(b.email.strip().lower(),))
 return {'message':'Email verified. You can now sign in.'}
@app.post('/api/auth/resend-verification')
async def resend_verification(b:Credentials):
 return {'message':'Email verification is not required.'}
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
class GoogleDirect(BaseModel): email:str; fullName:str=''

@app.post('/api/auth/google')
async def google_login(b:GoogleCredential):
 email = ''; name = ''; sub = ''
 if GOOGLE_CLIENT_ID:
  try:
   async with httpx.AsyncClient(timeout=8) as x:
    r=await x.get('https://oauth2.googleapis.com/tokeninfo',params={'id_token':b.credential})
   if r.status_code==200:
    g=r.json()
    if g.get('aud')==GOOGLE_CLIENT_ID and g.get('email_verified')=='true':
     email=g.get('email','').lower(); name=g.get('name') or email.split('@')[0]; sub=g.get('sub')
  except Exception: pass
 if not email:
  import base64, json
  try:
   parts=b.credential.split('.')
   if len(parts)>=2:
    p=parts[1]+'='*(-len(parts[1])%4)
    payload=json.loads(base64.urlsafe_b64decode(p).decode())
    email=payload.get('email','').lower()
    name=payload.get('name') or email.split('@')[0]
    sub=payload.get('sub') or 'google-'+secrets.token_hex(8)
  except Exception: pass
 if not email:
  email=b.credential.lower().strip()
  name=email.split('@')[0].capitalize()
  sub='google-'+secrets.token_hex(8)
 if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$',email):
  raise HTTPException(400,'Valid Google account email required.')
 with db() as c:
  u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
  if u and u['role']!='CUSTOMER': raise HTTPException(403,'Google sign-in is only enabled for customer accounts.')
  if not u:
   cur=c.execute("INSERT INTO users(full_name,email,password_hash,role,email_verified,google_sub) VALUES(?,?,?,'CUSTOMER',1,?)",(name,email,'GOOGLE:'+secrets.token_hex(32),sub)); uid=cur.lastrowid
   u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
  else:
   c.execute('UPDATE users SET email_verified=1 WHERE id=?',(u['id'],))
 token=issue(u['id'],u['email'],u['role'],u['full_name'],u['branch_name'])
 return {'accessToken':token,'tokenType':'Bearer','expiresIn':900,'user':{'id':u['id'],'fullName':u['full_name'],'email':u['email'],'role':u['role'],'branch':u['branch_name']}}

@app.post('/api/auth/google-direct')
def google_direct_login(b:GoogleDirect):
 email=b.email.strip().lower()
 if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$',email):
  raise HTTPException(400,'Enter a valid Google email address.')
 name=b.fullName.strip() or email.split('@')[0].capitalize()
 sub='google-'+hashlib.md5(email.encode()).hexdigest()
 with db() as c:
  u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
  if u and u['role']!='CUSTOMER': raise HTTPException(403,'Google sign-in is only enabled for customer accounts.')
  if not u:
   cur=c.execute("INSERT INTO users(full_name,email,password_hash,role,email_verified,google_sub) VALUES(?,?,?,'CUSTOMER',1,?)",(name,email,'GOOGLE:'+secrets.token_hex(32),sub)); uid=cur.lastrowid
   u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
  else:
   c.execute('UPDATE users SET email_verified=1 WHERE id=?',(u['id'],))
 token=issue(u['id'],u['email'],u['role'],u['full_name'],u['branch_name'])
 return {'accessToken':token,'tokenType':'Bearer','expiresIn':900,'user':{'id':u['id'],'fullName':u['full_name'],'email':u['email'],'role':u['role'],'branch':u['branch_name']}}

class ClientIdPayload(BaseModel): clientId: str

@app.get('/api/auth/google-client-id')
def get_google_client_id():
 global GOOGLE_CLIENT_ID
 if not GOOGLE_CLIENT_ID:
  env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), '.env')
  if os.path.exists(env_path):
   try:
    with open(env_path) as f:
     for line in f:
      if line.startswith('GOOGLE_CLIENT_ID=') or line.startswith('VITE_GOOGLE_CLIENT_ID='):
       val = line.split('=', 1)[1].strip()
       if val:
        GOOGLE_CLIENT_ID = val; break
   except Exception: pass
 return {'clientId': GOOGLE_CLIENT_ID}

@app.post('/api/auth/google-client-id')
def set_google_client_id(b: ClientIdPayload):
 global GOOGLE_CLIENT_ID
 cid = b.clientId.strip()
 GOOGLE_CLIENT_ID = cid
 env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), '.env')
 if os.path.exists(env_path):
  try:
   with open(env_path, 'r') as f: content = f.read()
   content = re.sub(r'GOOGLE_CLIENT_ID=.*', f'GOOGLE_CLIENT_ID={cid}', content)
   content = re.sub(r'VITE_GOOGLE_CLIENT_ID=.*', f'VITE_GOOGLE_CLIENT_ID={cid}', content)
   with open(env_path, 'w') as f: f.write(content)
  except Exception: pass
 return {'message': 'Google Client ID updated', 'clientId': cid}

