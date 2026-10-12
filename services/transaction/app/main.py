import os, sqlite3, secrets, json, time, asyncio
from datetime import datetime, timezone, timedelta
import httpx
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from shared_security import current, require, is_staff, is_manager

DB = os.getenv('DB_PATH', '/data/transaction.db')
ACCOUNT = os.getenv('ACCOUNT_URL', 'http://account-service:8000')
LEDGER = os.getenv('LEDGER_URL', 'http://ledger-service:8000')
INTERNAL = os.getenv('INTERNAL_SECRET', 'internal-secret-change-me')
RABBIT = os.getenv('RABBITMQ_HOST', 'rabbitmq')
NOTIFICATION = os.getenv('NOTIFICATION_URL', 'http://notification-service:8000')

app = FastAPI(title='Transaction and Saga Orchestrator Service')

_recovery_task = None
_RECOVERY_STALE_SECONDS = int(os.getenv('SAGA_RECOVERY_STALE_SECONDS', '120'))
_RECOVERY_INTERVAL_SECONDS = int(os.getenv('SAGA_RECOVERY_INTERVAL_SECONDS', '30'))
_transfer_lock = asyncio.Lock()

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def audit_log(event_type: str, actor_email: str, actor_role: str, reference_no: str, details: str, status: str = 'SUCCESS'):
    try:
        with db() as c:
            c.execute(
                "INSERT INTO audit_logs(event_type, actor_email, actor_role, reference_no, details, status) VALUES(?,?,?,?,?,?)",
                (event_type, actor_email, actor_role, reference_no, details, status)
            )
    except Exception:
        pass

async def push_notification(email: str, title: str, message: str, category: str = 'ALERT'):
    try:
        async with httpx.AsyncClient(timeout=4) as x:
            await x.post(NOTIFICATION + '/internal/notify', json={'email': email, 'title': title, 'message': message, 'category': category}, headers={'X-Internal-Secret': INTERNAL})
    except Exception:
        pass

@app.on_event('startup')
def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with db() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS transactions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_no TEXT UNIQUE,
                txn_type TEXT,
                customer_user_id INTEGER,
                customer_name TEXT,
                source_account_id INTEGER,
                destination_account_id INTEGER,
                amount REAL,
                status TEXT,
                description TEXT,
                failure_mode TEXT,
                requires_approval INTEGER DEFAULT 0,
                initiator_role TEXT DEFAULT 'CUSTOMER',
                rejection_reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS transaction_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER,
                status TEXT,
                title TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS approval_requests(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER UNIQUE,
                reference_no TEXT UNIQUE,
                initiator_user_id INTEGER,
                initiator_name TEXT,
                initiator_role TEXT,
                source_account_id INTEGER,
                source_account_number TEXT,
                destination_account_number TEXT,
                amount REAL,
                status TEXT DEFAULT 'PENDING_APPROVAL',
                risk_flag TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS system_config(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor_email TEXT,
                actor_role TEXT,
                reference_no TEXT,
                details TEXT,
                status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cols = {r[1] for r in c.execute('PRAGMA table_info(transactions)')}
        for col, ddl in [
            ('requires_approval', 'INTEGER DEFAULT 0'),
            ('initiator_role', "TEXT DEFAULT 'CUSTOMER'"),
            ('rejection_reason', "TEXT DEFAULT ''")
        ]:
            if col not in cols:
                c.execute(f'ALTER TABLE transactions ADD COLUMN {col} {ddl}')
        # Seed default system configs if not present
        configs = [
            ('approval_threshold', '20000', 'Transfers above this INR amount require Manager approval'),
            ('daily_limit', '50000', 'Default daily outgoing transfer limit in INR'),
            ('single_limit', '100000', 'Maximum allowed single transfer limit in INR'),
            ('min_balance', '1000', 'Required savings account minimum balance in INR')
        ]
        for k, v, desc in configs:
            if not c.execute('SELECT 1 FROM system_config WHERE key=?', (k,)).fetchone():
                c.execute('INSERT INTO system_config(key, value, description) VALUES(?,?,?)', (k, v, desc))

def get_config(key: str, default: float) -> float:
    try:
        with db() as c:
            row = c.execute('SELECT value FROM system_config WHERE key=?', (key,)).fetchone()
            if row:
                return float(row['value'])
    except Exception:
        pass
    return default

async def _recover_stale_sagas_once():
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=_RECOVERY_STALE_SECONDS)).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
    with db() as c:
        rows = c.execute(
            "SELECT * FROM transactions WHERE txn_type='TRANSFER' AND status IN ('DEBIT_CONFIRMED','CREDITING','CREDIT_FAILED','COMPENSATING') AND updated_at < ? ORDER BY id LIMIT 100",
            (cutoff,)
        ).fetchall()
    for row in rows:
        t = dict(row)
        tid = t['id']
        ref = t['reference_no']
        try:
            src = await get(f"{ACCOUNT}/internal/accounts/{t['source_account_id']}")
            credit = await get(f"{LEDGER}/internal/entry-by-reference/{ref}-CREDIT")
            if credit.get('found'):
                stage(tid, 'REQUIRES_REVIEW', 'Recovery requires reconciliation', 'A destination-credit ledger entry exists, but the Saga completion state was not safely confirmed. Staff must reconcile both ledger accounts.')
                continue
            stage(tid, 'COMPENSATING', 'Stale Saga recovery started', 'Recovery worker found a stale transfer after source debit and confirmed no destination-credit entry exists. Attempting idempotent source restoration.')
            await post(f"{LEDGER}/internal/postings", {'accountNumber': src['account_number'], 'amount': t['amount'], 'kind': 'COMPENSATION_CREDIT', 'reference': f'{ref}-COMPENSATION', 'description': f'Automated stale-Saga recovery for {ref}'})
            stage(tid, 'COMPENSATED', 'Stale Saga recovered', 'Ledger confirmed the idempotent compensation posting. Destination credit was not present when recovery checked.')
        except Exception as exc:
            try:
                stage(tid, 'REQUIRES_REVIEW', 'Automatic recovery needs staff review', f'Recovery could not prove a safe automatic outcome ({type(exc).__name__}). Staff investigation is required.')
            except Exception:
                pass

