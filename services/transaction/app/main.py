import os,sqlite3,secrets,json,time,asyncio
from datetime import datetime,timezone,timedelta
import httpx
from fastapi import FastAPI,HTTPException,Depends,Request
from pydantic import BaseModel
from shared_security import current,require,is_staff
DB=os.getenv('DB_PATH','/data/transaction.db'); ACCOUNT=os.getenv('ACCOUNT_URL','http://account-service:8000'); LEDGER=os.getenv('LEDGER_URL','http://ledger-service:8000'); INTERNAL=os.getenv('INTERNAL_SECRET','internal-secret-change-me'); RABBIT=os.getenv('RABBITMQ_HOST','rabbitmq'); NOTIFICATION=os.getenv('NOTIFICATION_URL','http://notification-service:8000')
app=FastAPI(title='Transaction and Saga Orchestrator Service')
_recovery_task=None
_RECOVERY_STALE_SECONDS=int(os.getenv('SAGA_RECOVERY_STALE_SECONDS','120'))
_RECOVERY_INTERVAL_SECONDS=int(os.getenv('SAGA_RECOVERY_INTERVAL_SECONDS','30'))
# This educational deployment runs one orchestrator replica. Serialize transfers so
# balance/daily-limit validation cannot race between requests in this process.
_transfer_lock=asyncio.Lock()
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
@app.on_event('startup')
def init():
 os.makedirs(os.path.dirname(DB),exist_ok=True)
 with db() as c: c.executescript('''CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,reference_no TEXT UNIQUE,txn_type TEXT,customer_user_id INTEGER,customer_name TEXT,source_account_id INTEGER,destination_account_id INTEGER,amount REAL,status TEXT,description TEXT,failure_mode TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS transaction_events(id INTEGER PRIMARY KEY AUTOINCREMENT,transaction_id INTEGER,status TEXT,title TEXT,details TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')

async def _recover_stale_sagas_once():
 """Recover stale debit-in-flight Sagas using deterministic, idempotent ledger references.
 Never claim compensation unless the ledger confirms the compensation posting.
 If a destination credit already exists but final state was not persisted, escalate for
 reconciliation instead of blindly refunding and risking a double-credit.
 """
 cutoff=(datetime.now(timezone.utc)-timedelta(seconds=_RECOVERY_STALE_SECONDS)).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
 with db() as c:
  rows=c.execute("SELECT * FROM transactions WHERE txn_type='TRANSFER' AND status IN ('DEBIT_CONFIRMED','CREDITING','CREDIT_FAILED','COMPENSATING') AND updated_at < ? ORDER BY id LIMIT 100",(cutoff,)).fetchall()
 for row in rows:
  t=dict(row); tid=t['id']; ref=t['reference_no']
  try:
   src=await get(f"{ACCOUNT}/internal/accounts/{t['source_account_id']}")
   credit=await get(f"{LEDGER}/internal/entry-by-reference/{ref}-CREDIT")
   if credit.get('found'):
    stage(tid,'REQUIRES_REVIEW','Recovery requires reconciliation','A destination-credit ledger entry exists, but the Saga completion state was not safely confirmed. No automatic refund was issued to avoid double-crediting. Staff must reconcile both ledger accounts.')
    continue
   stage(tid,'COMPENSATING','Stale Saga recovery started','Recovery worker found a stale transfer after source debit and confirmed no destination-credit entry exists. Attempting idempotent source restoration.')
   await post(f"{LEDGER}/internal/postings",{'accountNumber':src['account_number'],'amount':t['amount'],'kind':'COMPENSATION_CREDIT','reference':f'{ref}-COMPENSATION','description':f'Automated stale-Saga recovery for {ref}'})
   stage(tid,'COMPENSATED','Stale Saga recovered','Ledger confirmed the idempotent compensation posting. Destination credit was not present when recovery checked.')
  except Exception as exc:
   try: stage(tid,'REQUIRES_REVIEW','Automatic recovery needs staff review',f'Recovery could not prove a safe automatic outcome ({type(exc).__name__}). No success or compensation was claimed. Staff investigation is required.')
   except Exception: pass

async def _recovery_loop():
 while True:
  await asyncio.sleep(_RECOVERY_INTERVAL_SECONDS)
  try: await _recover_stale_sagas_once()
  except Exception: pass

@app.on_event('startup')
async def start_recovery_worker():
 global _recovery_task
 _recovery_task=asyncio.create_task(_recovery_loop())

@app.on_event('shutdown')
async def stop_recovery_worker():
 global _recovery_task
 if _recovery_task:
  _recovery_task.cancel()
  try: await _recovery_task
  except asyncio.CancelledError: pass
async def get(url):
 async with httpx.AsyncClient(timeout=8) as x:
  r=await x.get(url,headers={'X-Internal-Secret':INTERNAL})
  if r.status_code>=400: raise HTTPException(r.status_code,r.json().get('detail','Service request failed'))
  return r.json()
async def post(url,payload):
 async with httpx.AsyncClient(timeout=8) as x:
  r=await x.post(url,json=payload,headers={'X-Internal-Secret':INTERNAL})
  if r.status_code>=400: raise HTTPException(r.status_code,r.json().get('detail','Service request failed'))
  return r.json()
def publish(txid,status):
 try:
  import pika
  creds=pika.PlainCredentials(os.getenv('RABBITMQ_USER','northstar'),os.getenv('RABBITMQ_PASSWORD','replace-with-a-strong-rabbitmq-password'))
  conn=pika.BlockingConnection(pika.ConnectionParameters(host=RABBIT,credentials=creds,connection_attempts=1, socket_timeout=1)); ch=conn.channel(); ch.exchange_declare(exchange='northstar.events',exchange_type='fanout',durable=True); ch.basic_publish(exchange='northstar.events',routing_key='',body=json.dumps({'transactionId':txid,'status':status,'occurredAt':datetime.now(timezone.utc).isoformat()}),properties=pika.BasicProperties(delivery_mode=2,content_type='application/json')); conn.close()
 except Exception: pass
def stage(tid,status,title,details):
 with db() as c:
  c.execute('UPDATE transactions SET status=?,description=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,details,tid)); c.execute('INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,?,?,?)',(tid,status,title,details))
 publish(tid,status)
def gettxn(tid):
 with db() as c: t=c.execute('SELECT * FROM transactions WHERE id=?',(tid,)).fetchone()
 if not t: raise HTTPException(404,'Transaction not found.')
 return dict(t)
def access(t,u):
 if not is_staff(u) and t['customer_user_id']!=u['id']: raise HTTPException(404,'Transaction not found.')
 if u.get('role') in ('MANAGER','EMPLOYEE') and u.get('branch'):
  # Route handlers additionally verify branch through Account Service where needed.
  if t.get('source_account_id') is None and t.get('destination_account_id') is None: raise HTTPException(404,'Transaction not found.')
class Transfer(BaseModel): sourceAccountId:int; destinationAccountNumber:str; amount:float; otp:str=''
class TestTransfer(Transfer): outcome:str='SUCCESS'
async def _run_transfer_serialized(b,u,test=False):
 if b.amount<=0 or b.amount>100000: raise HTTPException(400,'Transfer amount must be greater than zero and no more than ₹1,00,000.')
 if test: require(u,'ADMIN')
 else:
  require(u,'CUSTOMER')
  if not b.otp or len(b.otp.strip())!=6: raise HTTPException(400,'Email OTP is required before a transfer.')
  async with httpx.AsyncClient(timeout=8) as client:
   vr=await client.post(NOTIFICATION+'/internal/verify-transfer-otp',json={'email':u['email'],'purpose':'TRANSFER','otp':b.otp.strip()},headers={'X-Internal-Secret':INTERNAL})
  if vr.status_code>=400: raise HTTPException(vr.status_code,vr.json().get('detail','Email OTP verification failed.'))
 src=await get(f'{ACCOUNT}/internal/accounts/{b.sourceAccountId}')
 if not test and src['owner_user_id']!=u['id']: raise HTTPException(404,'Source account not found.')
 reference='TRF-'+secrets.token_hex(5).upper()
 with db() as c:
  cur=c.execute("INSERT INTO transactions(reference_no,txn_type,customer_user_id,customer_name,source_account_id,amount,status,description,failure_mode) VALUES(?,?,?,?,?,?,'PENDING','Transfer request received',?)",(reference,'TRANSFER',u['id'],u['name'],b.sourceAccountId,b.amount,b.outcome if test else 'NONE')); tid=cur.lastrowid
  c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'PENDING','Transfer request received','Request recorded. No account balance has changed yet.')",(tid,))
 stage(tid,'VALIDATING','Validation started','Checking destination, account state, available funds, minimum balance and daily limit.')
 try: dest=await get(f"{ACCOUNT}/internal/account-number/{b.destinationAccountNumber.strip()}")
 except HTTPException:
  stage(tid,'VALIDATION_FAILED','Destination account not found',f"Recipient account '{b.destinationAccountNumber}' does not exist. Workflow stopped at validation; no funds were moved.")
  return gettxn(tid)
 if src['account_number']==dest['account_number']:
  stage(tid,'VALIDATION_FAILED','Invalid destination','Source and destination accounts must differ. No funds were moved.'); return gettxn(tid)
 if src['status']!='ACTIVE' or dest['status']!='ACTIVE':
  stage(tid,'VALIDATION_FAILED','Account is not active','Both accounts must be active. No funds were moved.'); return gettxn(tid)
 srcbal=(await get(f"{LEDGER}/internal/balances/{src['account_number']}"))['balance']
 with db() as c: spent=c.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE source_account_id=? AND txn_type='TRANSFER' AND status IN ('DEBIT_CONFIRMED','CREDITING','CREDIT_FAILED','COMPENSATING','SUCCESS','REQUIRES_REVIEW') AND date(created_at,'+5 hours','+30 minutes')=date('now','+5 hours','+30 minutes')",(b.sourceAccountId,)).fetchone()[0]
 if srcbal-b.amount < float(src['minimum_balance']):
  stage(tid,'VALIDATION_FAILED','Minimum balance or available funds check failed','Transfer would breach the savings minimum balance or available funds. No funds were moved.'); return gettxn(tid)
 if spent+b.amount>float(src['daily_limit']):
  stage(tid,'VALIDATION_FAILED','Daily limit exceeded','Transfer would exceed the daily outgoing limit. No funds were moved.'); return gettxn(tid)
 stage(tid,'VALIDATED','Validation passed','Destination exists; both accounts are active; balance, minimum-balance and daily-limit checks passed.')
 debit_ref=f'{reference}-DEBIT'
 try: await post(f'{LEDGER}/internal/postings',{'accountNumber':src['account_number'],'amount':b.amount,'kind':'DEBIT','reference':debit_ref,'description':f'Transfer {reference} source debit'})
 except HTTPException as e:
  stage(tid,'FAILED','Source debit failed',str(e.detail)); return gettxn(tid)
 stage(tid,'DEBIT_CONFIRMED','Source debit confirmed','Ledger service confirmed the source debit.')
 stage(tid,'CREDITING','Destination credit started','Attempting the destination ledger posting.')
 credit_ok=False
 if not (test and b.outcome in ('FAIL_CREDIT_COMPENSATE','FAIL_CREDIT_REVIEW')):
  try: await post(f'{LEDGER}/internal/postings',{'accountNumber':dest['account_number'],'amount':b.amount,'kind':'CREDIT','reference':f'{reference}-CREDIT','description':f'Transfer {reference} destination credit'}); credit_ok=True
  except HTTPException: credit_ok=False
 if credit_ok:
  stage(tid,'CREDIT_CONFIRMED','Destination credit confirmed','Ledger service confirmed destination credit.')
  stage(tid,'SUCCESS','Transfer completed','Source debit and destination credit are both confirmed.');
  with db() as c: c.execute('UPDATE transactions SET destination_account_id=? WHERE id=?',(dest['id'],tid))
  return gettxn(tid)
 stage(tid,'CREDIT_FAILED','Destination credit failed','Destination credit was not confirmed after source debit. Compensation is required.')
 stage(tid,'COMPENSATING','Compensation started','Saga is attempting to restore source funds with a uniquely identified compensating posting.')
 if test and b.outcome=='FAIL_CREDIT_REVIEW':
  stage(tid,'REQUIRES_REVIEW','Automatic compensation not confirmed','Controlled test scenario: source debit remains unresolved. Employee investigation is required; funds are not reported as returned.')
  with db() as c: c.execute('UPDATE transactions SET destination_account_id=? WHERE id=?',(dest['id'],tid))
  return gettxn(tid)
 try:
  await post(f'{LEDGER}/internal/postings',{'accountNumber':src['account_number'],'amount':b.amount,'kind':'COMPENSATION_CREDIT','reference':f'{reference}-COMPENSATION','description':f'Compensation for failed transfer {reference}'})
  stage(tid,'COMPENSATED','Compensation confirmed','Source funds restored by a separate compensating ledger posting. Destination was not credited.')
 except HTTPException:
  stage(tid,'REQUIRES_REVIEW','Compensation failed','Source funds could not be restored automatically. Staff investigation is required.')
 with db() as c: c.execute('UPDATE transactions SET destination_account_id=? WHERE id=?',(dest['id'],tid))
 return gettxn(tid)
async def run_transfer(b,u,test=False):
 # A single orchestrator replica is configured in compose; lock serializes all
 # transfers so two concurrent requests cannot both pass the daily-limit check.
 async with _transfer_lock:
  return await _run_transfer_serialized(b,u,test)

@app.get('/api/health')
def health(): return {'status':'UP','service':'transaction-saga-service'}
@app.post('/api/transfers')
async def transfer(b:Transfer,u=Depends(current)): return await run_transfer(b,u,False)
@app.post('/api/admin/saga-test-transfers')
async def test_transfer(b:TestTransfer,u=Depends(current)): return await run_transfer(b,u,True)
@app.get('/api/transactions')
async def transactions(u=Depends(current)):
 with db() as c: rows=[dict(r) for r in c.execute('SELECT * FROM transactions ORDER BY id DESC' if is_staff(u) else 'SELECT * FROM transactions WHERE customer_user_id=? ORDER BY id DESC',() if is_staff(u) else (u['id'],)).fetchall()]
 if u.get('role') in ('MANAGER','EMPLOYEE') and u.get('branch'):
  scoped=[]
  for t in rows:
   aid=t.get('source_account_id') or t.get('destination_account_id')
   try: a=await get(f"{ACCOUNT}/internal/accounts/{aid}");
   except Exception: continue
   if a.get('branch_name')==u['branch']: scoped.append(t)
  return scoped
 return rows
async def ensure_branch_scope(t,u):
 if u.get('role') in ('MANAGER','EMPLOYEE'):
  aid=t.get('source_account_id') or t.get('destination_account_id')
  if not aid: raise HTTPException(404,'Transaction not found.')
  a=await get(f"{ACCOUNT}/internal/accounts/{aid}")
  if a.get('branch_name')!=(u.get('branch') or ''): raise HTTPException(404,'Transaction not found in your branch.')
@app.get('/api/transactions/{tid}/events')
async def events(tid:int,u=Depends(current)):
 t=gettxn(tid); access(t,u); await ensure_branch_scope(t,u)
 with db() as c: return [dict(r) for r in c.execute('SELECT * FROM transaction_events WHERE transaction_id=? ORDER BY id',(tid,)).fetchall()]
@app.post('/api/transactions/{tid}/resolve-review')
async def resolve(tid:int,u=Depends(current)):
 require(u,'EMPLOYEE','MANAGER','ADMIN'); t=gettxn(tid); await ensure_branch_scope(t,u)
 if t['status']!='REQUIRES_REVIEW': raise HTTPException(409,'Transaction does not require review.')
 src=await get(f"{ACCOUNT}/internal/accounts/{t['source_account_id']}")
 await post(f"{LEDGER}/internal/postings",{'accountNumber':src['account_number'],'amount':t['amount'],'kind':'COMPENSATION_CREDIT','reference':f"{t['reference_no']}-MANUAL-RECOVERY",'description':f"Authorized recovery for {t['reference_no']}"})
 stage(tid,'COMPENSATED','Manual recovery confirmed',f"{u['email']} confirmed the source-fund restoration. Recovery ledger reference recorded.")
 return gettxn(tid)
@app.get('/internal/health')
def internal_health(): return {'status':'UP'}
class DepositEvent(BaseModel): reference:str; customerUserId:int; customerName:str; accountId:int; accountNumber:str; amount:float
class DepositDecision(BaseModel): status:str; actor:str; details:str
@app.post('/internal/deposits')
def internal_create_deposit(b:DepositEvent,request:Request):
 if request.headers.get('X-Internal-Secret')!=INTERNAL: raise HTTPException(403,'Internal only')
 with db() as c:
  old=c.execute('SELECT id FROM transactions WHERE reference_no=?',(b.reference,)).fetchone()
  if old: return {'id':old['id']}
  cur=c.execute("INSERT INTO transactions(reference_no,txn_type,customer_user_id,customer_name,destination_account_id,amount,status,description) VALUES(?,'DEPOSIT',?,?,?,?,'PENDING_APPROVAL','Deposit request submitted; awaiting employee approval')",(b.reference,b.customerUserId,b.customerName,b.accountId,b.amount)); tid=cur.lastrowid
  c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'PENDING_APPROVAL','Deposit submitted','No balance changes until an employee approves this request.')",(tid,))
 publish(tid,'PENDING_APPROVAL'); return {'id':tid}
@app.post('/internal/deposits/{tid}/decision')
def internal_deposit_decision(tid:int,b:DepositDecision,request:Request):
 if request.headers.get('X-Internal-Secret')!=INTERNAL: raise HTTPException(403,'Internal only')
 if b.status not in ('SUCCESS','REJECTED'): raise HTTPException(400,'Invalid deposit decision.')
 t=gettxn(tid)
 stage(tid,b.status,'Deposit '+('approved and credited' if b.status=='SUCCESS' else 'rejected'),b.details)
 return {'id':tid,'status':b.status}

@app.get('/internal/summary')
async def internal_summary(request:Request,userId:int,staff:bool=False,branch:str=''):
 if request.headers.get('X-Internal-Secret')!=INTERNAL: raise HTTPException(403,'Internal only')
 with db() as c:
  if not staff: rows=[dict(x) for x in c.execute('SELECT * FROM transactions WHERE customer_user_id=?',(userId,)).fetchall()]
  else: rows=[dict(x) for x in c.execute('SELECT * FROM transactions').fetchall()]
 if staff and branch:
  scoped=[]
  for t in rows:
   aid=t.get('source_account_id') or t.get('destination_account_id')
   if not aid: continue
   try: a=await get(f"{ACCOUNT}/internal/accounts/{aid}")
   except Exception: continue
   if a.get('branch_name')==branch: scoped.append(t)
  rows=scoped
 return {'transactions':len(rows),'reviewRequired':sum(1 for t in rows if t.get('status')=='REQUIRES_REVIEW')}

class OpeningDeposit(BaseModel): reference:str; customerUserId:int; customerName:str; accountId:int; accountNumber:str; amount:float
@app.post('/internal/opening-deposit')
def opening_deposit(b:OpeningDeposit,request:Request):
 if request.headers.get('X-Internal-Secret')!=INTERNAL: raise HTTPException(403,'Internal only')
 with db() as c:
  old=c.execute('SELECT id FROM transactions WHERE reference_no=?',(b.reference,)).fetchone()
  if old: return {'id':old['id']}
  cur=c.execute("INSERT INTO transactions(reference_no,txn_type,customer_user_id,customer_name,destination_account_id,amount,status,description) VALUES(?,'ACCOUNT_OPENING_DEPOSIT',?,?,?,?,'SUCCESS','Initial deposit posted when approved account was activated')",(b.reference,b.customerUserId,b.customerName,b.accountId,b.amount)); tid=cur.lastrowid
  c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'APPROVED','Account application approved','Manager approval recorded and account activated.')",(tid,))
  c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'OPENING_CREDIT_POSTED','Initial deposit posted',?)",(tid,f"₹{b.amount:.2f} initial balance posted to ledger account {b.accountNumber}."))
  c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'SUCCESS','Account activated','Opening balance and account activation confirmed.')",(tid,))
 publish(tid,'SUCCESS'); return {'id':tid,'status':'SUCCESS'}
