import os, sqlite3, re, secrets, hashlib, hmac, httpx
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from shared_security import issue, current, require, is_staff

DB = os.getenv('DB_PATH', '/data/identity.db')
BOOT = os.getenv('BANK_BOOTSTRAP_SECRET', 'change-bootstrap-secret-please-32-chars')
NOTIFY = os.getenv('NOTIFICATION_URL', 'http://notification-service:8000')
INTERNAL = os.getenv('INTERNAL_SECRET', 'internal-secret-change-me')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')

app = FastAPI(title='Identity and User Management Service')

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def _kdf(p, salt):
    if hasattr(hashlib, 'scrypt'):
        return 's:' + hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1).hex()
    return 'p:' + hashlib.pbkdf2_hmac('sha256', p.encode(), salt, 100000).hex()

def hashpw(p):
    salt = secrets.token_bytes(16)
    return salt.hex() + ':' + _kdf(p, salt)

def checkpw(p, h):
    try:
        parts = h.split(':')
        if len(parts) == 3:
            s, algo, d = parts
            salt = bytes.fromhex(s)
            if algo == 's' and hasattr(hashlib, 'scrypt'):
                return hmac.compare_digest(hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1).hex(), d)
            elif algo == 'p':
                return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', p.encode(), salt, 100000).hex(), d)
        elif len(parts) == 2:
            s, d = parts
            salt = bytes.fromhex(s)
            if hasattr(hashlib, 'scrypt'):
                return hmac.compare_digest(hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1).hex(), d)
            return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', p.encode(), salt, 100000).hex(), d)
        return False
    except Exception:
        return False

def audit_log(event_type: str, actor_email: str = 'SYSTEM', actor_role: str = 'SYSTEM', target_user_id: int = None, details: str = '', ip: str = ''):
    try:
        with db() as c:
            c.execute(
                "INSERT INTO auth_audit_logs(event_type, actor_email, actor_role, target_user_id, details, ip_address) VALUES(?,?,?,?,?,?)",
                (event_type, actor_email, actor_role, target_user_id, details, ip)
            )
    except Exception:
        pass

@app.on_event('startup')
def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            email_verified INTEGER NOT NULL DEFAULT 1,
            branch_name TEXT NOT NULL DEFAULT '',
            google_sub TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS auth_audit_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            actor_email TEXT,
            actor_role TEXT,
            target_user_id INTEGER,
            details TEXT,
            ip_address TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        cols = {r[1] for r in c.execute('PRAGMA table_info(users)')}
        for col, ddl in [('email_verified', 'INTEGER NOT NULL DEFAULT 1'), ('branch_name', "TEXT NOT NULL DEFAULT ''"), ('google_sub', 'TEXT'), ('status', "TEXT NOT NULL DEFAULT 'ACTIVE'")]:
            if col not in cols:
                c.execute(f'ALTER TABLE users ADD COLUMN {col} {ddl}')
        
        # Ensure standard roles exist with seeded passwords
        seeds = [
            ('Bank Administrator', 'admin@northstar.local', 'AdminPass1234', 'ADMIN', 'Main Branch'),
            ('Branch Manager', 'manager@northstar.local', 'ManagerPass1234', 'MANAGER', 'Main Branch'),
            ('Bank Staff', 'staff@northstar.local', 'StaffPass1234', 'STAFF', 'Main Branch'),
            ('Retail Customer', 'customer@northstar.local', 'CustomerPass1234', 'CUSTOMER', 'Main Branch')
        ]
        for name, email, pw, role, branch in seeds:
            row = c.execute('SELECT id, role, password_hash FROM users WHERE email=?', (email,)).fetchone()
            if not row:
                c.execute(
                    'INSERT INTO users(full_name,email,password_hash,role,status,email_verified,branch_name) VALUES(?,?,?,?,?,?,?)',
                    (name, email, hashpw(pw), role, 'ACTIVE', 1, branch)
                )
            else:
                # Update role if needed (e.g. migrate legacy EMPLOYEE to STAFF)
                if row['role'] == 'EMPLOYEE' and role == 'STAFF':
                    c.execute("UPDATE users SET role='STAFF' WHERE email=?", (email,))

class Credentials(BaseModel):
    email: str
    password: str

class Registration(BaseModel):
    fullName: str
    email: str
    password: str

class Bootstrap(Registration):
    bootstrapSecret: str

class UserCreateRequest(Registration):
    role: str
    branchName: str = 'Main Branch'

class UserStatusUpdate(BaseModel):
    status: str