async def _recovery_loop():
    while True:
        await asyncio.sleep(_RECOVERY_INTERVAL_SECONDS)
        try:
            await _recover_stale_sagas_once()
        except Exception:
            pass

@app.on_event('startup')
async def start_recovery_worker():
    global _recovery_task
    _recovery_task = asyncio.create_task(_recovery_loop())

@app.on_event('shutdown')
async def stop_recovery_worker():
    global _recovery_task
    if _recovery_task:
        _recovery_task.cancel()
        try:
            await _recovery_task
        except asyncio.CancelledError:
            pass

async def get(url):
    async with httpx.AsyncClient(timeout=8) as x:
        r = await x.get(url, headers={'X-Internal-Secret': INTERNAL})
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.json().get('detail', 'Service request failed'))
        return r.json()

async def post(url, payload):
    async with httpx.AsyncClient(timeout=8) as x:
        r = await x.post(url, json=payload, headers={'X-Internal-Secret': INTERNAL})
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.json().get('detail', 'Service request failed'))
        return r.json()

def publish(txid, status):
    try:
        import pika
        creds = pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'northstar'), os.getenv('RABBITMQ_PASSWORD', 'replace-with-a-strong-rabbitmq-password'))
        conn = pika.BlockingConnection(pika.ConnectionParameters(host=RABBIT, credentials=creds, connection_attempts=1, socket_timeout=1))
        ch = conn.channel()
        ch.exchange_declare(exchange='northstar.events', exchange_type='fanout', durable=True)
        ch.basic_publish(exchange='northstar.events', routing_key='', body=json.dumps({'transactionId': txid, 'status': status, 'occurredAt': datetime.now(timezone.utc).isoformat()}), properties=pika.BasicProperties(delivery_mode=2, content_type='application/json'))
        conn.close()
    except Exception:
        pass

