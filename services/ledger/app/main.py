import os,sqlite3,uuid
from fastapi import FastAPI,HTTPException,Request
from pydantic import BaseModel
DB=os.getenv('DB_PATH','/data/ledger.db'); INTERNAL=os.getenv('INTERNAL_SECRET','internal-secret-change-me')
app=FastAPI(title='Ledger Service')
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def guard(req):
 if req.headers.get('X-Internal-Secret')!=INTERNAL: raise HTTPException(403,'Internal service credentials required.')
@app.on_event('startup')
def init():
 os.makedirs(os.path.dirname(DB),exist_ok=True)
 with db() as c: c.executescript('''CREATE TABLE IF NOT EXISTS ledger_accounts(account_number TEXT PRIMARY KEY,owner_user_id INTEGER,available_balance REAL NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS ledger_entries(id INTEGER PRIMARY KEY AUTOINCREMENT,reference TEXT UNIQUE NOT NULL,account_number TEXT NOT NULL,amount REAL NOT NULL,entry_type TEXT NOT NULL,description TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
class NewAccount(BaseModel): accountNumber:str; ownerUserId:int; openingBalance:float=0
class Posting(BaseModel): accountNumber:str; amount:float; kind:str; reference:str; description:str=''
@app.get('/health')
def health(): return {'status':'UP','service':'ledger-service'}
@app.post('/internal/accounts')
def create_account(b:NewAccount,request:Request):
 guard(request)
 if b.openingBalance<0: raise HTTPException(400,'Opening balance cannot be negative.')
 with db() as c:
  c.execute('INSERT OR IGNORE INTO ledger_accounts(account_number,owner_user_id,available_balance) VALUES(?,?,0)',(b.accountNumber,b.ownerUserId))
  if b.openingBalance>0:
   ref='OPEN-'+b.accountNumber
   if not c.execute('SELECT 1 FROM ledger_entries WHERE reference=?',(ref,)).fetchone():
    c.execute('UPDATE ledger_accounts SET available_balance=available_balance+? WHERE account_number=?',(b.openingBalance,b.accountNumber)); c.execute("INSERT INTO ledger_entries(reference,account_number,amount,entry_type,description) VALUES(?,?,?,'OPENING_CREDIT','Approved account opening balance')",(ref,b.accountNumber,b.openingBalance))
 return {'accountNumber':b.accountNumber,'status':'CREATED'}
@app.get('/internal/balances/{number}')
def balance(number:str,request:Request):
 guard(request)
 with db() as c: a=c.execute('SELECT * FROM ledger_accounts WHERE account_number=?',(number,)).fetchone()
 if not a: raise HTTPException(404,'Ledger account not found.')
 return {'accountNumber':number,'balance':a['available_balance']}
@app.post('/internal/postings')
def posting(b:Posting,request:Request):
 guard(request)
 if b.amount<=0: raise HTTPException(400,'Posting amount must be positive.')
 if b.kind not in ('DEPOSIT','DEBIT','CREDIT','COMPENSATION_CREDIT'): raise HTTPException(400,'Unsupported posting type.')
 with db() as c:
  old=c.execute('SELECT * FROM ledger_entries WHERE reference=?',(b.reference,)).fetchone()
  if old:
   # Idempotency keys may be retried, but must never be reused for a different posting.
   expected_amount=(-b.amount if b.kind=='DEBIT' else b.amount)
   if old['account_number']!=b.accountNumber or old['entry_type']!=b.kind or abs(float(old['amount'])-expected_amount)>0.000001:
    raise HTTPException(409,'Idempotency reference was already used for a different ledger posting.')
   return {'status':'ALREADY_POSTED','reference':b.reference}
  a=c.execute('SELECT * FROM ledger_accounts WHERE account_number=?',(b.accountNumber,)).fetchone()
  if not a: raise HTTPException(404,'Ledger account not found.')
  if b.kind=='DEBIT':
   if a['available_balance']-b.amount < 0: raise HTTPException(409,'Insufficient ledger balance.')
   c.execute('UPDATE ledger_accounts SET available_balance=available_balance-? WHERE account_number=?',(b.amount,b.accountNumber))
  else: c.execute('UPDATE ledger_accounts SET available_balance=available_balance+? WHERE account_number=?',(b.amount,b.accountNumber))
  c.execute('INSERT INTO ledger_entries(reference,account_number,amount,entry_type,description) VALUES(?,?,?,?,?)',(b.reference,b.accountNumber,(-b.amount if b.kind=='DEBIT' else b.amount),b.kind,b.description))
  return {'status':'POSTED','reference':b.reference,'balance':c.execute('SELECT available_balance FROM ledger_accounts WHERE account_number=?',(b.accountNumber,)).fetchone()[0]}
@app.get('/internal/entries/{number}')
def entries(number:str,request:Request):
 guard(request)
 with db() as c: return [dict(x) for x in c.execute('SELECT * FROM ledger_entries WHERE account_number=? ORDER BY id',(number,)).fetchall()]

@app.get('/internal/entry-by-reference/{reference}')
def entry_by_reference(reference:str,request:Request):
 guard(request)
 with db() as c: row=c.execute('SELECT * FROM ledger_entries WHERE reference=?',(reference,)).fetchone()
 return dict(row) if row else {'found':False,'reference':reference}
