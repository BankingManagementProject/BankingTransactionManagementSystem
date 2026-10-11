import os,sqlite3,httpx,secrets,datetime
from fastapi import FastAPI,HTTPException,Depends,Request
from pydantic import BaseModel
from shared_security import current,require,is_staff
DB=os.getenv('DB_PATH','/data/account.db'); LEDGER=os.getenv('LEDGER_URL','http://ledger-service:8000'); INTERNAL=os.getenv('INTERNAL_SECRET','internal-secret-change-me'); TRANSACTION=os.getenv('TRANSACTION_URL','http://transaction-service:8000')
app=FastAPI(title='Account and Approval Service')
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
@app.on_event('startup')
def init():
 os.makedirs(os.path.dirname(DB),exist_ok=True)
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY AUTOINCREMENT,customer_user_id INTEGER,customer_name TEXT,customer_phone TEXT NOT NULL DEFAULT '',date_of_birth TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',occupation TEXT NOT NULL DEFAULT '',account_type TEXT,initial_deposit REAL,reason TEXT,status TEXT DEFAULT 'PENDING_REVIEW',account_id INTEGER,branch_name TEXT NOT NULL DEFAULT 'Main Branch',created_at TEXT DEFAULT CURRENT_TIMESTAMP,reviewed_by TEXT); CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_user_id INTEGER,customer_name TEXT,account_type TEXT,account_number TEXT UNIQUE,balance REAL DEFAULT 0,minimum_balance REAL DEFAULT 1000,daily_limit REAL DEFAULT 25000,status TEXT DEFAULT 'ACTIVE',branch_name TEXT NOT NULL DEFAULT 'Main Branch',created_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY AUTOINCREMENT,reference_no TEXT UNIQUE,customer_user_id INTEGER,customer_name TEXT,account_id INTEGER,amount REAL,status TEXT DEFAULT 'PENDING_APPROVAL',description TEXT,branch_name TEXT NOT NULL DEFAULT 'Main Branch',created_at TEXT DEFAULT CURRENT_TIMESTAMP,reviewed_by TEXT); CREATE TABLE IF NOT EXISTS fixed_deposits(id INTEGER PRIMARY KEY AUTOINCREMENT,reference_no TEXT UNIQUE,customer_user_id INTEGER,account_id INTEGER,account_number TEXT,principal REAL,tenure_months INTEGER,annual_rate REAL DEFAULT 6.5,maturity_date TEXT,status TEXT DEFAULT 'ACTIVE',created_at TEXT DEFAULT CURRENT_TIMESTAMP,closed_at TEXT); CREATE TABLE IF NOT EXISTS loan_applications(id INTEGER PRIMARY KEY AUTOINCREMENT,customer_user_id INTEGER,account_id INTEGER,account_number TEXT,amount REAL,purpose TEXT,monthly_income REAL,status TEXT DEFAULT 'PENDING_REVIEW',branch_name TEXT NOT NULL DEFAULT 'Main Branch',created_at TEXT DEFAULT CURRENT_TIMESTAMP,reviewed_by TEXT,decision_reason TEXT);''')
  migrations={'applications':{'customer_phone':"TEXT NOT NULL DEFAULT ''",'date_of_birth':"TEXT NOT NULL DEFAULT ''",'address':"TEXT NOT NULL DEFAULT ''",'occupation':"TEXT NOT NULL DEFAULT ''",'branch_name':"TEXT NOT NULL DEFAULT 'Main Branch'"},'accounts':{'branch_name':"TEXT NOT NULL DEFAULT 'Main Branch'"},'deposits':{'branch_name':"TEXT NOT NULL DEFAULT 'Main Branch'"}}
  for table,cols in migrations.items():
   existing={r[1] for r in c.execute(f'PRAGMA table_info({table})').fetchall()}
   for name,ddl in cols.items():
    if name not in existing: c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')
async def ledger(method,path,payload=None):
 async with httpx.AsyncClient(timeout=8) as x:
  r=await x.request(method,LEDGER+path,json=payload,headers={'X-Internal-Secret':INTERNAL});
  if r.status_code>=400: raise HTTPException(r.status_code,r.json().get('detail','Ledger request failed'))
  return r.json()
class Application(BaseModel):
 accountType:str='SAVINGS'; initialDeposit:float=0; phone:str; dateOfBirth:str; address:str; occupation:str; branchName:str='Main Branch'; reason:str='New account application'