def stage(tid, status, title, details):
    with db() as c:
        c.execute('UPDATE transactions SET status=?,description=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (status, details, tid))
        c.execute('INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,?,?,?)', (tid, status, title, details))
    publish(tid, status)

def gettxn(tid):
    with db() as c:
        t = c.execute('SELECT * FROM transactions WHERE id=?', (tid,)).fetchone()
    if not t:
        raise HTTPException(404, 'Transaction not found.')
    return dict(t)

def access(t, u):
    if not is_staff(u) and t['customer_user_id'] != u['id']:
        raise HTTPException(404, 'Transaction not found.')

class Transfer(BaseModel):
    sourceAccountId: int
    destinationAccountNumber: str
    amount: float
    otp: str = ''
    description: str = 'Fund transfer'

class TestTransfer(Transfer):
    outcome: str = 'SUCCESS'

class ApprovalDecision(BaseModel):
    reason: str = ''

class SystemConfigUpdate(BaseModel):
    approvalThreshold: float = 20000
    dailyLimit: float = 50000
    singleLimit: float = 100000
    minBalance: float = 1000

@app.get('/api/health')
def health():
    return {'status': 'UP', 'service': 'transaction-saga-service'}

# System Configuration API
@app.get('/api/transactions/config')
def get_system_config(u = Depends(current)):
    require(u, 'ADMIN', 'MANAGER')
    with db() as c:
        rows = c.execute('SELECT * FROM system_config').fetchall()
    return {r['key']: r['value'] for r in rows}

@app.post('/api/transactions/config')
def update_system_config(b: SystemConfigUpdate, u = Depends(current)):
    require(u, 'ADMIN')
    with db() as c:
        c.execute("UPDATE system_config SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key='approval_threshold'", (str(b.approvalThreshold),))
        c.execute("UPDATE system_config SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key='daily_limit'", (str(b.dailyLimit),))
        c.execute("UPDATE system_config SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key='single_limit'", (str(b.singleLimit),))
        c.execute("UPDATE system_config SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key='min_balance'", (str(b.minBalance),))
    audit_log('SYSTEM_CONFIG_UPDATED', u['email'], u['role'], 'SYSTEM', f"Updated thresholds: Approval={b.approvalThreshold}, Daily={b.dailyLimit}, Single={b.singleLimit}")
    return {'message': 'System policies updated successfully.'}

# Audit Logs API
@app.get('/api/transactions/audit-logs')
def get_audit_logs(limit: int = 100, u = Depends(current)):
    require(u, 'ADMIN', 'MANAGER')
    with db() as c:
        rows = c.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    return [dict(r) for r in rows]

# Approval Queue for Manager
@app.get('/api/transactions/approvals')
def list_approvals(u = Depends(current)):
    require(u, 'MANAGER', 'ADMIN')
    with db() as c:
        rows = c.execute(
            "SELECT a.*, t.customer_name, t.description as txn_desc, t.created_at as txn_created FROM approval_requests a JOIN transactions t ON a.transaction_id = t.id WHERE a.status='PENDING_APPROVAL' ORDER BY a.id DESC"
        ).fetchall()
    return [dict(r) for r in rows]

# Transfer Orchestration
async def _execute_saga_financial_transfer(tid: int, t: dict, src: dict, dest: dict, reference: str, amount: float, test: bool = False, test_outcome: str = 'SUCCESS'):
    stage(tid, 'PROCESSING', 'Financial workflow in progress', 'Executing atomic debit against source account.')
    debit_ref = f'{reference}-DEBIT'
    try:
        await post(f'{LEDGER}/internal/postings', {
            'accountNumber': src['account_number'],
            'amount': amount,
            'kind': 'DEBIT',
            'reference': debit_ref,
            'description': f'Transfer {reference} source debit'
        })
    except HTTPException as e:
        stage(tid, 'FAILED', 'Source debit failed', str(e.detail))
        return gettxn(tid)
        
    stage(tid, 'DEBIT_CONFIRMED', 'Source debit confirmed', 'Ledger service confirmed the source debit.')
    stage(tid, 'CREDITING', 'Destination credit started', 'Attempting destination account posting.')
    
    credit_ok = False
    if not (test and test_outcome in ('FAIL_CREDIT_COMPENSATE', 'FAIL_CREDIT_REVIEW')):
        try:
            await post(f'{LEDGER}/internal/postings', {
                'accountNumber': dest['account_number'],
                'amount': amount,
                'kind': 'CREDIT',
                'reference': f'{reference}-CREDIT',
                'description': f'Transfer {reference} destination credit'
            })
            credit_ok = True
        except HTTPException:
            credit_ok = False
            
    if credit_ok:
        stage(tid, 'SUCCESS', 'Transfer completed', 'Source debit and destination credit are both durably confirmed.')
        with db() as c:
            c.execute('UPDATE transactions SET destination_account_id=? WHERE id=?', (dest['id'], tid))
        audit_log('TRANSFER_SUCCESS', t['customer_name'], t['initiator_role'], reference, f"Successfully transferred ₹{amount} from {src['account_number']} to {dest['account_number']}")
        return gettxn(tid)
        
    # Credit failed -> initiate Saga compensating reversal
    stage(tid, 'CREDIT_FAILED', 'Destination credit failed', 'Destination credit could not be posted. Initiating compensating refund.')
    stage(tid, 'COMPENSATING', 'Compensation started', 'Saga is attempting to restore source funds with a uniquely identified compensating posting.')
    
    if test and test_outcome == 'FAIL_CREDIT_REVIEW':
        stage(tid, 'REQUIRES_REVIEW', 'Automatic compensation not confirmed', 'Controlled test scenario: source debit remains unresolved. Manual staff reconciliation required.')
        with db() as c:
            c.execute('UPDATE transactions SET destination_account_id=? WHERE id=?', (dest['id'], tid))
        audit_log('TRANSFER_REQUIRES_REVIEW', t['customer_name'], t['initiator_role'], reference, f"Compensation unresolved for ₹{amount}; requires investigation")
        return gettxn(tid)
        
    try:
        await post(f'{LEDGER}/internal/postings', {
            'accountNumber': src['account_number'],
            'amount': amount,
            'kind': 'COMPENSATION_CREDIT',
            'reference': f'{reference}-COMPENSATION',
            'description': f'Compensation for failed transfer {reference}'
        })
        stage(tid, 'COMPENSATED', 'Compensation confirmed', 'Source funds restored by a separate compensating ledger posting. Destination was not credited.')
        audit_log('TRANSFER_COMPENSATED', t['customer_name'], t['initiator_role'], reference, f"Compensated failed transfer of ₹{amount}; source funds restored")
    except HTTPException:
        stage(tid, 'REQUIRES_REVIEW', 'Compensation failed', 'Source funds could not be restored automatically. Staff investigation is required.')
        audit_log('TRANSFER_RECONCILIATION_REQUIRED', t['customer_name'], t['initiator_role'], reference, f"Compensation failed for ₹{amount}")
        
    with db() as c:
        c.execute('UPDATE transactions SET destination_account_id=? WHERE id=?', (dest['id'], tid))
    return gettxn(tid)

async def _run_transfer_serialized(b: Transfer, u: dict, test: bool = False, outcome: str = 'SUCCESS'):
    single_max = get_config('single_limit', 100000.0)
    approval_threshold = get_config('approval_threshold', 20000.0)
    
    if b.amount <= 0 or b.amount > single_max:
        raise HTTPException(400, f'Transfer amount must be greater than zero and no more than ₹{single_max:,.2f}.')
        
    if test:
        require(u, 'ADMIN')
    else:
        require(u, 'CUSTOMER', 'STAFF', 'EMPLOYEE')
        if not b.otp or len(b.otp.strip()) != 6:
            raise HTTPException(400, 'Email OTP is required before initiating a transfer.')
        async with httpx.AsyncClient(timeout=8) as client:
            vr = await client.post(
                NOTIFICATION + '/internal/verify-transfer-otp',
                json={'email': u['email'], 'purpose': 'TRANSFER', 'otp': b.otp.strip()},
                headers={'X-Internal-Secret': INTERNAL}
            )
        if vr.status_code >= 400:
            raise HTTPException(vr.status_code, vr.json().get('detail', 'Email OTP verification failed.'))
            
    src = await get(f'{ACCOUNT}/internal/accounts/{b.sourceAccountId}')
    if not test and u['role'] == 'CUSTOMER' and src['owner_user_id'] != u['id']:
        raise HTTPException(403, 'You do not own this source account.')
        
    reference = 'TRF-' + secrets.token_hex(5).upper()
    role_name = 'STAFF' if u['role'] == 'EMPLOYEE' else u['role']
    
    with db() as c:
        cur = c.execute(
            "INSERT INTO transactions(reference_no,txn_type,customer_user_id,customer_name,source_account_id,amount,status,description,failure_mode,initiator_role) VALUES(?,?,?,?,?,?,'INITIATED',?,? ,?)",
            (reference, 'TRANSFER', u['id'], u['name'], b.sourceAccountId, b.amount, b.description or 'Fund transfer', outcome if test else 'NONE', role_name)
        )
        tid = cur.lastrowid
        c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'INITIATED','Transfer request received','Request recorded. No account balance has changed yet.')", (tid,))
        
    stage(tid, 'VALIDATING', 'Validation started', 'Checking destination, account state, available funds, minimum balance and daily limit.')
    
    try:
        dest = await get(f"{ACCOUNT}/internal/account-number/{b.destinationAccountNumber.strip()}")
    except HTTPException:
        stage(tid, 'VALIDATION_FAILED', 'Destination account not found', f"Recipient account '{b.destinationAccountNumber}' does not exist. Workflow stopped; no funds moved.")
        audit_log('TRANSFER_VALIDATION_FAILED', u['email'], role_name, reference, f"Destination account '{b.destinationAccountNumber}' not found", 'FAILED')
        return gettxn(tid)
        
    if src['account_number'] == dest['account_number']:
        stage(tid, 'VALIDATION_FAILED', 'Invalid destination', 'Source and destination accounts must differ. No funds moved.')
        return gettxn(tid)
        
    if src['status'] != 'ACTIVE' or dest['status'] != 'ACTIVE':
        stage(tid, 'VALIDATION_FAILED', 'Account is not active', 'Both source and destination accounts must be active. No funds moved.')
        return gettxn(tid)
        
    srcbal = (await get(f"{LEDGER}/internal/balances/{src['account_number']}"))['balance']
    with db() as c:
        spent = c.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE source_account_id=? AND txn_type='TRANSFER' AND status IN ('DEBIT_CONFIRMED','CREDITING','CREDIT_FAILED','COMPENSATING','SUCCESS','REQUIRES_REVIEW') AND date(created_at,'+5 hours','+30 minutes')=date('now','+5 hours','+30 minutes')",
            (b.sourceAccountId,)
        ).fetchone()[0]
        
    min_bal = float(src['minimum_balance'])
    daily_lim = float(src['daily_limit'])
    if srcbal - b.amount < min_bal:
        stage(tid, 'VALIDATION_FAILED', 'Insufficient balance', f'Transfer would breach minimum balance (₹{min_bal:,.2f}) or available funds. Available: ₹{srcbal:,.2f}. No funds moved.')
        return gettxn(tid)
        
    if spent + b.amount > daily_lim:
        stage(tid, 'VALIDATION_FAILED', 'Daily limit exceeded', f'Transfer would exceed the daily limit of ₹{daily_lim:,.2f}. Spent today: ₹{spent:,.2f}. No funds moved.')
        return gettxn(tid)
        
    stage(tid, 'VALIDATED', 'Validation passed', 'Destination exists; accounts are active; balance and daily-limit checks passed.')
    
    # Check if Manager Approval is required (amount > approval_threshold)
    requires_approval = (b.amount > approval_threshold) and not test
    if requires_approval:
        with db() as c:
            c.execute('UPDATE transactions SET requires_approval=1, destination_account_id=? WHERE id=?', (dest['id'], tid))
            c.execute(
                "INSERT INTO approval_requests(transaction_id, reference_no, initiator_user_id, initiator_name, initiator_role, source_account_id, source_account_number, destination_account_number, amount, status, risk_flag) VALUES(?,?,?,?,?,?,?,?,?,'PENDING_APPROVAL',?)",
                (tid, reference, u['id'], u['name'], role_name, b.sourceAccountId, src['account_number'], dest['account_number'], b.amount, f'High-value transfer exceeding ₹{approval_threshold:,.2f} policy threshold')
            )
        stage(tid, 'PENDING_APPROVAL', 'Awaiting Manager approval', f'Transfer amount of ₹{b.amount:,.2f} exceeds threshold ₹{approval_threshold:,.2f}. Awaiting Branch Manager review and approval.')
        audit_log('TRANSFER_PENDING_APPROVAL', u['email'], role_name, reference, f'Transfer of ₹{b.amount} submitted to Manager approval queue')
        await push_notification(u['email'], 'Transfer Submitted for Approval', f'Transfer {reference} for ₹{b.amount:,.2f} requires Manager approval before funds are debited.', 'TRANSFER')
        return gettxn(tid)
        
    # If no approval required, execute Saga directly
    return await _execute_saga_financial_transfer(tid, {'customer_name': u['name'], 'initiator_role': role_name}, src, dest, reference, b.amount, test, outcome)

