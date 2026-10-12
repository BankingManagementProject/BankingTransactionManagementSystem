import os, sqlite3, secrets, hashlib, hmac, smtplib
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from shared_security import current, require

DB = os.getenv('DB_PATH', '/data/notification.db')
INTERNAL = os.getenv('INTERNAL_SECRET', 'internal-secret-change-me')
SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_FROM = os.getenv('SMTP_FROM', SMTP_USER)
SMTP_STARTTLS = os.getenv('SMTP_STARTTLS', 'true').lower() == 'true'

app = FastAPI(title='Notification and In-App Alert Service')

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

@app.on_event('startup')
def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS otp_challenges(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            purpose TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            consumed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS in_app_notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            email TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'ALERT',
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

def send_mail(to, subject, body):
    if not SMTP_HOST or not SMTP_FROM:
        print(f"\n[DEMO NOTIFICATION] Simulated email sent to {to}:\nSubject: {subject}\n{body}\n", flush=True)
        return
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM
    msg['To'] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            if SMTP_STARTTLS:
                server.starttls()
                server.ehlo()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception:
        raise HTTPException(503, 'Email delivery failed. Check SMTP settings.')

def otp_hash(email, purpose, otp):
    return hashlib.sha256((email.lower() + '|' + purpose + '|' + otp + INTERNAL).encode()).hexdigest()

def create_challenge(email, purpose, name='Customer'):
    email = email.strip().lower()
    otp = f'{secrets.randbelow(1000000):06d}'
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    with db() as c:
        c.execute('UPDATE otp_challenges SET consumed=1 WHERE email=? AND purpose=? AND consumed=0', (email, purpose))
        c.execute('INSERT INTO otp_challenges(email,purpose,otp_hash,expires_at) VALUES(?,?,?,?)', (email, purpose, otp_hash(email, purpose, otp), expires))
    subject = 'Northstar Bank email verification' if purpose == 'EMAIL_VERIFY' else 'Northstar Bank transfer authorization code'
    action = 'verify your email address' if purpose == 'EMAIL_VERIFY' else 'authorize your bank transfer'
    send_mail(email, subject, f'Hello {name},\n\nYour Northstar Bank code to {action} is {otp}. It expires in 5 minutes.\n\nNorthstar Bank educational simulator')
    # Also create an in-app notification so user can see it right in the web app
    with db() as c:
        c.execute('INSERT INTO in_app_notifications(email,title,message,category) VALUES(?,?,?,?)',
                  (email, 'Security Code Generated', f"Your one-time transfer authorization code is {otp}. Valid for 5 minutes.", 'SECURITY'))
    return {'message': 'One-time code sent to your registered email. It expires in 5 minutes.', 'demoOtp': otp}

class Issue(BaseModel): email: str; purpose: str; name: str = 'Customer'
class Verify(BaseModel): email: str; purpose: str; otp: str
class PushNotify(BaseModel): email: str; userId: int = None; title: str; message: str; category: str = 'ALERT'

@app.post('/internal/notify')
def internal_notify(b: PushNotify, request: Request):
    if request.headers.get('X-Internal-Secret') != INTERNAL:
        raise HTTPException(403, 'Internal only')
    with db() as c:
        c.execute(
            'INSERT INTO in_app_notifications(user_id,email,title,message,category) VALUES(?,?,?,?,?)',
            (b.userId, b.email.lower().strip(), b.title, b.message, b.category)
        )
    return {'status': 'SENT'}

@app.get('/api/notifications/my')
def list_my_notifications(u = Depends(current)):
    with db() as c:
        rows = c.execute(
            'SELECT * FROM in_app_notifications WHERE email=? OR user_id=? ORDER BY id DESC LIMIT 50',
            (u['email'].lower(), u['id'])
        ).fetchall()
    return [dict(r) for r in rows]

@app.post('/api/notifications/{nid}/read')
def mark_read(nid: int, u = Depends(current)):
    with db() as c:
        c.execute('UPDATE in_app_notifications SET is_read=1 WHERE id=? AND (email=? OR user_id=?)', (nid, u['email'].lower(), u['id']))
    return {'status': 'OK'}

@app.post('/api/notifications/read-all')
def mark_all_read(u = Depends(current)):
    with db() as c:
        c.execute('UPDATE in_app_notifications SET is_read=1 WHERE email=? OR user_id=?', (u['email'].lower(), u['id']))
    return {'status': 'OK'}

@app.post('/internal/email-otp')
def internal_issue(b: Issue, request: Request):
    if request.headers.get('X-Internal-Secret') != INTERNAL:
        raise HTTPException(403, 'Internal only')
    if b.purpose not in ('EMAIL_VERIFY',):
        raise HTTPException(400, 'Unsupported internal OTP purpose.')
    return create_challenge(str(b.email), b.purpose, b.name)

@app.post('/internal/verify-otp')
def internal_verify(b: Verify, request: Request):
    if request.headers.get('X-Internal-Secret') != INTERNAL:
        raise HTTPException(403, 'Internal only')
    return verify_code(str(b.email), b.purpose, b.otp)

def verify_code(email, purpose, otp):
    email = email.lower().strip()
    with db() as c:
        row = c.execute('SELECT * FROM otp_challenges WHERE email=? AND purpose=? AND consumed=0 ORDER BY id DESC LIMIT 1', (email, purpose)).fetchone()
        if not row:
            raise HTTPException(400, 'No active code. Request a new code.')
        if row['attempts'] >= 5:
            c.execute('UPDATE otp_challenges SET consumed=1 WHERE id=?', (row['id'],))
            raise HTTPException(429, 'Too many attempts. Request a new code.')
        if datetime.fromisoformat(row['expires_at']) < datetime.now(timezone.utc):
            c.execute('UPDATE otp_challenges SET consumed=1 WHERE id=?', (row['id'],))
            raise HTTPException(400, 'Code expired. Request a new code.')
        c.execute('UPDATE otp_challenges SET attempts=attempts+1 WHERE id=?', (row['id'],))
        if not hmac.compare_digest(row['otp_hash'], otp_hash(email, purpose, otp.strip())):
            raise HTTPException(400, 'Incorrect code.')
        c.execute('UPDATE otp_challenges SET consumed=1 WHERE id=?', (row['id'],))
    return {'verified': True}

@app.post('/api/notifications/transfer-otp')
def transfer_otp(u = Depends(current)):
    require(u, 'CUSTOMER', 'STAFF', 'EMPLOYEE')
    return create_challenge(u['email'], 'TRANSFER', u['name'])

@app.post('/internal/verify-transfer-otp')
def verify_transfer(b: Verify, request: Request):
    if request.headers.get('X-Internal-Secret') != INTERNAL:
        raise HTTPException(403, 'Internal only')
    if b.purpose != 'TRANSFER':
        raise HTTPException(400, 'Invalid OTP purpose.')
    return verify_code(str(b.email), b.purpose, b.otp)

@app.get('/health')
def health():
    return {'status': 'UP', 'service': 'notification-service', 'smtpConfigured': bool(SMTP_HOST and SMTP_FROM)}