class Deposit(BaseModel): accountId:int; amount:float
class Decision(BaseModel): reason:str='Did not meet review requirements'
@app.get('/api/health')
def health(): return {'status':'UP','service':'account-service'}
@app.get('/api/accounts')
async def accounts(u=Depends(current)):
 with db() as c:
  if u['role']=='ADMIN': rows=c.execute('SELECT * FROM accounts ORDER BY id DESC').fetchall()
  elif u['role'] in ('EMPLOYEE','MANAGER'): rows=c.execute('SELECT * FROM accounts WHERE branch_name=? ORDER BY id DESC',(u.get('branch') or '',)).fetchall()
  else: rows=c.execute('SELECT * FROM accounts WHERE owner_user_id=? ORDER BY id DESC',(u['id'],)).fetchall()
 out=[]
 for r in rows:
  a=dict(r); l=await ledger('GET',f"/internal/balances/{a['account_number']}"); a['balance']=l['balance']; out.append(a)
 return out
@app.get('/api/applications')
def applications(u=Depends(current)):
 with db() as c:
  if u['role']=='ADMIN': rows=c.execute('SELECT * FROM applications ORDER BY id DESC').fetchall()
  elif u['role'] in ('EMPLOYEE','MANAGER'): rows=c.execute('SELECT * FROM applications WHERE branch_name=? ORDER BY id DESC',(u.get('branch') or '',)).fetchall()
  else: rows=c.execute('SELECT * FROM applications WHERE customer_user_id=? ORDER BY id DESC',(u['id'],)).fetchall()
 return [dict(x) for x in rows]
@app.post('/api/applications')
def apply(b:Application,u=Depends(current)):
 require(u,'CUSTOMER')
 if not b.branchName.strip(): raise HTTPException(400,'Select a branch.')
 if b.accountType not in ('SAVINGS','CURRENT') or b.initialDeposit<0 or b.initialDeposit>100000: raise HTTPException(400,'Enter valid account type and initial deposit.')
 phone=''.join(ch for ch in b.phone if ch.isdigit())
 if len(phone) != 10: raise HTTPException(400,'Enter a valid 10-digit mobile number.')
 import datetime
 try: dob=datetime.date.fromisoformat(b.dateOfBirth)
 except ValueError: raise HTTPException(400,'Date of birth must be a valid date.')
 today=datetime.date.today(); age=today.year-dob.year-((today.month,today.day)<(dob.month,dob.day))
 if dob>=today or age<18: raise HTTPException(400,'Applicant must be at least 18 years old.')
 if len(b.address.strip())<10 or len(b.occupation.strip())<2: raise HTTPException(400,'Enter a complete address and occupation.')
 if b.accountType=='SAVINGS' and b.initialDeposit<1000: raise HTTPException(400,'Initial deposit must be at least ₹1,000.')
 with db() as c:
  cur=c.execute("INSERT INTO applications(customer_user_id,customer_name,customer_phone,date_of_birth,address,occupation,account_type,initial_deposit,reason,status,branch_name) VALUES(?,?,?,?,?,?,?,?,?,'PENDING_REVIEW',?)",(u['id'],u['name'],phone,b.dateOfBirth,b.address.strip(),b.occupation.strip(),b.accountType,b.initialDeposit,b.reason,b.branchName.strip())); aid=cur.lastrowid
 return {'id':aid,'status':'PENDING_REVIEW','message':'Application submitted for employee review.'}
@app.post('/api/applications/{aid}/verify')
def verify(aid:int,u=Depends(current)):
 require(u,'EMPLOYEE')
 with db() as c:
  a=c.execute('SELECT branch_name FROM applications WHERE id=?',(aid,)).fetchone()
  if not a or a['branch_name']!=(u.get('branch') or ''): raise HTTPException(404,'Application not found in your branch.')
  cur=c.execute("UPDATE applications SET status='VERIFIED',reviewed_by=? WHERE id=? AND status='PENDING_REVIEW'",(u['email'],aid))
 if cur.rowcount!=1: raise HTTPException(409,'Application is not awaiting verification.')
 return {'status':'VERIFIED','message':'Verified; manager approval required.'}