@app.post('/api/transfers')
async def transfer(b: Transfer, u = Depends(current)):
    async with _transfer_lock:
        return await _run_transfer_serialized(b, u, False)

@app.post('/api/admin/saga-test-transfers')
async def test_transfer(b: TestTransfer, u = Depends(current)):
    async with _transfer_lock:
        return await _run_transfer_serialized(b, u, True, b.outcome)

# Manager Approval Actions
@app.post('/api/transactions/{tid}/approve')
async def approve_transaction(tid: int, u = Depends(current)):
    require(u, 'MANAGER', 'ADMIN')
    t = gettxn(tid)
    if t['status'] != 'PENDING_APPROVAL':
        raise HTTPException(409, f"Transaction is not pending approval (current status: {t['status']}).")
        
    # Separation of duties: Anti-self-approval protection
    if t['customer_user_id'] == u['id']:
        raise HTTPException(403, 'Separation of duties violation: You cannot approve a transaction that you initiated.')
        
    async with _transfer_lock:
        src = await get(f"{ACCOUNT}/internal/accounts/{t['source_account_id']}")
        dest = await get(f"{ACCOUNT}/internal/accounts/{t['destination_account_id']}")
        
        # Revalidate conditions before financial execution
        srcbal = (await get(f"{LEDGER}/internal/balances/{src['account_number']}"))['balance']
        if srcbal - t['amount'] < float(src['minimum_balance']):
            stage(tid, 'FAILED', 'Approval execution failed', 'Source account balance became insufficient prior to Manager approval.')
            return gettxn(tid)
            
        stage(tid, 'APPROVED', 'Manager approval recorded', f"Approved by {u['role']} ({u['email']}). Financial processing started.")
        with db() as c:
            c.execute("UPDATE approval_requests SET status='APPROVED', reviewed_by=?, reviewed_at=CURRENT_TIMESTAMP WHERE transaction_id=?", (u['email'], tid))
            
        audit_log('TRANSFER_APPROVED', u['email'], u['role'], t['reference_no'], f"Manager approved transfer of ₹{t['amount']}")
        res = await _execute_saga_financial_transfer(tid, t, src, dest, t['reference_no'], t['amount'], False)
        await push_notification(u['email'], 'Transfer Approved', f"Transfer {t['reference_no']} for ₹{t['amount']:,.2f} has been approved and successfully executed.", 'TRANSFER')
        return res