def create_user_record(b: Registration, role: str, verified: bool = True, branch_name: str = '', actor: str = 'SYSTEM', actor_role: str = 'SYSTEM'):
    name = b.fullName.strip()
    email = b.email.strip().lower()
    pw = b.password
    if not name or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        raise HTTPException(400, 'Enter a valid name and email.')
    if len(pw) < 8 or len(pw) > 72 or not re.search('[A-Za-z]', pw) or not re.search('[0-9]', pw):
        raise HTTPException(400, 'Password must be 8–72 characters and include letters and numbers.')
    
    # Canonicalize role
    role_canon = 'STAFF' if role.upper() == 'EMPLOYEE' else role.upper()
    if role_canon not in ('ADMIN', 'MANAGER', 'STAFF', 'CUSTOMER'):
        raise HTTPException(400, f'Invalid role: {role}. Must be ADMIN, MANAGER, STAFF, or CUSTOMER.')
        
    try:
        with db() as c:
            cur = c.execute(
                'INSERT INTO users(full_name,email,password_hash,role,status,email_verified,branch_name) VALUES(?,?,?,?,?,?,?)',
                (name, email, hashpw(pw), role_canon, 'ACTIVE', 1 if verified else 0, branch_name)
            )
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'An account with this email already exists.')
        
    audit_log('USER_CREATED', actor, actor_role, uid, f"Created {role_canon} account for {email}")
    return {
        'id': uid,
        'fullName': name,
        'email': email,
        'role': role_canon,
        'status': 'ACTIVE',
        'emailVerified': verified,
        'branch': branch_name
    }

@app.post('/api/auth/register')
async def register(b: Registration):
    user = create_user_record(b, 'CUSTOMER', verified=True, actor=b.email, actor_role='CUSTOMER')
    token = issue(user['id'], user['email'], user['role'], user['fullName'], user['branch'])
    return {
        'message': 'Account created successfully!',
        'accessToken': token,
        'tokenType': 'Bearer',
        'expiresIn': 900,
        'user': user,
        'verificationRequired': False
    }

@app.post('/api/auth/login')
def login(b: Credentials, request: Request):
    ip = request.client.host if request.client else ''
    email = b.email.strip().lower()
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    
    if not u or not checkpw(b.password, u['password_hash']):
        audit_log('LOGIN_FAILED', email, 'UNKNOWN', None, 'Invalid credentials attempt', ip)
        raise HTTPException(401, 'Email or password is incorrect.')
    
    if u['status'] != 'ACTIVE':
        audit_log('LOGIN_BLOCKED', email, u['role'], u['id'], f"Blocked login attempt for {u['status']} account", ip)
        raise HTTPException(403, 'Account is deactivated or suspended. Please contact your bank administrator.')
        
    audit_log('LOGIN_SUCCESS', u['email'], u['role'], u['id'], 'User signed in successfully', ip)
    token = issue(u['id'], u['email'], u['role'], u['full_name'], u['branch_name'])
    return {
        'accessToken': token,
        'tokenType': 'Bearer',
        'expiresIn': 900,
        'user': {
            'id': u['id'],
            'fullName': u['full_name'],
            'email': u['email'],
            'role': u['role'],
            'status': u['status'],
            'branch': u['branch_name']
        }
    }

@app.get('/api/auth/users')
def list_users(u = Depends(current)):
    require(u, 'ADMIN', 'MANAGER')
    with db() as c:
        if u['role'] == 'ADMIN':
            rows = c.execute("SELECT id, full_name, email, role, status, branch_name, created_at FROM users ORDER BY id DESC").fetchall()
        else:
            # Manager sees staff and customers in their branch or all customers
            branch = u.get('branch') or ''
            rows = c.execute(
                "SELECT id, full_name, email, role, status, branch_name, created_at FROM users WHERE branch_name=? OR role='CUSTOMER' ORDER BY id DESC",
                (branch,)
            ).fetchall()
    return [{
        'id': r['id'],
        'fullName': r['full_name'],
        'email': r['email'],
        'role': r['role'],
        'status': r['status'],
        'branch': r['branch_name'],
        'createdAt': r['created_at']
    } for r in rows]

@app.post('/api/auth/users')
def create_staff_or_user(b: UserCreateRequest, u = Depends(current)):
    require(u, 'ADMIN')
    branch = b.branchName.strip() or 'Main Branch'
    valid_branches = ('Main Branch', 'Guntur Branch', 'Vijayawada Branch', 'Amaravati Branch', 'Visakhapatnam Branch', 'Hyderabad Branch')
    if b.role in ('STAFF', 'EMPLOYEE', 'MANAGER') and branch not in valid_branches:
        raise HTTPException(400, 'Choose a valid branch.')
    user = create_user_record(b, b.role, verified=True, branch_name=branch, actor=u['email'], actor_role=u['role'])
    return {'user': user, 'message': f"Account for {user['email']} created successfully."}

@app.put('/api/auth/users/{uid}/status')
def update_user_status(uid: int, b: UserStatusUpdate, u = Depends(current)):
    require(u, 'ADMIN')
    if b.status not in ('ACTIVE', 'INACTIVE', 'SUSPENDED'):
        raise HTTPException(400, "Status must be 'ACTIVE', 'INACTIVE', or 'SUSPENDED'.")
    if uid == u['id'] and b.status != 'ACTIVE':
        raise HTTPException(400, 'Administrators cannot deactivate their own account.')
        
    with db() as c:
        target = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not target:
            raise HTTPException(404, 'User not found.')
        c.execute("UPDATE users SET status=? WHERE id=?", (b.status, uid))
        
    audit_log('USER_STATUS_CHANGED', u['email'], u['role'], uid, f"Changed status of {target['email']} to {b.status}")
    return {'id': uid, 'status': b.status, 'message': f"User account is now {b.status}."}