@app.post('/api/applications/{aid}/approve')
async def approve(aid:int,u=Depends(current)):
 require(u,'MANAGER','ADMIN')
 with db() as c:
  a=c.execute('SELECT * FROM applications WHERE id=?',(aid,)).fetchone()
  if u['role']=='MANAGER' and (not a or a['branch_name']!=(u.get('branch') or '')): raise HTTPException(404,'Application not found in your branch.')
  if not a or (a['status']!='VERIFIED' and not (u['role']=='ADMIN' and a['status']=='PENDING_REVIEW')): raise HTTPException(409,'Application must be verified first.')
  number='20'+str(aid).zfill(8)+secrets.token_hex(3).upper()
  cur=c.execute("INSERT INTO accounts(owner_user_id,customer_name,account_type,account_number,balance,minimum_balance,daily_limit,status,branch_name) VALUES(?,?,?,?,0,1000,25000,'ACTIVE',?)",(a['customer_user_id'],a['customer_name'],a['account_type'],number,a['branch_name'])); accid=cur.lastrowid
  await ledger('POST','/internal/accounts',{'accountNumber':number,'ownerUserId':a['customer_user_id'],'openingBalance':float(a['initial_deposit'])})
  if float(a['initial_deposit'])>0:
   async with httpx.AsyncClient(timeout=8) as client:
    event=await client.post(TRANSACTION+'/internal/opening-deposit',json={'reference':'OPENDEP-'+number,'customerUserId':a['customer_user_id'],'customerName':a['customer_name'],'accountId':accid,'accountNumber':number,'amount':float(a['initial_deposit'])},headers={'X-Internal-Secret':INTERNAL})
    if event.status_code>=400: raise HTTPException(event.status_code,'Account was funded but its opening-deposit history event could not be recorded; staff review is required.')
  c.execute("UPDATE applications SET status='APPROVED',account_id=?,reviewed_by=? WHERE id=?",(accid,u['email'],aid))
 return {'status':'APPROVED','accountId':accid,'accountNumber':number,'message':'Account activated.'}
@app.post('/api/applications/{aid}/reject')
def rejectapp(aid:int,b:Decision,u=Depends(current)):
 require(u,'EMPLOYEE','MANAGER','ADMIN')
 with db() as c:
  a=c.execute('SELECT branch_name FROM applications WHERE id=?',(aid,)).fetchone()
  if u['role']!='ADMIN' and (not a or a['branch_name']!=(u.get('branch') or '')): raise HTTPException(404,'Application not found in your branch.')
  cur=c.execute("UPDATE applications SET status='REJECTED',reviewed_by=? WHERE id=? AND status IN ('PENDING_REVIEW','VERIFIED')",(u['email'],aid))
 if not cur.rowcount: raise HTTPException(409,'Application not found or already reviewed.')
 return {'status':'REJECTED','reason':b.reason}
@app.post('/api/deposits')
async def deposit(b:Deposit,u=Depends(current)):
 require(u,'CUSTOMER')
 with db() as c: a=c.execute('SELECT * FROM accounts WHERE id=? AND owner_user_id=?',(b.accountId,u['id'])).fetchone()
 if not a: raise HTTPException(404,'Account not found.')
 if a['status']!='ACTIVE' or b.amount<=0 or b.amount>100000: raise HTTPException(400,'Invalid amount or inactive account.')
 ref='DEP-'+secrets.token_hex(5).upper()
 async with httpx.AsyncClient(timeout=8) as client:
  tr=await client.post(TRANSACTION+'/internal/deposits',json={'reference':ref,'customerUserId':u['id'],'customerName':u['name'],'accountId':b.accountId,'accountNumber':a['account_number'],'amount':b.amount},headers={'X-Internal-Secret':INTERNAL})
  if tr.status_code>=400: raise HTTPException(tr.status_code,tr.json().get('detail','Could not record deposit transaction'))
  did=tr.json()['id']
 with db() as c: c.execute("INSERT INTO deposits(id,reference_no,customer_user_id,customer_name,account_id,amount,status,description,branch_name) VALUES(?,?,?,?,?,?,'PENDING_APPROVAL','Awaiting employee approval',?)",(did,ref,u['id'],u['name'],b.accountId,b.amount,a['branch_name']))
 return {'id':did,'reference_no':ref,'status':'PENDING_APPROVAL','message':'Deposit awaits employee approval.'}
@app.get('/api/deposits')
def deposits(u=Depends(current)):
 require(u,'EMPLOYEE','MANAGER','ADMIN')
 with db() as c:
  if u['role']=='ADMIN': rows=c.execute('SELECT * FROM deposits ORDER BY id DESC').fetchall()
  else: rows=c.execute('SELECT * FROM deposits WHERE branch_name=? ORDER BY id DESC',(u.get('branch') or '',)).fetchall()
 return [dict(x) for x in rows]