@app.post('/api/transactions/{tid}/reject')
async def reject_transaction(tid: int, b: ApprovalDecision, u = Depends(current)):
    require(u, 'MANAGER', 'ADMIN')
    t = gettxn(tid)
    if t['status'] != 'PENDING_APPROVAL':
        raise HTTPException(409, f"Transaction is not pending approval (current status: {t['status']}).")
        
    reason = b.reason.strip() or 'Rejected by Branch Manager during policy review'
    stage(tid, 'REJECTED', 'Transfer rejected by Manager', f"Rejected by {u['role']} ({u['email']}): {reason}. No funds were debited.")
    with db() as c:
        c.execute("UPDATE transactions SET rejection_reason=? WHERE id=?", (reason, tid))
        c.execute("UPDATE approval_requests SET status='REJECTED', reason=?, reviewed_by=?, reviewed_at=CURRENT_TIMESTAMP WHERE transaction_id=?", (reason, u['email'], tid))
        
    audit_log('TRANSFER_REJECTED', u['email'], u['role'], t['reference_no'], f"Manager rejected transfer: {reason}")
    await push_notification(u['email'], 'Transfer Rejected', f"Transfer {t['reference_no']} for ₹{t['amount']:,.2f} was rejected: {reason}", 'TRANSFER')
    return gettxn(tid)