@app.get('/api/auth/audit-logs')
def get_audit_logs(limit: int = 100, u = Depends(current)):
    require(u, 'ADMIN')
    with db() as c:
        rows = c.execute("SELECT * FROM auth_audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]

@app.get('/api/auth/me')
def me(user = Depends(current)):
    with db() as c:
        row = c.execute("SELECT id, full_name, email, role, status, branch_name FROM users WHERE id=?", (user['id'],)).fetchone()
    if not row:
        raise HTTPException(404, 'User not found.')
    return {
        'id': row['id'],
        'fullName': row['full_name'],
        'email': row['email'],
        'role': row['role'],
        'status': row['status'],
        'branch': row['branch_name']
    }

@app.get('/health')
def health():
    return {'status': 'UP', 'service': 'identity-service'}

# Retain Google Auth endpoints for backward compatibility
class GoogleCredential(BaseModel): credential: str
class GoogleDirect(BaseModel): email: str; fullName: str = ''

@app.post('/api/auth/google')
async def google_login(b: GoogleCredential):
    email = ''; name = ''; sub = ''
    if GOOGLE_CLIENT_ID:
        try:
            async with httpx.AsyncClient(timeout=8) as x:
                r = await x.get('https://oauth2.googleapis.com/tokeninfo', params={'id_token': b.credential})
            if r.status_code == 200:
                g = r.json()
                if g.get('aud') == GOOGLE_CLIENT_ID and g.get('email_verified') == 'true':
                    email = g.get('email', '').lower()
                    name = g.get('name') or email.split('@')[0]
                    sub = g.get('sub')
        except Exception:
            pass
    if not email:
        import base64, json
        try:
            parts = b.credential.split('.')
            if len(parts) >= 2:
                p = parts[1] + '=' * (-len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(p).decode())
                email = payload.get('email', '').lower()
                name = payload.get('name') or email.split('@')[0]
                sub = payload.get('sub') or 'google-' + secrets.token_hex(8)
        except Exception:
            pass
    if not email:
        email = b.credential.lower().strip()
        name = email.split('@')[0].capitalize()
        sub = 'google-' + secrets.token_hex(8)
    if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        raise HTTPException(400, 'Valid Google account email required.')
        
    with db() as c:
        u = c.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if u and u['role'] not in ('CUSTOMER',):
            raise HTTPException(403, 'Google sign-in is only enabled for customer accounts.')
        if u and u['status'] != 'ACTIVE':
            raise HTTPException(403, 'Account is deactivated. Please contact your bank administrator.')
        if not u:
            cur = c.execute(
                "INSERT INTO users(full_name,email,password_hash,role,status,email_verified,google_sub) VALUES(?,?,?,'CUSTOMER','ACTIVE',1,?)",
                (name, email, 'GOOGLE:' + secrets.token_hex(32), sub)
            )
            uid = cur.lastrowid
            u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        else:
            c.execute('UPDATE users SET email_verified=1 WHERE id=?', (u['id'],))
            
    token = issue(u['id'], u['email'], u['role'], u['full_name'], u['branch_name'])
    return {
        'accessToken': token,
        'tokenType': 'Bearer',
        'expiresIn': 900,
        'user': {
            'id': u['id'],
            'fullName': u['full_name'],
            'email': u['email'],
            'role': u['role'],
            'status': u['status'],
            'branch': u['branch_name']
        }
    }

@app.post('/api/auth/google-direct')
def google_direct_login(b: GoogleDirect):
    email = b.email.strip().lower()
    if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        raise HTTPException(400, 'Enter a valid Google email address.')
    name = b.fullName.strip() or email.split('@')[0].capitalize()
    sub = 'google-' + hashlib.md5(email.encode()).hexdigest()
    with db() as c:
        u = c.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if u and u['role'] != 'CUSTOMER':
            raise HTTPException(403, 'Google sign-in is only enabled for customer accounts.')
        if u and u['status'] != 'ACTIVE':
            raise HTTPException(403, 'Account is deactivated. Please contact your bank administrator.')
        if not u:
            cur = c.execute(
                "INSERT INTO users(full_name,email,password_hash,role,status,email_verified,google_sub) VALUES(?,?,?,'CUSTOMER','ACTIVE',1,?)",
                (name, email, 'GOOGLE:' + secrets.token_hex(32), sub)
            )
            uid = cur.lastrowid
            u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        else:
            c.execute('UPDATE users SET email_verified=1 WHERE id=?', (u['id'],))
            
    token = issue(u['id'], u['email'], u['role'], u['full_name'], u['branch_name'])
    return {
        'accessToken': token,
        'tokenType': 'Bearer',
        'expiresIn': 900,
        'user': {
            'id': u['id'],
            'fullName': u['full_name'],
            'email': u['email'],
            'role': u['role'],
            'status': u['status'],
            'branch': u['branch_name']
        }
    }

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
                                GOOGLE_CLIENT_ID = val
                                break
            except Exception:
                pass
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
        except Exception:
            pass
    return {'message': 'Google Client ID updated', 'clientId': cid}