@app.post('/api/deposits/{did}/approve')
async def approvedep(did:int,u=Depends(current)):
 require(u,'EMPLOYEE','MANAGER','ADMIN')
 with db() as c:
  d=c.execute('SELECT * FROM deposits WHERE id=?',(did,)).fetchone()
  if not d or d['status']!='PENDING_APPROVAL': raise HTTPException(409,'Deposit is not pending approval.')
  if u['role']!='ADMIN' and d['branch_name']!=(u.get('branch') or ''): raise HTTPException(404,'Deposit not found in your branch.')
  with httpx.Client(timeout=8) as x: r=x.post(LEDGER+'/internal/postings',json={'accountNumber':c.execute('SELECT account_number FROM accounts WHERE id=?',(d['account_id'],)).fetchone()[0],'amount':d['amount'],'kind':'DEPOSIT','reference':d['reference_no'],'description':'Employee-approved deposit'},headers={'X-Internal-Secret':INTERNAL})
  if r.status_code>=400: raise HTTPException(r.status_code,r.json().get('detail','Credit failed'))
  c.execute("UPDATE deposits SET status='SUCCESS',reviewed_by=? WHERE id=?",(u['email'],did))
 async with httpx.AsyncClient(timeout=8) as client: await client.post(TRANSACTION+f'/internal/deposits/{did}/decision',json={'status':'SUCCESS','actor':u['email'],'details':'Employee approval confirmed; ledger credit posted.'},headers={'X-Internal-Secret':INTERNAL})
 return {'status':'SUCCESS','message':'Deposit approved and credited.'}
@app.post('/api/deposits/{did}/reject')
async def rejectdep(did:int,b:Decision,u=Depends(current)):
 require(u,'EMPLOYEE','MANAGER','ADMIN')
 with db() as c:
  d=c.execute('SELECT branch_name FROM deposits WHERE id=?',(did,)).fetchone()
  if u['role']!='ADMIN' and (not d or d['branch_name']!=(u.get('branch') or '')): raise HTTPException(404,'Deposit not found in your branch.')
  cur=c.execute("UPDATE deposits SET status='REJECTED',description=?,reviewed_by=? WHERE id=? AND status='PENDING_APPROVAL'",(b.reason,u['email'],did))
 if not cur.rowcount: raise HTTPException(409,'Deposit is not pending approval.')
 async with httpx.AsyncClient(timeout=8) as client: await client.post(TRANSACTION+f'/internal/deposits/{did}/decision',json={'status':'REJECTED','actor':u['email'],'details':b.reason},headers={'X-Internal-Secret':INTERNAL})
 return {'status':'REJECTED','message':b.reason}
@app.get('/api/summary')
async def summary(u=Depends(current)):
 with db() as c:
  if u['role']=='ADMIN': base={'accounts':c.execute('SELECT count(*) FROM accounts').fetchone()[0],'pendingDeposits':c.execute("SELECT count(*) FROM deposits WHERE status='PENDING_APPROVAL'").fetchone()[0],'pendingApplications':c.execute("SELECT count(*) FROM applications WHERE status IN ('PENDING_REVIEW','VERIFIED')").fetchone()[0]}
  elif u['role'] in ('EMPLOYEE','MANAGER'):
   branch=u.get('branch') or ''
   base={'accounts':c.execute('SELECT count(*) FROM accounts WHERE branch_name=?',(branch,)).fetchone()[0],'pendingDeposits':c.execute("SELECT count(*) FROM deposits WHERE branch_name=? AND status='PENDING_APPROVAL'",(branch,)).fetchone()[0],'pendingApplications':c.execute("SELECT count(*) FROM applications WHERE branch_name=? AND status IN ('PENDING_REVIEW','VERIFIED')",(branch,)).fetchone()[0]}
  else: base={'accounts':c.execute('SELECT count(*) FROM accounts WHERE owner_user_id=?',(u['id'],)).fetchone()[0],'pendingDeposits':c.execute("SELECT count(*) FROM deposits WHERE customer_user_id=? AND status='PENDING_APPROVAL'",(u['id'],)).fetchone()[0],'pendingApplications':c.execute("SELECT count(*) FROM applications WHERE customer_user_id=? AND status IN ('PENDING_REVIEW','VERIFIED')",(u['id'],)).fetchone()[0]}
 async with httpx.AsyncClient(timeout=5) as client:
  r=await client.get(TRANSACTION+'/internal/summary',params={'userId':u['id'],'staff':str(is_staff(u)).lower(),'branch':u.get('branch') or '' if u['role'] in ('EMPLOYEE','MANAGER') else ''},headers={'X-Internal-Secret':INTERNAL})
  if r.status_code==200: base.update(r.json())
  else: base.update({'transactions':0,'reviewRequired':0})
 return base