# Transaction listing and details
@app.get('/api/transactions')
async def list_transactions(
    status: str = None,
    minAmount: float = None,
    maxAmount: float = None,
    u = Depends(current)
):
    query = 'SELECT * FROM transactions WHERE 1=1'
    params = []
    if not is_staff(u):
        query += ' AND customer_user_id=?'
        params.append(u['id'])
    if status and status.upper() != 'ALL':
        query += ' AND status=?'
        params.append(status.upper())
    if minAmount is not None:
        query += ' AND amount>=?'
        params.append(minAmount)
    if maxAmount is not None:
        query += ' AND amount<=?'
        params.append(maxAmount)
    query += ' ORDER BY id DESC'
    
    with db() as c:
        rows = [dict(r) for r in c.execute(query, tuple(params)).fetchall()]
        
    if u.get('role') in ('MANAGER', 'EMPLOYEE', 'STAFF') and u.get('branch'):
        scoped = []
        for t in rows:
            aid = t.get('source_account_id') or t.get('destination_account_id')
            if not aid:
                continue
            try:
                a = await get(f"{ACCOUNT}/internal/accounts/{aid}")
                if a.get('branch_name') == u['branch']:
                    scoped.append(t)
            except Exception:
                continue
        return scoped
    return rows

async def ensure_branch_scope(t, u):
    if u.get('role') in ('MANAGER', 'EMPLOYEE', 'STAFF'):
        aid = t.get('source_account_id') or t.get('destination_account_id')
        if not aid:
            return
        a = await get(f"{ACCOUNT}/internal/accounts/{aid}")
        if a.get('branch_name') and u.get('branch') and a.get('branch_name') != u['branch']:
            raise HTTPException(404, 'Transaction not found in your branch.')

