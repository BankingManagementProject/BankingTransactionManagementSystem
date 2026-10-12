import {useCallback,useEffect,useState} from 'react';
import {Activity,ArrowDownLeft,ArrowLeftRight,ArrowUpRight,Banknote,CheckCircle2,ChevronRight,Clock3,FileText,LayoutDashboard,RefreshCw,ShieldCheck,Users,Wallet,XCircle,AlertTriangle,ClipboardCheck,Landmark} from 'lucide-react';
type Row=Record<string,any>;
const money=(v:any)=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(Number(v||0));
const statusClass=(s:string)=>'status '+(s||'').toLowerCase().replaceAll('_','-');
// Fix UTC timestamps from SQLite (stored without Z suffix) to display in correct local time
const fmtDate=(s:string)=>{if(!s)return '—';const ts=s.endsWith('Z')||s.includes('+')? s : s.replace(' ','T')+'Z';return new Date(ts).toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:true});};
export default function App(){
  const [googleClientId, setGoogleClientId] = useState<string>(() => {
    return (import.meta as any).env?.VITE_GOOGLE_CLIENT_ID || localStorage.getItem('northstar_google_client_id') || '';
  });
  const [showGoogleConfig, setShowGoogleConfig] = useState(false);
  const [clientIdInput, setClientIdInput] = useState('');
  const [authToken,setAuthToken]=useState(()=>localStorage.getItem('northstar_token')||''); const [user,setUser]=useState<Row|null>(()=>{try{return JSON.parse(localStorage.getItem('northstar_user')||'null')}catch{return null}}); const [authMode,setAuthMode]=useState<'LOGIN'|'REGISTER'|'BOOTSTRAP'>('LOGIN'); const [authForm,setAuthForm]=useState({fullName:'',email:'',password:'',bootstrapSecret:''}); const [authError,setAuthError]=useState(''); const [authMessage,setAuthMessage]=useState(''); const [authBusy,setAuthBusy]=useState(false); const [staffForm,setStaffForm]=useState({fullName:'',email:'',password:'',role:'EMPLOYEE',branchName:'Main Branch'}); const [transferOtp,setTransferOtp]=useState(''); const [transferOtpSent,setTransferOtpSent]=useState(false); const [fdForm,setFdForm]=useState({accountId:'',amount:'',tenureMonths:'12'}); const [loanForm,setLoanForm]=useState({accountId:'',amount:'',purpose:'',monthlyIncome:''}); const [fixedDeposits,setFixedDeposits]=useState<Row[]>([]); const [loans,setLoans]=useState<Row[]>([]); const role=String(user?.role||'CUSTOMER'); const [tab,setTab]=useState('Overview'); const [accounts,setAccounts]=useState<Row[]>([]); const [apps,setApps]=useState<Row[]>([]); const [txns,setTxns]=useState<Row[]>([]); const [events,setEvents]=useState<Row[]>([]); const [selected,setSelected]=useState<Row|null>(null); const [summary,setSummary]=useState<Row>({}); const [notice,setNotice]=useState(''); const [error,setError]=useState(''); const [busy,setBusy]=useState(false);
  const [deposit,setDeposit]=useState({accountId:'',amount:'',description:''}); const [application,setApplication]=useState({accountType:'SAVINGS',initialDeposit:'',phone:'',dateOfBirth:'',address:'',occupation:'',branchName:'Main Branch',reason:'New account application'}); const [transfer,setTransfer]=useState({sourceAccountId:'',destinationAccountId:'',amount:'',demoOutcome:'SUCCESS'});
 const request=useCallback(async(path:string,opts:RequestInit={})=>{const res=await fetch('/api'+path,{...opts,headers:{'Content-Type':'application/json',...(authToken?{Authorization:'Bearer '+authToken}:{}),...opts.headers}});const data=await res.json().catch(()=>({message:'Unexpected server response'}));if(res.status===401 && authToken){localStorage.removeItem('northstar_token');localStorage.removeItem('northstar_user');setAuthToken('');setUser(null);}if(!res.ok)throw new Error(data.message||data.detail||data.error||'Request failed');return data;},[authToken]);
 const load=useCallback(async()=>{try{const [a,ap,t,s,fd,lo]=await Promise.all([request('/accounts'),request('/applications'),request('/transactions'),request('/summary'),request('/fixed-deposits').catch(()=>[]),request('/loans').catch(()=>[])]);setAccounts(a);setApps(ap);setTxns(t);setSummary(s);setFixedDeposits(fd);setLoans(lo)}catch(e:any){setError(e.message+' — if this is a fresh start, wait for containers to finish starting and refresh.')}},[request]);
 useEffect(()=>{if(!authToken)return;load();const timer=setInterval(load,7000);return()=>clearInterval(timer)},[load,authToken]);
 useEffect(()=>{if(accounts.length===0){setDeposit(v=>({...v,accountId:''}));setTransfer(v=>({...v,sourceAccountId:''}));return;}setDeposit(v=>({...v,accountId:accounts.some(a=>String(a.id)===v.accountId)?v.accountId:String(accounts[0].id)}));setTransfer(v=>({...v,sourceAccountId:accounts.some(a=>String(a.id)===v.sourceAccountId)?v.sourceAccountId:String(accounts[0].id)}));},[accounts]);
 const act=async(fn:()=>Promise<any>,success?:string)=>{setBusy(true);setError('');setNotice('');try{const r=await fn();setNotice(success||r.message||'Completed successfully.');await load();return r}catch(e:any){setError(e.message)}finally{setBusy(false)}};
 const openTxn=async(t:Row)=>{setSelected(t);setEvents([]);try{const [latest,ev]=await Promise.all([request('/transactions'),request('/transactions/'+t.id+'/events')]);setSelected(latest.find((x:Row)=>x.id===t.id)||t);setEvents(ev)}catch(e:any){setError(e.message)}};
 const doDeposit=()=>act(()=>request('/deposits',{method:'POST',body:JSON.stringify({accountId:Number(deposit.accountId),amount:deposit.amount})}),'Deposit request submitted. No balance changes until an employee approves it.').then(()=>setTab('Transactions'));
 const requestTransferOtp=()=>act(()=>request('/notifications/transfer-otp',{method:'POST'}),'Transfer OTP sent to your registered email.').then(()=>setTransferOtpSent(true));
 const doTransfer=()=>act(()=>request('/transfers',{method:'POST',body:JSON.stringify({sourceAccountId:Number(transfer.sourceAccountId),destinationAccountNumber:transfer.destinationAccountId.trim(),amount:transfer.amount,otp:transferOtp})})).then((r:any)=>{if(r?.status==='VALIDATION_FAILED')setNotice(r.description||'Transfer stopped during validation. No funds were moved.');else if(r?.status==='SUCCESS')setNotice('Transfer completed successfully. Open its timeline to inspect the recorded stages.');setTransferOtp('');setTransferOtpSent(false);setTab('Transactions')});
  const isStaff = ['EMPLOYEE', 'MANAGER', 'ADMIN'].includes(role);
  const nav = [
    ['Overview', LayoutDashboard],
    ['Accounts', Wallet],
    ['Deposit requests', ArrowDownLeft],
    ['Transfer money', ArrowLeftRight],
    ['Transactions', Activity],
    ['Applications', ClipboardCheck],
    ...(role === 'CUSTOMER' ? [['Fixed deposits', Banknote] as const] : []),
    ['Loans', FileText],
    ...(role === 'ADMIN' ? [['Staff access', Users] as const] : [])
  ] as const;

  // Fetch Google Client ID from backend if not already set
  useEffect(() => {
    if (!googleClientId) {
      fetch('/api/auth/google-client-id')
        .then(r => r.json())
        .then(d => {
          if (d.clientId) {
            setGoogleClientId(d.clientId);
            localStorage.setItem('northstar_google_client_id', d.clientId);
          }
        })
        .catch(() => {});
    }
  }, [googleClientId]);

  // Initialize Google Identity Services and render official Google Sign In button
  useEffect(() => {
    if (!googleClientId) return;
    let tries = 0;
    const timer = setInterval(() => {
      tries++;
      const g = (window as any).google;
      if (!g?.accounts?.id) {
        if (tries > 40) clearInterval(timer);
        return;
      }
      clearInterval(timer);
      try {
        g.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (resp: any) => {
            setAuthBusy(true);
            setAuthError('');
            try {
              const r = await fetch('/api/auth/google', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ credential: resp.credential })
              });
              const d = await r.json();
              if (!r.ok) throw new Error(d.detail || d.message || 'Google sign-in failed');
              localStorage.setItem('northstar_token', d.accessToken);
              localStorage.setItem('northstar_user', JSON.stringify(d.user));
              setAuthToken(d.accessToken);
              setUser(d.user);
              setTab('Overview');
              setNotice('Signed in successfully with your Google account!');
            } catch (e: any) {
              setAuthError(e.message);
            } finally {
              setAuthBusy(false);
            }
          }
        });

        const target = document.getElementById('google-signin-btn-slot');
        if (target) {
          target.innerHTML = '';
          g.accounts.id.renderButton(target, {
            theme: 'outline',
            size: 'large',
            text: authMode === 'REGISTER' ? 'signup_with' : 'signin_with',
            shape: 'rectangular',
            width: 380,
            logo_alignment: 'left'
          });
        }
        try { g.accounts.id.prompt(); } catch {}
      } catch (err: any) {
        console.error('Failed to initialize Google Sign-In:', err);
      }
    }, 200);
    return () => clearInterval(timer);
  }, [googleClientId, authMode]);

  const saveGoogleClientId = (e: any) => {
    e.preventDefault();
    const cid = clientIdInput.trim();
    if (!cid) return;
    setGoogleClientId(cid);
    localStorage.setItem('northstar_google_client_id', cid);
    setShowGoogleConfig(false);
    fetch('/api/auth/google-client-id', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clientId: cid })
    }).catch(() => {});
  };

  const authSubmit = async (e: any) => {
    e.preventDefault();
    setAuthBusy(true);
    setAuthError('');
    setAuthMessage('');
    try {
      const endpoint = authMode === 'REGISTER' ? '/api/auth/register' : authMode === 'BOOTSTRAP' ? '/api/auth/bootstrap-admin' : '/api/auth/login';
      const payload = authMode === 'REGISTER'
        ? { fullName: authForm.fullName, email: authForm.email, password: authForm.password }
        : authMode === 'BOOTSTRAP'
          ? { fullName: authForm.fullName, email: authForm.email, password: authForm.password, bootstrapSecret: authForm.bootstrapSecret }
          : { email: authForm.email, password: authForm.password };
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({ message: 'Unexpected server response' }));
      if (!res.ok) throw new Error(data.message || data.detail || 'Authentication failed');
      if (authMode === 'BOOTSTRAP') {
        setAuthMessage('Administrator created. Sign in using the new administrator credentials.');
        setAuthMode('LOGIN');
        setAuthForm({ ...authForm, bootstrapSecret: '', password: '' });
      } else {
        localStorage.setItem('northstar_token', data.accessToken);
        localStorage.setItem('northstar_user', JSON.stringify(data.user));
        setAuthToken(data.accessToken);
        setUser(data.user);
        setTab('Overview');
        if (authMode === 'REGISTER') {
          setNotice('Customer account created successfully! Welcome to Northstar Bank.');
        }
      }
    } catch (e: any) {
      setAuthError(e.message);
    } finally {
      setAuthBusy(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('northstar_token');
    localStorage.removeItem('northstar_user');
    setAuthToken('');
    setUser(null);
    setAccounts([]);
    setApps([]);
    setTxns([]);
    setSelected(null);
    setEvents([]);
    setTab('Overview');
  };

  if (!authToken || !user) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <div className="brand auth-brand">
            <div className="brandmark"><Landmark size={22} /></div>
            <div><b>northstar</b><small> DIGITAL BANK</small></div>
          </div>
          <p className="eyebrow">SECURE ONLINE BANKING</p>
          <h1>
            {authMode === 'LOGIN' ? 'Sign in to your bank' : authMode === 'REGISTER' ? 'Create your customer account' : 'Set up the first administrator'}
          </h1>
          <p className="auth-subtitle">
            {authMode === 'REGISTER' ? 'Enter your details below to instantly open your customer portal.' : 'Use your credentials to access your banking workspace.'}
          </p>

          {authError && <div className="notice error">{authError}</div>}
          {authMessage && <div className="notice success">{authMessage}</div>}

          {/* Google Sign In Section */}
          {authMode !== 'BOOTSTRAP' && (
            <div style={{ marginBottom: '16px' }}>
              {googleClientId ? (
                <div
                  id="google-signin-btn-slot"
                  style={{ display: 'flex', justifyContent: 'center', minHeight: '44px' }}
                />
              ) : (
                <button
                  type="button"
                  className="google-btn"
                  onClick={() => setShowGoogleConfig(true)}
                  disabled={authBusy}
                  id="google-custom-btn"
                >
                  <svg width="18" height="18" viewBox="0 0 48 48">
                    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                  </svg>
                  <span>{authMode === 'REGISTER' ? 'Sign up with Google' : 'Sign in with Google'}</span>
                </button>
              )}
              <div className="auth-divider"><span>or continue with email</span></div>
            </div>
          )}

          <form className="form" onSubmit={authSubmit}>
            {(authMode === 'REGISTER' || authMode === 'BOOTSTRAP') && (
              <Field label="Full name">
                <input
                  value={authForm.fullName}
                  onChange={e => setAuthForm({ ...authForm, fullName: e.target.value })}
                  placeholder="e.g. John Doe"
                  required
                />
              </Field>
            )}
            <Field label="Email address">
              <input
                type="email"
                autoComplete="username"
                value={authForm.email}
                onChange={e => setAuthForm({ ...authForm, email: e.target.value })}
                placeholder="name@example.com"
                required
              />
            </Field>
            <Field label="Password">
              <input
                type="password"
                autoComplete={authMode === 'LOGIN' ? 'current-password' : 'new-password'}
                minLength={authMode === 'LOGIN' ? 1 : 10}
                value={authForm.password}
                onChange={e => setAuthForm({ ...authForm, password: e.target.value })}
                placeholder={authMode === 'LOGIN' ? '••••••••' : 'Min 10 chars (letters + numbers)'}
                required
              />
            </Field>
            {authMode === 'BOOTSTRAP' && (
              <Field label="One-time administrator bootstrap secret">
                <input
                  type="password"
                  value={authForm.bootstrapSecret}
                  onChange={e => setAuthForm({ ...authForm, bootstrapSecret: e.target.value })}
                  required
                />
              </Field>
            )}
            <button className="primary" disabled={authBusy}>
              {authBusy ? 'Please wait…' : authMode === 'LOGIN' ? 'Sign in' : authMode === 'REGISTER' ? 'Create customer account' : 'Create first administrator'}{' '}
              <ChevronRight size={17} />
            </button>
          </form>

          <div className="auth-links">
            {authMode !== 'LOGIN' && (
              <button type="button" onClick={() => { setAuthMode('LOGIN'); setAuthError(''); setAuthMessage(''); }}>
                Back to sign in
              </button>
            )}
            {authMode === 'LOGIN' && (
              <>
                <button type="button" onClick={() => { setAuthMode('REGISTER'); setAuthError(''); setAuthMessage(''); }}>
                  New customer? Register
                </button>
                <button type="button" onClick={() => { setAuthMode('BOOTSTRAP'); setAuthError(''); setAuthMessage(''); }}>
                  Initial administrator setup
                </button>
              </>
            )}
          </div>
          <small className="auth-foot">Educational banking simulator · Northstar Bank Online Services</small>
        </div>

        {/* Google OAuth Configuration Modal (only shown if Google Client ID is not configured yet) */}
        {showGoogleConfig && (
          <div className="google-modal-overlay" onClick={() => setShowGoogleConfig(false)}>
            <div className="google-modal" onClick={e => e.stopPropagation()}>
              <div className="google-modal-header">
                <svg width="22" height="22" viewBox="0 0 48 48">
                  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                </svg>
                <h3>Connect Google Sign-In</h3>
              </div>
              <p>To display your real Google accounts, enter your Google OAuth Web Client ID below:</p>
              <form onSubmit={saveGoogleClientId} style={{ display: 'grid', gap: '12px' }}>
                <input
                  type="text"
                  placeholder="e.g. 123456789-abcdef.apps.googleusercontent.com"
                  value={clientIdInput}
                  onChange={e => setClientIdInput(e.target.value)}
                  required
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid #dfe5ec', borderRadius: '8px', fontSize: '12px' }}
                />
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button type="button" className="secondary" onClick={() => setShowGoogleConfig(false)} style={{ flex: 1 }}>
                    Cancel
                  </button>
                  <button type="submit" className="primary" style={{ flex: 1 }}>
                    Connect Google
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    );
  }
 return <div className="shell"><aside className="sidebar"><div className="brand"><div className="brandmark"><Landmark size={22}/></div><div><b>northstar</b><small> DIGITAL BANK</small></div></div><div className="profile"><div className="avatar">{role==='CUSTOMER'?'CU':role==='EMPLOYEE'?'EO':role==='MANAGER'?'BM':'SA'}</div><div><b>{role==='CUSTOMER'?'Customer workspace':role==='EMPLOYEE'?'Operations Officer':role==='MANAGER'?'Branch Manager':'System Admin'}</b><small>{role.replace('_',' ')}{user?.branch?` · ${user.branch}`:''}</small></div></div><div className="navlabel">WORKSPACE</div><nav>{nav.map(([label,Icon])=><button key={label} className={'navitem '+(tab===label?'active':'')} onClick={()=>setTab(label)}><Icon size={18}/><span>{label}</span>{label==='Deposit requests'&&Number(summary.pendingDeposits)>0&&<i>{summary.pendingDeposits}</i>}</button>)}</nav><div className="sidebar-bottom"><div className="secure"><ShieldCheck size={18}/><div><b>Secure workspace</b><small>Account operations</small></div></div><small className="buildtag">ONLINE BANKING · MVP 1.0</small></div></aside>
 <main className="main"><header className="topbar"><div><div className="eyebrow">DIGITAL BANKING / {tab.toUpperCase()}</div><h1>{tab==='Overview'?'Welcome to Northstar Bank':tab}</h1><p>{tab==='Overview'?'Your money, your view. A clear picture of your banking activity.':'Manage accounts, review requests and track transaction stages.'}</p></div><div className="top-actions"><div className="signed-in"><b>{user?.fullName||user?.full_name||user?.email}</b><small>{role} · authenticated</small></div><button className="secondary" onClick={logout}>Sign out</button><button className="iconbtn" title="Refresh" onClick={load}><RefreshCw size={18}/></button></div></header>
 {notice&&<div className="notice success"><CheckCircle2 size={18}/>{notice}<button onClick={()=>setNotice('')}>×</button></div>}{error&&<div className="notice error"><AlertTriangle size={18}/>{error}<button onClick={()=>setError('')}>×</button></div>}
 {tab==='Overview'&&<><section className="hero"><div className="hero-copy"><div className="hero-kicker"><span className="live-dot"/> ACCOUNT OVERVIEW</div><div className="hero-label">Total available balance</div><div className="hero-balance">{money(accounts.filter(a=>a.status==='ACTIVE').reduce((n,a)=>n+Number(a.balance),0))}</div><div className="hero-foot"><span><CheckCircle2 size={15}/> All balances from account service</span><span>INR · Indian Rupee</span></div></div><div className="hero-art"><div className="orbit orbit1"/><div className="orbit orbit2"/><div className="hero-emblem"><Landmark size={58}/></div><div className="float-card"><span>ACCOUNT STATUS</span><b><i/> {accounts.some(a=>a.status==='ACTIVE')?'Active and monitored':'Awaiting first account'}</b></div></div></section>
 <section className="stats"><Stat icon={<Wallet/>} label="Active accounts" value={accounts.filter(a=>a.status==='ACTIVE').length} sub="Approved and available"/><Stat icon={<Clock3/>} label="Pending deposits" value={summary.pendingDeposits||0} sub="Awaiting staff approval"/><Stat icon={<Activity/>} label="Transactions" value={summary.transactions||0} sub="All recorded activity"/><Stat icon={<AlertTriangle/>} label="Needs review" value={summary.reviewRequired||0} sub="Requires staff action"/></section>
 <section className="content-grid"><div className="panel"><div className="panel-head"><div><h2>Your accounts</h2><p>Account balances and product rules</p></div><button className="textbtn" onClick={()=>setTab('Accounts')}>View all <ChevronRight size={15}/></button></div><div className="account-list">{accounts.length===0&&<Empty text="No active accounts yet. Submit an application and have it approved to create your first account."/>}{accounts.map((a,i)=><div className="account-row" key={a.id}><div className={'account-icon tone'+(i%3)}><Landmark size={20}/></div><div className="account-info"><b>{a.account_type==='SAVINGS'?'Savings account':'Current account'}</b><small>•••• {String(a.account_number).slice(-4)} · {a.account_number}</small><small>Minimum balance {money(a.minimum_balance)} · Daily limit {money(a.daily_limit)}</small></div><div className="account-balance"><b>{money(a.balance)}</b><span className={statusClass(a.status)}>{a.status}</span></div></div>)}</div></div><div className="panel activity-panel"><div className="panel-head"><div><h2>Recent activity</h2><p>Latest requests and transaction outcomes</p></div><button className="textbtn" onClick={()=>setTab('Transactions')}>History <ChevronRight size={15}/></button></div><div className="recent-list">{txns.slice(0,5).map(t=><button className="recent-row" key={t.id} onClick={()=>openTxn(t)}><div className="recent-icon"><Activity size={17}/></div><div className="recent-info"><b>{t.txn_type==='DEPOSIT'?'Deposit request':t.txn_type==='TRANSFER'?'Internal transfer':'Bank transaction'}</b><small>{t.reference_no} · {fmtDate(t.created_at)}</small></div><div className="recent-amount"><b>{money(t.amount)}</b><span className={statusClass(t.status)}>{t.status}</span></div></button>)}{txns.length===0&&<Empty text="No transactions yet. Submit a deposit or transfer to begin."/>}</div></div></section></>}
 {tab==='Accounts'&&<><div className="section-intro"><div><h2>Your accounts &amp; applications</h2><p>All your active accounts are listed below. You can also submit a new account application for employee review.</p></div><button className="secondary" onClick={load}><RefreshCw size={15}/> Refresh</button></div>{/* Existing accounts list */}<div className="panel" style={{marginBottom:'24px'}}><div className="panel-head"><div><h2>All accounts</h2><p>Your approved and pending accounts</p></div><span className="count-bubble">{accounts.length}</span></div><div className="account-list">{accounts.length===0&&<Empty text="No accounts yet. Submit an application below to open your first account."/>}{accounts.map((a,i)=><div className="account-row" key={a.id}><div className={'account-icon tone'+(i%3)}><Landmark size={20}/></div><div className="account-info"><b>{a.account_type==='SAVINGS'?'Savings account':'Current account'}</b><small>Account No: {a.account_number}</small><small>Min balance {money(a.minimum_balance)} · Daily limit {money(a.daily_limit)} · Opened {fmtDate(a.created_at)}</small></div><div className="account-balance"><b>{money(a.balance)}</b><span className={statusClass(a.status)}>{a.status}</span></div></div>)}</div></div><div className="two-col"><div className="panel"><div className="panel-head"><div><h2>Open a new account</h2><p>Submit for review — no instant activation</p></div></div><form className="form" onSubmit={e=>{e.preventDefault();act(()=>request('/applications',{method:'POST',body:JSON.stringify(application)}),'Application submitted for employee review.').then(()=>setApplication({accountType:'SAVINGS',initialDeposit:'',phone:'',dateOfBirth:'',address:'',occupation:'',branchName:'Main Branch',reason:'New account application'}))}}><div className="info-box"><Users size={18}/><span>Application submitted under your verified sign-in identity: <b>{user?.fullName||user?.full_name}</b>.</span></div><Field label="Applicant full name"><input value={user?.fullName||user?.full_name||''} readOnly required/></Field><Field label="Mobile number (10 digits)"><input type="tel" inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={application.phone} onChange={e=>setApplication({...application,phone:e.target.value.replace(/\D/g,'').slice(0,10)})} placeholder="9876543210" required/></Field><Field label="Date of birth"><input type="date" max={new Date().toISOString().slice(0,10)} value={application.dateOfBirth} onChange={e=>setApplication({...application,dateOfBirth:e.target.value})} required/></Field><Field label="Residential address"><textarea minLength={10} rows={3} value={application.address} onChange={e=>setApplication({...application,address:e.target.value})} placeholder="House / street, area, city, state, PIN code" required/></Field><Field label="Occupation"><input minLength={2} value={application.occupation} onChange={e=>setApplication({...application,occupation:e.target.value})} placeholder="Student, employed, self-employed…" required/></Field><Field label="Branch"><select value={(application as any).branchName||'Main Branch'} onChange={e=>setApplication({...application,branchName:e.target.value})}><option>Main Branch</option><option>Guntur Branch</option><option>Vijayawada Branch</option><option>Amaravati Branch</option><option>Visakhapatnam Branch</option><option>Hyderabad Branch</option></select></Field><Field label="Account type"><select value={application.accountType} onChange={e=>setApplication({...application,accountType:e.target.value})}><option value="SAVINGS">Savings account</option><option value="CURRENT">Current account</option></select></Field><Field label="Initial deposit (₹)"><input type="number" min="1000" max="100000" step="100" value={application.initialDeposit} onChange={e=>setApplication({...application,initialDeposit:e.target.value})} required/></Field><Field label="Purpose / notes"><input value={application.reason} onChange={e=>setApplication({...application,reason:e.target.value})} required/></Field><button className="primary" disabled={busy||role!=='CUSTOMER'}>Submit account application <ChevronRight size={17}/></button>{role!=='CUSTOMER'&&<small className="help">Switch to Customer to submit an application.</small>}</form></div><div className="panel"><div className="panel-head"><div><h2>Account rules</h2><p>Current account policies</p></div></div><Rule title="Savings minimum balance" value="₹1,000"/><Rule title="Daily outgoing transfer limit" value="₹25,000"/><Rule title="Initial deposit approval" value="Employee required"/><Rule title="Overdraft" value="Disabled"/><div className="info-box"><ShieldCheck size={18}/><span>Product values are configurable policies and may differ from real bank terms. Account creation and activation are separate steps.</span></div></div></div></>}
 {tab==='Deposit requests'&&<><div className="section-intro"><div><h2>Deposit workflow</h2><p>Every deposit requires employee approval before funds are credited.</p></div><span className="pill">{summary.pendingDeposits||0} awaiting review</span></div><div className="two-col"><div className="panel"><div className="panel-head"><div><h2>Request a deposit</h2><p>Submitting a request does not change your balance</p></div><div className="round-icon"><Banknote/></div></div><form className="form" onSubmit={e=>{e.preventDefault();doDeposit()}}><Field label="Credit account"><select value={deposit.accountId} onChange={e=>setDeposit({...deposit,accountId:e.target.value})} required><option value="">Select an active account</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_number} · {a.account_type} · {money(a.balance)}</option>)}</select></Field><Field label="Deposit amount (₹)"><input type="number" min="1" max="100000" step="0.01" value={deposit.amount} onChange={e=>setDeposit({...deposit,amount:e.target.value})} required/></Field><div className="info-box"><Clock3 size={18}/><span>After submission, status becomes <b>PENDING_APPROVAL</b>. The balance remains unchanged until an employee approves it.</span></div><button className="primary" disabled={busy||role!=='CUSTOMER'||accounts.length===0||!deposit.accountId}><ArrowDownLeft size={17}/> Submit deposit for approval</button>{role!=='CUSTOMER'&&<small className="help">Switch to Customer to submit a deposit.</small>}</form></div><div className="panel"><div className="panel-head"><div><h2>Awaiting approval</h2><p>Employee review queue</p></div><span className="count-bubble">{txns.filter(t=>t.txn_type==='DEPOSIT'&&t.status==='PENDING_APPROVAL').length}</span></div>{txns.filter(t=>t.txn_type==='DEPOSIT'&&t.status==='PENDING_APPROVAL').map(t=><div className="queue-row" key={t.id}><div><b>{money(t.amount)} deposit</b><small>{t.reference_no} · Account #{t.destination_account_id}</small><small>{fmtDate(t.created_at)}</small></div>{isStaff?<div className="queue-actions"><button className="approve" disabled={busy} onClick={()=>act(()=>request('/deposits/'+t.id+'/approve',{method:'POST'}),'Deposit approved and balance credited.')}>Approve</button><button className="reject" disabled={busy} onClick={()=>act(()=>request('/deposits/'+t.id+'/reject',{method:'POST',body:JSON.stringify({reason:'Rejected during staff review'})}),'Deposit rejected. Balance unchanged.')}>Reject</button></div>:<span className={statusClass(t.status)}>{t.status}</span>}</div>)}{txns.filter(t=>t.txn_type==='DEPOSIT'&&t.status==='PENDING_APPROVAL').length===0&&<Empty text="No deposits waiting for approval."/>}{!isStaff&&<div className="info-box"><Users size={18}/><span>An authorized employee must approve or reject pending requests.</span></div>}</div></div></>}
 {tab==='Transfer money'&&<><div className="section-intro"><div><h2>Transfer between accounts</h2><p>Each transaction timeline stops at the last stage actually reached.</p></div><span className="pill">Saga orchestration</span></div>{role==='ADMIN'?<div className="two-col"><div className="panel"><div className="panel-head"><div><h2>Admin Saga test runner</h2><p>Run controlled failure scenarios against real demo accounts you create.</p></div><div className="round-icon"><Activity/></div></div><form className="form" onSubmit={e=>{e.preventDefault();act(()=>request('/admin/saga-test-transfers',{method:'POST',body:JSON.stringify({sourceAccountId:Number(transfer.sourceAccountId),destinationAccountNumber:transfer.destinationAccountId.trim(),amount:transfer.amount,outcome:transfer.demoOutcome})}),'Saga workflow finished. Open the transaction timeline to inspect each persisted stage.').then(()=>setTab('Transactions'))}}><Field label="Source account"><select value={transfer.sourceAccountId} onChange={e=>setTransfer({...transfer,sourceAccountId:e.target.value})} required><option value="">Select source account</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_number} · {money(a.balance)}</option>)}</select></Field><Field label="Destination account number"><input value={transfer.destinationAccountId} onChange={e=>setTransfer({...transfer,destinationAccountId:e.target.value})} placeholder="Enter an existing account number" required/></Field><Field label="Amount (₹)"><input type="number" min="1" step="0.01" value={transfer.amount} onChange={e=>setTransfer({...transfer,amount:e.target.value})} required/></Field><Field label="Scenario (admin test only)"><select value={transfer.demoOutcome} onChange={e=>setTransfer({...transfer,demoOutcome:e.target.value})}><option value="SUCCESS">Success — debit and credit confirmed</option><option value="FAIL_CREDIT_COMPENSATE">Destination credit fails — compensation succeeds</option><option value="FAIL_CREDIT_REVIEW">Destination credit and compensation fail — review required</option></select></Field><button className="primary" disabled={busy||accounts.length===0||!transfer.sourceAccountId||!transfer.destinationAccountId.trim()}>Run Saga test <ChevronRight size={17}/></button></form></div><div className="panel"><div className="panel-head"><div><h2>Expected stages</h2><p>Only events reached by this run appear in its history.</p></div></div><div className="saga-steps"><Step n="01" title="PENDING → VALIDATING" text="Request recorded; destination and rules checked."/><Step n="02" title="VALIDATED" text="Only appears when all validation checks pass."/><Step n="03" title="DEBIT_CONFIRMED" text="Source debit is committed as a separate step."/><Step n="04" title="CREDITING" text="Destination credit is attempted."/><Step n="05" title="Outcome" text="SUCCESS, COMPENSATING → COMPENSATED, or REQUIRES_REVIEW."/></div><div className="info-box warning"><AlertTriangle size={18}/><span>Use an existing destination account to test Saga compensation. To test a missing recipient, use the normal customer transfer form and enter a nonexistent account number; the timeline should stop at validation failure without debiting funds.</span></div></div></div>:<div className="two-col"><div className="panel"><div className="panel-head"><div><h2>New transfer</h2><p>Transfer between two active accounts</p></div><div className="round-icon"><ArrowLeftRight/></div></div><form className="form" onSubmit={e=>{e.preventDefault();doTransfer()}}><Field label="From account"><select value={transfer.sourceAccountId} onChange={e=>setTransfer({...transfer,sourceAccountId:e.target.value})} required><option value="">Select source account</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_number} · {money(a.balance)}</option>)}</select></Field><Field label="Recipient account number"><input inputMode="numeric" value={transfer.destinationAccountId} onChange={e=>setTransfer({...transfer,destinationAccountId:e.target.value})} placeholder="Enter the recipient account number" required/></Field><Field label="Amount (₹)"><input type="number" min="1" step="0.01" value={transfer.amount} onChange={e=>setTransfer({...transfer,amount:e.target.value})} required/></Field><div className="info-box"><Activity size={18}/><span>Transfers require a one-time code sent to your registered email. Do not submit again while a request is pending.</span></div><button type="button" className="secondary" disabled={busy||role!=='CUSTOMER'} onClick={requestTransferOtp}>{transferOtpSent?'Resend transfer OTP':'Send transfer OTP to email'}</button>{transferOtpSent&&<Field label="Email transfer OTP (6 digits)"><input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={transferOtp} onChange={e=>setTransferOtp(e.target.value.replace(/\D/g,'').slice(0,6))} required/></Field>}<button className="primary" disabled={busy||role!=='CUSTOMER'||accounts.length<1||!transfer.sourceAccountId||!transfer.destinationAccountId.trim()||!transferOtpSent||transferOtp.length!==6}><ArrowLeftRight size={17}/> Start transfer workflow</button>{role!=='CUSTOMER'&&<small className="help">Only customers can initiate normal transfers. Admins have a separate test runner.</small>}</form></div><div className="panel"><div className="panel-head"><div><h2>How Saga works</h2><p>Persisted, inspectable transaction stages</p></div></div><div className="saga-steps"><Step n="01" title="Validate" text="Destination, account state, minimum balance and daily limit"/><Step n="02" title="Debit source" text="Record the source account debit"/><Step n="03" title="Credit destination" text="Attempt destination posting"/><Step n="04" title="Compensate if needed" text="Restore source funds or escalate unresolved recovery"/><Step n="05" title="Record outcome" text="SUCCESS, COMPENSATED or REQUIRES_REVIEW"/></div></div></div>}</>}
  {tab==='Transactions'&&<><div className="section-intro"><div><h2>Transaction history</h2><p>Open any record to inspect the full event timeline.</p></div><button className="secondary" onClick={load}><RefreshCw size={15}/> Refresh</button></div><div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Transaction</th><th>Reference</th><th>Amount</th><th>Status</th><th>Created</th><th></th></tr></thead><tbody>{txns.map(t=><tr key={t.id}><td><b>{t.txn_type==='DEPOSIT'?'Deposit request':'Internal transfer'}</b><small>{t.description}</small></td><td className="mono">{t.reference_no}</td><td className="amount">{money(t.amount)}</td><td><span className={statusClass(t.status)}>{t.status}</span></td><td>{fmtDate(t.created_at)}</td><td><div className="queue-actions"><button className="detailbtn" onClick={()=>openTxn(t)}>Timeline <ChevronRight size={14}/></button></div></td></tr>)}</tbody></table>{txns.length===0&&<Empty text="No transaction records yet."/>}</div></div>{selected&&<div className="panel timeline-panel"><div className="panel-head"><div><h2>Transaction timeline</h2><p>{selected.reference_no} · {selected.txn_type} · {money(selected.amount)}</p></div><button className="iconbtn" onClick={()=>{setSelected(null);setEvents([])}}>×</button></div><div className="timeline-summary"><div><small>Current status</small><span className={statusClass(selected.status)}>{selected.status}</span></div><div><small>Created</small><b>{fmtDate(selected.created_at)}</b></div><div><small>Source / destination</small><b>{selected.source_account_id||'—'} → {selected.destination_account_id||'—'}</b></div></div><div className="timeline">{events.map((ev,i)=><div className="timeline-item" key={ev.id}><div className={'timeline-marker '+(ev.status==='SUCCESS'?'good':ev.status==='COMPENSATED'?'warn':ev.status==='FAILED'||ev.status==='VALIDATION_FAILED'||ev.status==='CREDIT_FAILED'||ev.status==='REQUIRES_REVIEW'?'bad':'')}>{ev.status==='SUCCESS'?<CheckCircle2 size={16}/>:ev.status==='FAILED'?<XCircle size={16}/>:<Activity size={16}/>}</div><div className="timeline-body"><div className="timeline-title"><b>{ev.title}</b><span className={statusClass(ev.status)}>{ev.status}</span></div><p>{ev.details}</p><small>{fmtDate(ev.created_at)}</small></div></div>)}</div>{selected.status==='REQUIRES_REVIEW'&&isStaff&&<button className="primary" disabled={busy} onClick={()=>act(()=>request('/transactions/'+selected.id+'/resolve-review',{method:'POST'}),'Manual recovery completed. Source funds restored and compensation recorded.').then(()=>openTxn(selected))}><ShieldCheck size={17}/> Resolve investigation &amp; restore source funds</button>}</div>}</>}
 {tab==='Fixed deposits'&&<><div className="section-intro"><div><h2>Fixed deposits</h2><p>Lock funds for a selected term and receive estimated simple interest at maturity.</p></div></div><div className="two-col"><div className="panel"><h2>Open fixed deposit</h2><form className="form" onSubmit={e=>{e.preventDefault();act(()=>request('/fixed-deposits',{method:'POST',body:JSON.stringify({accountId:Number(fdForm.accountId),amount:fdForm.amount,tenureMonths:Number(fdForm.tenureMonths)})}),'Fixed deposit opened.').then(()=>setFdForm({...fdForm,amount:''}))}}><Field label="Fund from account"><select value={fdForm.accountId} onChange={e=>setFdForm({...fdForm,accountId:e.target.value})} required><option value="">Select account</option>{accounts.filter(a=>a.owner_user_id===user?.id).map(a=><option key={a.id} value={a.id}>{a.account_number} · {money(a.balance)}</option>)}</select></Field><Field label="Principal amount (₹)"><input type="number" min="1" step="0.01" value={fdForm.amount} onChange={e=>setFdForm({...fdForm,amount:e.target.value})} required/></Field><Field label="Tenure"><select value={fdForm.tenureMonths} onChange={e=>setFdForm({...fdForm,tenureMonths:e.target.value})}><option value="3">3 months</option><option value="6">6 months</option><option value="12">12 months</option><option value="24">24 months</option><option value="36">36 months</option><option value="60">60 months</option></select></Field><button className="primary" disabled={busy||role!=='CUSTOMER'||!fdForm.accountId}>Open fixed deposit</button></form></div><div className="panel table-panel"><h2>Your fixed deposits</h2><div className="table-scroll"><table><thead><tr><th>Reference</th><th>Principal</th><th>Tenure</th><th>Maturity</th><th>Status</th><th></th></tr></thead><tbody>{fixedDeposits.map(fd=><tr key={fd.id}><td>{fd.reference_no}</td><td>{money(fd.principal)}</td><td>{fd.tenure_months} months</td><td>{fd.maturity_date}</td><td>{fd.status}</td><td>{fd.status==='ACTIVE'&&<button className="secondary" disabled={busy} onClick={()=>act(()=>request('/fixed-deposits/'+fd.id+'/close',{method:'POST'}),'Maturity payout processed.')}>Mature / close</button>}</td></tr>)}</tbody></table>{fixedDeposits.length===0&&<Empty text="No fixed deposits yet."/>}</div></div></div><div className="info-box"><ShieldCheck size={18}/><span>Educational fixed deposit model: 6.5% simple annual interest, maturity-only closure. Not a real bank rate or a production financial product.</span></div></>}
  {tab==='Loans'&&<><div className="section-intro"><div><h2>Loans</h2><p>Submit a loan request; a branch manager or admin reviews it before any disbursement.</p></div></div><div className="two-col"><div className="panel"><h2>Apply for a loan</h2><form className="form" onSubmit={e=>{e.preventDefault();act(()=>request('/loans',{method:'POST',body:JSON.stringify({accountId:Number(loanForm.accountId),amount:loanForm.amount,purpose:loanForm.purpose,monthlyIncome:loanForm.monthlyIncome})}),'Loan application submitted for review.').then(()=>setLoanForm({...loanForm,amount:'',purpose:'',monthlyIncome:''}))}}><Field label="Credit destination account"><select value={loanForm.accountId} onChange={e=>setLoanForm({...loanForm,accountId:e.target.value})} required><option value="">Select account</option>{accounts.filter(a=>a.owner_user_id===user?.id).map(a=><option key={a.id} value={a.id}>{a.account_number}</option>)}</select></Field><Field label="Loan amount (₹5,000–₹10,00,000)"><input type="number" min="5000" max="1000000" value={loanForm.amount} onChange={e=>setLoanForm({...loanForm,amount:e.target.value})} required/></Field><Field label="Monthly income (₹)"><input type="number" min="1" value={loanForm.monthlyIncome} onChange={e=>setLoanForm({...loanForm,monthlyIncome:e.target.value})} required/></Field><Field label="Purpose (10+ characters)"><textarea minLength={10} value={loanForm.purpose} onChange={e=>setLoanForm({...loanForm,purpose:e.target.value})} required/></Field><button className="primary" disabled={busy||role!=='CUSTOMER'||!loanForm.accountId}>Submit loan application</button></form></div><div className="panel table-panel"><h2>Loan applications</h2><div className="table-scroll"><table><thead><tr><th>ID</th><th>Amount</th><th>Purpose</th><th>Status</th><th>Action</th></tr></thead><tbody>{loans.map(l=><tr key={l.id}><td>LN-{l.id}</td><td>{money(l.amount)}</td><td>{l.purpose}</td><td>{l.status}</td><td>{isStaff&&l.status==='PENDING_REVIEW'&&<div className="queue-actions"><button className="approve" disabled={busy} onClick={()=>act(()=>request('/loans/'+l.id+'/approve',{method:'POST',body:JSON.stringify({reason:'Approved after branch review'})}),'Loan approved and disbursed.')}>Approve &amp; disburse</button><button className="reject" disabled={busy} onClick={()=>act(()=>request('/loans/'+l.id+'/reject',{method:'POST',body:JSON.stringify({reason:'Did not meet review requirements'})}),'Loan rejected.')}>Reject</button></div>}</td></tr>)}</tbody></table>{loans.length===0&&<Empty text="No loan applications yet."/>}</div></div></div><div className="info-box warning"><AlertTriangle size={18}/><span>Educational loan workflow only. No EMI schedule, interest amortization, credit scoring or regulated lending compliance is implemented.</span></div></>}
  {tab==='Applications'&&<><div className="section-intro"><div><h2>Account application queue</h2><p>Review account applications before an account is created and activated.</p></div><span className="pill">{summary.pendingApplications||0} pending</span></div><div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Applicant</th><th>Product</th><th>Initial deposit</th><th>Status</th><th>Submitted</th><th>Review action</th></tr></thead><tbody>{apps.map(a=><tr key={a.id}><td><b>{a.customer_name}</b><small>{a.reason}</small></td><td>{a.account_type}</td><td>{money(a.initial_deposit)}</td><td><span className={statusClass(a.status)}>{a.status}</span></td><td>{fmtDate(a.created_at)}</td><td>{isStaff&&(a.status==='PENDING_REVIEW'||a.status==='VERIFIED')?<div className="queue-actions">{role==='EMPLOYEE'&&a.status==='PENDING_REVIEW'&&<button className="approve" disabled={busy} onClick={()=>act(()=>request('/applications/'+a.id+'/verify',{method:'POST'}),'Employee verification complete; manager approval required.')}>Verify</button>}{['MANAGER','ADMIN'].includes(role)&&(a.status==='VERIFIED'||role==='ADMIN'&&a.status==='PENDING_REVIEW')&&<button className="approve" disabled={busy} onClick={()=>act(()=>request('/applications/'+a.id+'/approve',{method:'POST'}),'Application approved; account activated.')}>Approve</button>}<button className="reject" disabled={busy} onClick={()=>act(()=>request('/applications/'+a.id+'/reject',{method:'POST',body:JSON.stringify({reason:'Did not meet review requirements'})}),'Application rejected.')}>Reject</button></div>:a.status==='PENDING_REVIEW'||a.status==='VERIFIED'?<span className="muted">Staff review required</span>:<span className="muted">{a.account_id?'Account #'+a.account_id:'Reviewed'}</span>}</td></tr>)}</tbody></table>{apps.length===0&&<Empty text="No applications yet. Submit one from Accounts."/>}</div></div></>}
 {tab==='Staff access'&&role==='ADMIN'&&<><div className="section-intro"><div><h2>Staff access management</h2><p>Create named employee and branch-manager logins. Passwords are stored as BCrypt hashes.</p></div></div><div className="panel"><form className="form" onSubmit={e=>{e.preventDefault();act(()=>request('/auth/users',{method:'POST',body:JSON.stringify(staffForm)}),'Staff account created. Share credentials securely.').then(()=>setStaffForm({fullName:'',email:'',password:'',role:'EMPLOYEE',branchName:'Main Branch'}))}}><Field label="Full name"><input value={staffForm.fullName} onChange={e=>setStaffForm({...staffForm,fullName:e.target.value})} required/></Field><Field label="Work email"><input type="email" value={staffForm.email} onChange={e=>setStaffForm({...staffForm,email:e.target.value})} required/></Field><Field label="Temporary password (10+ characters, letters and numbers)"><input type="password" minLength={10} value={staffForm.password} onChange={e=>setStaffForm({...staffForm,password:e.target.value})} required/></Field><Field label="Assigned branch"><select value={staffForm.branchName} onChange={e=>setStaffForm({...staffForm,branchName:e.target.value})} required><option>Main Branch</option><option>Guntur Branch</option><option>Vijayawada Branch</option><option>Amaravati Branch</option><option>Visakhapatnam Branch</option><option>Hyderabad Branch</option></select></Field><Field label="Role"><select value={staffForm.role} onChange={e=>setStaffForm({...staffForm,role:e.target.value})}><option value="EMPLOYEE">Employee</option><option value="MANAGER">Branch Manager</option></select></Field><button className="primary" disabled={busy}>Create staff login <ChevronRight size={17}/></button></form></div></>}
 <footer><span>Northstar Bank · Online banking portal</span><span><ShieldCheck size={14}/> Educational application · Not for real financial transactions</span></footer></main></div>
}
function Stat({icon,label,value,sub}:{icon:any,label:string,value:any,sub:string}){return <div className="stat"><div className="stat-icon">{icon}</div><div><small>{label}</small><strong>{value}</strong><span>{sub}</span></div></div>}
function Field({label,children}:{label:string,children:any}){return <label className="field"><span>{label}</span>{children}</label>}
function Rule({title,value}:{title:string,value:string}){return <div className="rule"><span>{title}</span><b>{value}</b></div>}
function Step({n,title,text}:{n:string,title:string,text:string}){return <div className="saga-step"><div>{n}</div><section><b>{title}</b><small>{text}</small></section><ChevronRight size={16}/></div>}
function Empty({text}:{text:string}){return <div className="empty"><FileText size={23}/><span>{text}</span></div>}