@app.get('/internal/accounts/{aid}')
def internal_account(aid:int,request:Request):
 if request.headers.get('X-Internal-Secret')!=INTERNAL: raise HTTPException(403,'Internal only')
 with db() as c: a=c.execute('SELECT * FROM accounts WHERE id=?',(aid,)).fetchone()
 if not a: raise HTTPException(404,'Source account not found.')
 return dict(a)
@app.get('/internal/account-number/{number}')
def internal_number(number:str,request:Request):
 if request.headers.get('X-Internal-Secret')!=INTERNAL: raise HTTPException(403,'Internal only')
 with db() as c: a=c.execute('SELECT * FROM accounts WHERE account_number=?',(number,)).fetchone()
 if not a: raise HTTPException(404,'Destination account not found.')
 return dict(a)


class FixedDepositRequest(BaseModel): accountId:int; amount:float; tenureMonths:int
class LoanRequest(BaseModel): accountId:int; amount:float; purpose:str; monthlyIncome:float
class LoanDecision(BaseModel): reason:str='Approved after review'
@app.get('/api/fixed-deposits')
def list_fixed_deposits(u=Depends(current)):
 with db() as c:
  if u['role']=='ADMIN': rows=c.execute('SELECT * FROM fixed_deposits ORDER BY id DESC').fetchall()
  else: rows=c.execute('SELECT * FROM fixed_deposits WHERE customer_user_id=? ORDER BY id DESC',(u['id'],)).fetchall()
 return [dict(r) for r in rows]
@app.post('/api/fixed-deposits')
async def open_fixed_deposit(b:FixedDepositRequest,u=Depends(current)):
 require(u,'CUSTOMER')
 if b.amount<=0 or b.tenureMonths not in (3,6,12,24,36,60): raise HTTPException(400,'Choose a positive amount and a supported tenure (3, 6, 12, 24, 36 or 60 months).')
 with db() as c: a=c.execute("SELECT * FROM accounts WHERE id=? AND owner_user_id=? AND status='ACTIVE'",(b.accountId,u['id'])).fetchone()
 if not a: raise HTTPException(404,'Active source account not found.')
 bal=(await ledger('GET',f"/internal/balances/{a['account_number']}"))['balance']
 if bal-b.amount<float(a['minimum_balance']): raise HTTPException(400,'Opening this fixed deposit would breach your account minimum balance.')
 ref='FD-'+secrets.token_hex(6).upper(); today=datetime.date.today(); maturity=today+datetime.timedelta(days=round(b.tenureMonths*30.4375))
 await ledger('POST','/internal/postings',{'accountNumber':a['account_number'],'amount':b.amount,'kind':'DEBIT','reference':ref+'-LOCK','description':'Fixed deposit principal locked'})
 with db() as c:
  cur=c.execute("INSERT INTO fixed_deposits(reference_no,customer_user_id,account_id,account_number,principal,tenure_months,annual_rate,maturity_date,status) VALUES(?,?,?,?,?,?,6.5,?,'ACTIVE')",(ref,u['id'],b.accountId,a['account_number'],b.amount,b.tenureMonths,maturity.isoformat())); fid=cur.lastrowid
 return {'id':fid,'reference_no':ref,'status':'ACTIVE','maturity_date':maturity.isoformat(),'annual_rate':6.5,'message':'Fixed deposit opened. Principal is locked until maturity.'}