@app.get('/api/transactions/{tid}/events')
async def events(tid: int, u = Depends(current)):
    t = gettxn(tid)
    access(t, u)
    await ensure_branch_scope(t, u)
    with db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM transaction_events WHERE transaction_id=? ORDER BY id', (tid,)).fetchall()]

@app.post('/api/transactions/{tid}/resolve-review')
async def resolve(tid: int, u = Depends(current)):
    require(u, 'STAFF', 'EMPLOYEE', 'MANAGER', 'ADMIN')
    t = gettxn(tid)
    await ensure_branch_scope(t, u)
    if t['status'] != 'REQUIRES_REVIEW':
        raise HTTPException(409, 'Transaction does not require review.')
    src = await get(f"{ACCOUNT}/internal/accounts/{t['source_account_id']}")
    await post(f"{LEDGER}/internal/postings", {
        'accountNumber': src['account_number'],
        'amount': t['amount'],
        'kind': 'COMPENSATION_CREDIT',
        'reference': f"{t['reference_no']}-MANUAL-RECOVERY",
        'description': f"Authorized recovery for {t['reference_no']}"
    })
    stage(tid, 'COMPENSATED', 'Manual recovery confirmed', f"{u['email']} confirmed the source-fund restoration. Recovery ledger reference recorded.")
    audit_log('MANUAL_RECOVERY_RESOLVED', u['email'], u['role'], t['reference_no'], 'Manual recovery completed')
    return gettxn(tid)

# Internal endpoints
@app.get('/internal/health')
def internal_health(): return {'status': 'UP'}

class DepositEvent(BaseModel): reference: str; customerUserId: int; customerName: str; accountId: int; accountNumber: str; amount: float
class DepositDecision(BaseModel): status: str; actor: str; details: str