@app.post('/api/fixed-deposits/{fid}/close')
async def close_fixed_deposit(fid:int,u=Depends(current)):
 require(u,'CUSTOMER')
 with db() as c: fd=c.execute('SELECT * FROM fixed_deposits WHERE id=? AND customer_user_id=?',(fid,u['id'])).fetchone()
 if not fd: raise HTTPException(404,'Fixed deposit not found.')
 if fd['status']!='ACTIVE': raise HTTPException(409,'Fixed deposit is already closed.')
 if datetime.date.today()<datetime.date.fromisoformat(fd['maturity_date']): raise HTTPException(400,'Fixed deposit cannot be closed before maturity in this educational version.')
 days=(datetime.date.today()-datetime.date.fromisoformat(fd['created_at'][:10])).days; interest=round(fd['principal']*fd['annual_rate']*days/36500,2); payout=round(fd['principal']+interest,2)
 await ledger('POST','/internal/postings',{'accountNumber':fd['account_number'],'amount':payout,'kind':'CREDIT','reference':fd['reference_no']+'-MATURITY','description':f'Fixed deposit maturity payout including estimated simple interest ₹{interest:.2f}'})
 with db() as c: c.execute("UPDATE fixed_deposits SET status='MATURED_PAID',closed_at=CURRENT_TIMESTAMP WHERE id=? AND status='ACTIVE'",(fid,))
 return {'status':'MATURED_PAID','principal':fd['principal'],'interest':interest,'payout':payout}
@app.get('/api/loans')
def list_loans(u=Depends(current)):
 with db() as c:
  if u['role']=='ADMIN': rows=c.execute('SELECT * FROM loan_applications ORDER BY id DESC').fetchall()
  elif u['role'] in ('EMPLOYEE','MANAGER'): rows=c.execute('SELECT * FROM loan_applications WHERE branch_name=? ORDER BY id DESC',(u.get('branch') or '',)).fetchall()
  else: rows=c.execute('SELECT * FROM loan_applications WHERE customer_user_id=? ORDER BY id DESC',(u['id'],)).fetchall()
 return [dict(r) for r in rows]
@app.post('/api/loans')
def apply_loan(b:LoanRequest,u=Depends(current)):
 require(u,'CUSTOMER')
 if b.amount<5000 or b.amount>1000000 or b.monthlyIncome<=0 or len(b.purpose.strip())<10: raise HTTPException(400,'Loan amount must be ₹5,000–₹10,00,000; enter monthly income and a detailed purpose.')
 with db() as c:
  a=c.execute("SELECT * FROM accounts WHERE id=? AND owner_user_id=? AND status='ACTIVE'",(b.accountId,u['id'])).fetchone()
  if not a: raise HTTPException(404,'Active account not found.')
  cur=c.execute("INSERT INTO loan_applications(customer_user_id,account_id,account_number,amount,purpose,monthly_income,branch_name) VALUES(?,?,?,?,?,?,?)",(u['id'],b.accountId,a['account_number'],b.amount,b.purpose.strip(),b.monthlyIncome,a['branch_name'])); lid=cur.lastrowid
 return {'id':lid,'status':'PENDING_REVIEW','message':'Loan application submitted for branch review. No money has been disbursed.'}
@app.post('/api/loans/{lid}/approve')
async def approve_loan(lid:int,b:LoanDecision,u=Depends(current)):
 require(u,'MANAGER','ADMIN')
 with db() as c:
  loan=c.execute('SELECT * FROM loan_applications WHERE id=?',(lid,)).fetchone()
  if not loan or loan['status']!='PENDING_REVIEW': raise HTTPException(409,'Loan is not pending review.')
  if u['role']=='MANAGER' and loan['branch_name']!=(u.get('branch') or ''): raise HTTPException(404,'Loan application not found in your branch.')
  await ledger('POST','/internal/postings',{'accountNumber':loan['account_number'],'amount':loan['amount'],'kind':'CREDIT','reference':f"LOAN-{lid}-DISBURSE",'description':'Manager-approved educational loan disbursement'})
  c.execute("UPDATE loan_applications SET status='APPROVED_DISBURSED',reviewed_by=?,decision_reason=? WHERE id=?",(u['email'],b.reason,lid))
 return {'status':'APPROVED_DISBURSED','message':'Loan approved and credited to the selected account.'}
@app.post('/api/loans/{lid}/reject')
def reject_loan(lid:int,b:LoanDecision,u=Depends(current)):
 require(u,'MANAGER','ADMIN','EMPLOYEE')
 with db() as c:
  loan=c.execute('SELECT * FROM loan_applications WHERE id=?',(lid,)).fetchone()
  if not loan or loan['status']!='PENDING_REVIEW': raise HTTPException(409,'Loan is not pending review.')
  if u['role']!='ADMIN' and loan['branch_name']!=(u.get('branch') or ''): raise HTTPException(404,'Loan application not found in your branch.')
  c.execute("UPDATE loan_applications SET status='REJECTED',reviewed_by=?,decision_reason=? WHERE id=?",(u['email'],b.reason,lid))
 return {'status':'REJECTED','message':'Loan application rejected; no funds disbursed.'}