@app.post('/internal/deposits')
def internal_create_deposit(b: DepositEvent, request: Request):
    if request.headers.get('X-Internal-Secret') != INTERNAL:
        raise HTTPException(403, 'Internal only')
    with db() as c:
        old = c.execute('SELECT id FROM transactions WHERE reference_no=?', (b.reference,)).fetchone()
        if old:
            return {'id': old['id']}
        cur = c.execute(
            "INSERT INTO transactions(reference_no,txn_type,customer_user_id,customer_name,destination_account_id,amount,status,description) VALUES(?,'DEPOSIT',?,?,?,?,'PENDING_APPROVAL','Deposit request submitted; awaiting approval')",
            (b.reference, b.customerUserId, b.customerName, b.accountId, b.amount)
        )
        tid = cur.lastrowid
        c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'PENDING_APPROVAL','Deposit submitted','No balance changes until employee/manager approves this request.')", (tid,))
    publish(tid, 'PENDING_APPROVAL')
    return {'id': tid}

@app.post('/internal/deposits/{tid}/decision')
def internal_deposit_decision(tid: int, b: DepositDecision, request: Request):
    if request.headers.get('X-Internal-Secret') != INTERNAL:
        raise HTTPException(403, 'Internal only')
    if b.status not in ('SUCCESS', 'REJECTED'):
        raise HTTPException(400, 'Invalid deposit decision.')
    t = gettxn(tid)
    stage(tid, b.status, 'Deposit ' + ('approved and credited' if b.status == 'SUCCESS' else 'rejected'), b.details)
    return {'id': tid, 'status': b.status}

@app.get('/internal/summary')
async def internal_summary(request: Request, userId: int, staff: bool = False, branch: str = ''):
    if request.headers.get('X-Internal-Secret') != INTERNAL:
        raise HTTPException(403, 'Internal only')
    with db() as c:
        if not staff:
            rows = [dict(x) for x in c.execute('SELECT * FROM transactions WHERE customer_user_id=?', (userId,)).fetchall()]
            pending_appr = c.execute("SELECT count(*) FROM transactions WHERE customer_user_id=? AND status='PENDING_APPROVAL'", (userId,)).fetchone()[0]
        else:
            rows = [dict(x) for x in c.execute('SELECT * FROM transactions').fetchall()]
            pending_appr = c.execute("SELECT count(*) FROM transactions WHERE status='PENDING_APPROVAL'").fetchone()[0]
    return {
        'transactions': len(rows),
        'reviewRequired': sum(1 for t in rows if t.get('status') == 'REQUIRES_REVIEW'),
        'pendingApprovals': pending_appr
    }

class OpeningDeposit(BaseModel): reference: str; customerUserId: int; customerName: str; accountId: int; accountNumber: str; amount: float

@app.post('/internal/opening-deposit')
def opening_deposit(b: OpeningDeposit, request: Request):
    if request.headers.get('X-Internal-Secret') != INTERNAL:
        raise HTTPException(403, 'Internal only')
    with db() as c:
        old = c.execute('SELECT id FROM transactions WHERE reference_no=?', (b.reference,)).fetchone()
        if old:
            return {'id': old['id']}
        cur = c.execute(
            "INSERT INTO transactions(reference_no,txn_type,customer_user_id,customer_name,destination_account_id,amount,status,description) VALUES(?,'ACCOUNT_OPENING_DEPOSIT',?,?,?,?,'SUCCESS','Initial deposit posted when approved account was activated')",
            (b.reference, b.customerUserId, b.customerName, b.accountId, b.amount)
        )
        tid = cur.lastrowid
        c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'APPROVED','Account application approved','Manager approval recorded and account activated.')", (tid,))
        c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'OPENING_CREDIT_POSTED','Initial deposit posted',?)", (tid, f"₹{b.amount:,.2f} initial balance posted to ledger account {b.accountNumber}."))
        c.execute("INSERT INTO transaction_events(transaction_id,status,title,details) VALUES(?,'SUCCESS','Account activated','Opening balance and account activation confirmed.')", (tid,))
    publish(tid, 'SUCCESS')
    return {'id': tid, 'status': 'SUCCESS'}
