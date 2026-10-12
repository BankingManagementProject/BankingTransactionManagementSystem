import { useCallback, useEffect, useState } from 'react';
import {
  Activity, ArrowDownLeft, ArrowLeftRight, Banknote, CheckCircle2, ChevronRight,
  Clock3, FileText, LayoutDashboard, RefreshCw, ShieldCheck, Users, Wallet,
  XCircle, AlertTriangle, ClipboardCheck, Landmark, Bell, UserPlus, Download,
  Check, ShieldAlert, Sliders, Plus
} from 'lucide-react';

type Row = Record<string, any>;
const money = (v: any) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(v || 0));
const statusClass = (s: string) => 'status ' + (s || '').toLowerCase().replaceAll('_', '-');
const fmtDate = (s: string) => {
  if (!s) return '—';
  const str = String(s).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) {
    const [y, m, d] = str.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }
  let iso = str;
  if (/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}/.test(str)) {
    iso = str.replace(' ', 'T') + 'Z';
  } else if (!str.endsWith('Z') && !str.includes('+') && !str.includes('T')) {
    iso = str.replace(' ', 'T') + 'Z';
  } else if (str.includes('T') && !str.endsWith('Z') && !str.includes('+') && !str.slice(10).includes('-')) {
    iso = str + 'Z';
  }
  const date = new Date(iso);
  if (isNaN(date.getTime())) return str;
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  });
};

export default function App() {
  const [googleClientId, setGoogleClientId] = useState<string>(() => {
    return (import.meta as any).env?.VITE_GOOGLE_CLIENT_ID || localStorage.getItem('northstar_google_client_id') || '';
  });
  const [showGoogleConfig, setShowGoogleConfig] = useState(false);
  const [showDirectGoogleModal, setShowDirectGoogleModal] = useState(false);
  const [clientIdInput, setClientIdInput] = useState('');
  const [directGoogleEmail, setDirectGoogleEmail] = useState('');

  // Authentication
  const [authToken, setAuthToken] = useState(() => localStorage.getItem('northstar_token') || '');
  const [user, setUser] = useState<Row | null>(() => {
    try { return JSON.parse(localStorage.getItem('northstar_user') || 'null'); } catch { return null; }
  });
  const [authMode, setAuthMode] = useState<'LOGIN' | 'REGISTER' | 'BOOTSTRAP'>('LOGIN');
  const [authForm, setAuthForm] = useState({ fullName: '', email: '', password: '', bootstrapSecret: '' });
  const [authError, setAuthError] = useState('');
  const [authMessage, setAuthMessage] = useState('');
  const [authBusy, setAuthBusy] = useState(false);

  const role = String(user?.role || 'CUSTOMER').toUpperCase();
  const isStaff = ['STAFF', 'EMPLOYEE', 'MANAGER', 'ADMIN'].includes(role);
  const isManager = ['MANAGER', 'ADMIN'].includes(role);
  const isAdmin = role === 'ADMIN';

  // Navigation tab
  const [tab, setTab] = useState('Overview');

  // Shared Data
  const [accounts, setAccounts] = useState<Row[]>([]);
  const [apps, setApps] = useState<Row[]>([]);
  const [txns, setTxns] = useState<Row[]>([]);
  const [events, setEvents] = useState<Row[]>([]);
  const [selected, setSelected] = useState<Row | null>(null);
  const [summary, setSummary] = useState<Row>({});
  const [fixedDeposits, setFixedDeposits] = useState<Row[]>([]);
  const [loans, setLoans] = useState<Row[]>([]);
  const [beneficiaries, setBeneficiaries] = useState<Row[]>([]);
  const [complaints, setComplaints] = useState<Row[]>([]);
  const [notifications, setNotifications] = useState<Row[]>([]);
  const [approvals, setApprovals] = useState<Row[]>([]);
  const [usersList, setUsersList] = useState<Row[]>([]);
  const [auditLogs, setAuditLogs] = useState<Row[]>([]);
  const [systemConfig, setSystemConfig] = useState<Row>({});

  // UI state & Modals
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [rejectionModal, setRejectionModal] = useState<{ open: boolean; targetId: number | null; targetType: 'TRANSACTION' | 'APPLICATION' | 'DEPOSIT' | 'LOAN'; reason: string }>({
    open: false, targetId: null, targetType: 'TRANSACTION', reason: ''
  });
  const [statementData, setStatementData] = useState<Row | null>(null);
  const [selectedStatementAcc, setSelectedStatementAcc] = useState('');
  const [complaintModal, setComplaintModal] = useState(false);
  const [complaintForm, setComplaintForm] = useState({ accountNumber: '', category: 'TRANSACTION', subject: '', description: '' });
  const [replyModal, setReplyModal] = useState<{ open: boolean; ticketId: number | null; notes: string; status: string }>({ open: false, ticketId: null, notes: '', status: 'IN_PROGRESS' });
  const [beneficiaryModal, setBeneficiaryModal] = useState(false);
  const [beneficiaryForm, setBeneficiaryForm] = useState({ accountNumber: '', beneficiaryName: '', nickname: '' });

  // Forms
  const [showNewApp, setShowNewApp] = useState(false);
  const [deposit, setDeposit] = useState({ accountId: '', amount: '', description: '' });
  const [application, setApplication] = useState({ accountType: 'SAVINGS', initialDeposit: '1000', phone: '', dateOfBirth: '', address: '', occupation: '', branchName: 'Main Branch', reason: 'New account application' });
  const [transfer, setTransfer] = useState({ sourceAccountId: '', destinationAccountId: '', amount: '', demoOutcome: 'SUCCESS', description: '' });
  const [transferOtp, setTransferOtp] = useState('');
  const [transferOtpSent, setTransferOtpSent] = useState(false);
  const [fdForm, setFdForm] = useState({ accountId: '', amount: '', tenureMonths: '12' });
  const [loanForm, setLoanForm] = useState({ accountId: '', amount: '', purpose: '', monthlyIncome: '' });
  const [staffForm, setStaffForm] = useState({ fullName: '', email: '', password: '', role: 'STAFF', branchName: 'Main Branch' });
  const [staffOnboard, setStaffOnboard] = useState({ fullName: '', email: '', phone: '', dateOfBirth: '', address: '', occupation: '', accountType: 'SAVINGS', initialDeposit: '1000', branchName: 'Main Branch' });
  const [configForm, setConfigForm] = useState({ approvalThreshold: '20000', dailyLimit: '50000', singleLimit: '100000', minBalance: '1000' });
  const [txnFilterStatus, setTxnFilterStatus] = useState('ALL');

  // Fetch Google Client ID from backend
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

  // Initialize Google Identity Services
  useEffect(() => {
    if (!googleClientId || authToken) return;
    let tries = 0;
    const timer = setInterval(() => {
      tries++;
      const g = (window as any).google;
      if (!g?.accounts?.id) {
        if (tries > 30) clearInterval(timer);
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
      } catch (err) {
        console.warn('GIS initialize note:', err);
      }
    }, 250);
    return () => clearInterval(timer);
  }, [googleClientId, authMode, authToken]);

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

  const handleDirectGoogleLogin = async (e: any) => {
    e.preventDefault();
    if (!directGoogleEmail.trim()) return;
    setAuthBusy(true);
    setAuthError('');
    try {
      const res = await fetch('/api/auth/google-direct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: directGoogleEmail.trim() })
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || d.message || 'Direct Google login failed');
      localStorage.setItem('northstar_token', d.accessToken);
      localStorage.setItem('northstar_user', JSON.stringify(d.user));
      setAuthToken(d.accessToken);
      setUser(d.user);
      setShowDirectGoogleModal(false);
      setTab('Overview');
      setNotice('Signed in via Google identity.');
    } catch (err: any) {
      setAuthError(err.message);
    } finally {
      setAuthBusy(false);
    }
  };

  // Authenticated API request helper
  const request = useCallback(async (path: string, opts: RequestInit = {}) => {
    const res = await fetch('/api' + path, {
      ...opts,
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { Authorization: 'Bearer ' + authToken } : {}),
        ...opts.headers
      }
    });
    const data = await res.json().catch(() => ({ message: 'Unexpected server response' }));
    if (res.status === 401 && authToken) {
      localStorage.removeItem('northstar_token');
      localStorage.removeItem('northstar_user');
      setAuthToken('');
      setUser(null);
    }
    if (!res.ok) throw new Error(data.message || data.detail || data.error || 'Request failed');
    return data;
  }, [authToken]);

  // Load authoritative data from backend based on role
  const load = useCallback(async () => {
    try {
      const [a, ap, t, s, fd, lo, comp, notif] = await Promise.all([
        request('/accounts').catch(() => []),
        request('/applications').catch(() => []),
        request('/transactions').catch(() => []),
        request('/summary').catch(() => ({})),
        request('/fixed-deposits').catch(() => []),
        request('/loans').catch(() => []),
        request('/complaints').catch(() => []),
        request('/notifications/my').catch(() => [])
      ]);
      setAccounts(a);
      setApps(ap);
      setTxns(t);
      setSummary(s);
      setFixedDeposits(fd);
      setLoans(lo);
      setComplaints(comp);
      setNotifications(notif);

      if (role === 'CUSTOMER') {
        const b = await request('/beneficiaries').catch(() => []);
        setBeneficiaries(b);
      }
      if (isManager) {
        const [apprs, uList] = await Promise.all([
          request('/transactions/approvals').catch(() => []),
          request('/auth/users').catch(() => [])
        ]);
        setApprovals(apprs);
        setUsersList(uList);
      }
      if (isAdmin) {
        const [uList, logs, cfg] = await Promise.all([
          request('/auth/users').catch(() => []),
          request('/transactions/audit-logs').catch(() => []),
          request('/transactions/config').catch(() => ({}))
        ]);
        setUsersList(uList);
        setAuditLogs(logs);
        setSystemConfig(cfg);
        if (cfg.approval_threshold) {
          setConfigForm({
            approvalThreshold: cfg.approval_threshold,
            dailyLimit: cfg.daily_limit || '50000',
            singleLimit: cfg.single_limit || '100000',
            minBalance: cfg.min_balance || '1000'
          });
        }
      }
    } catch (e: any) {
      setError(e.message || 'Error fetching banking data.');
    }
  }, [request, role, isManager, isAdmin]);

  useEffect(() => {
    if (!authToken) return;
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [load, authToken]);

  useEffect(() => {
    if (accounts.length === 0) {
      setDeposit(v => ({ ...v, accountId: '' }));
      setTransfer(v => ({ ...v, sourceAccountId: '' }));
      return;
    }
    setDeposit(v => ({ ...v, accountId: accounts.some(a => String(a.id) === v.accountId) ? v.accountId : String(accounts[0].id) }));
    setTransfer(v => ({ ...v, sourceAccountId: accounts.some(a => String(a.id) === v.sourceAccountId) ? v.sourceAccountId : String(accounts[0].id) }));
    if (!selectedStatementAcc && accounts.length > 0) {
      setSelectedStatementAcc(accounts[0].account_number);
      loadStatement(accounts[0].account_number);
    }
  }, [accounts, selectedStatementAcc]);

  const act = async (fn: () => Promise<any>, success?: string) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const r = await fn();
      setNotice(success || r.message || 'Operation completed successfully.');
      await load();
      return r;
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const openTxn = async (t: Row) => {
    setSelected(t);
    setEvents([]);
    try {
      const [latest, ev] = await Promise.all([
        request('/transactions'),
        request('/transactions/' + t.id + '/events')
      ]);
      setSelected(latest.find((x: Row) => x.id === t.id) || t);
      setEvents(ev);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const doDeposit = () => act(
    () => request('/deposits', { method: 'POST', body: JSON.stringify({ accountId: Number(deposit.accountId), amount: Number(deposit.amount) }) }),
    'Deposit request submitted. Awaiting authorized approval.'
  ).then(() => setTab('Transactions'));

  const requestTransferOtp = () => act(
    () => request('/notifications/transfer-otp', { method: 'POST' }),
    'Transfer OTP sent to your registered email & in-app security notifications.'
  ).then((r: any) => {
    setTransferOtpSent(true);
    if (r?.demoOtp) setTransferOtp(r.demoOtp);
  });

  const doTransfer = () => act(
    () => request('/transfers', {
      method: 'POST',
      body: JSON.stringify({
        sourceAccountId: Number(transfer.sourceAccountId),
        destinationAccountNumber: transfer.destinationAccountId.trim(),
        amount: Number(transfer.amount),
        otp: transferOtp,
        description: transfer.description || 'Fund transfer'
      })
    })
  ).then((r: any) => {
    if (r?.status === 'PENDING_APPROVAL') {
      setNotice(`High-value transfer ${r.reference_no} submitted for Branch Manager review and approval.`);
    } else if (r?.status === 'VALIDATION_FAILED') {
      setNotice(r.description || 'Transfer stopped during validation. No funds were moved.');
    } else if (r?.status === 'SUCCESS') {
      setNotice('Transfer completed successfully. Open timeline to inspect recorded Saga stages.');
    }
    setTransferOtp('');
    setTransferOtpSent(false);
    setTab('Transactions');
  });

  const loadStatement = async (accNum: string) => {
    if (!accNum) return;
    try {
      setBusy(true);
      const data = await request('/statements/' + accNum);
      setStatementData(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleUserStatus = (uid: number, currentStatus: string) => {
    const nextStatus = currentStatus === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    act(() => request(`/auth/users/${uid}/status`, { method: 'PUT', body: JSON.stringify({ status: nextStatus }) }), `User status updated to ${nextStatus}.`);
  };

  const saveConfig = () => {
    act(() => request('/transactions/config', {
      method: 'POST',
      body: JSON.stringify({
        approvalThreshold: Number(configForm.approvalThreshold),
        dailyLimit: Number(configForm.dailyLimit),
        singleLimit: Number(configForm.singleLimit),
        minBalance: Number(configForm.minBalance)
      })
    }), 'System transaction policies updated successfully.');
  };

  const handleManagerDecision = (id: number, approve: boolean) => {
    if (approve) {
      act(() => request(`/transactions/${id}/approve`, { method: 'POST' }), 'Transfer approved and executed.');
    } else {
      setRejectionModal({ open: true, targetId: id, targetType: 'TRANSACTION', reason: '' });
    }
  };

  const submitRejection = () => {
    if (!rejectionModal.targetId) return;
    const { targetId, targetType, reason } = rejectionModal;
    if (targetType === 'TRANSACTION') {
      act(() => request(`/transactions/${targetId}/reject`, { method: 'POST', body: JSON.stringify({ reason: reason || 'Rejected by Branch Manager during review' }) }), 'Transfer rejected. Decisions & reason recorded.');
    } else if (targetType === 'APPLICATION') {
      act(() => request(`/applications/${targetId}/reject`, { method: 'POST', body: JSON.stringify({ reason: reason || 'Application rejected' }) }), 'Application rejected.');
    } else if (targetType === 'DEPOSIT') {
      act(() => request(`/deposits/${targetId}/reject`, { method: 'POST', body: JSON.stringify({ reason: reason || 'Deposit rejected' }) }), 'Deposit rejected.');
    } else if (targetType === 'LOAN') {
      act(() => request(`/loans/${targetId}/reject`, { method: 'POST', body: JSON.stringify({ reason: reason || 'Loan rejected' }) }), 'Loan rejected.');
    }
    setRejectionModal({ open: false, targetId: null, targetType: 'TRANSACTION', reason: '' });
  };

  const logout = () => {
    localStorage.removeItem('northstar_token');
    localStorage.removeItem('northstar_user');
    setAuthToken('');
    setUser(null);
    setTab('Overview');
  };

  // Build role-tailored navigation items
  const navItems = (() => {
    if (isAdmin) {
      return [
        ['Overview', LayoutDashboard],
        ['User Management', Users],
        ['Customer Accounts', Landmark],
        ['Transaction Monitor', Activity],
        ['System Policies', Sliders],
        ['Audit Logs', FileText],
        ['Saga Test Runner', ArrowLeftRight]
      ] as const;
    }
    if (role === 'MANAGER') {
      return [
        ['Overview', LayoutDashboard],
        ['Approval Queue', ClipboardCheck],
        ['Account Applications', Wallet],
        ['Branch Accounts', Landmark],
        ['Deposit Requests', ArrowDownLeft],
        ['Loan Approvals', Banknote],
        ['Transactions', Activity],
        ['Customer Complaints', AlertTriangle],
        ['Staff Monitoring', Users]
      ] as const;
    }
    if (role === 'STAFF' || role === 'EMPLOYEE') {
      return [
        ['Overview', LayoutDashboard],
        ['Customer Onboarding', UserPlus],
        ['Applications Queue', ClipboardCheck],
        ['Deposit Requests', ArrowDownLeft],
        ['Customer Support', AlertTriangle],
        ['Branch Accounts', Landmark],
        ['Transactions', Activity]
      ] as const;
    }
    // CUSTOMER
    return [
      ['Overview', LayoutDashboard],
      ['My Accounts', Wallet],
      ['Deposit Requests', ArrowDownLeft],
      ['Transfer Money', ArrowLeftRight],
      ['Beneficiaries', Users],
      ['Transactions', Activity],
      ['Account Statements', FileText],
      ['Help & Support', AlertTriangle],
      ['Notifications', Bell],
      ['Fixed Deposits', Banknote],
      ['Loans', FileText]
    ] as const;
  })();

  // ---------------- Authentication Screen ----------------
  if (!authToken) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <div className="brand auth-brand">
            <div className="brandmark"><Landmark size={24} /></div>
            <div><b>northstar</b><small> DIGITAL BANK</small></div>
          </div>
          <h1>{authMode === 'LOGIN' ? 'Secure sign in' : authMode === 'REGISTER' ? 'Open customer account' : 'System bootstrap'}</h1>
          <p className="auth-subtitle">
            {authMode === 'LOGIN'
              ? 'Role-based access control with multi-tier authorization and auditable transaction processing.'
              : authMode === 'REGISTER'
                ? 'Register your customer banking profile. Manager verification is required before full activation.'
                : 'Initialize first bank administrator credentials.'}
          </p>

          {authError && <div className="notice error"><AlertTriangle size={16} />{authError}</div>}
          {authMessage && <div className="notice success"><CheckCircle2 size={16} />{authMessage}</div>}

          {/* Google Sign In Section for Customers */}
          {authMode !== 'BOOTSTRAP' && (
            <div style={{ marginBottom: '16px' }}>
              <div id="google-signin-btn-slot" style={{ display: 'flex', justifyContent: 'center', minHeight: '44px' }} />
              <button
                type="button"
                className="google-btn"
                style={{ marginTop: '8px' }}
                onClick={() => setShowDirectGoogleModal(true)}
                disabled={authBusy}
              >
                <svg width="18" height="18" viewBox="0 0 48 48">
                  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
                  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
                  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
                </svg>
                <span>Direct Google Account Sign-In</span>
              </button>
              <div className="auth-divider"><span>or continue with email &amp; password</span></div>
            </div>
          )}

          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            setAuthBusy(true);
            setAuthError('');
            setAuthMessage('');
            try {
              if (authMode === 'LOGIN') {
                const res = await fetch('/api/auth/login', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ email: authForm.email, password: authForm.password })
                });
                const d = await res.json();
                if (!res.ok) throw new Error(d.message || d.detail || 'Sign in failed');
                localStorage.setItem('northstar_token', d.accessToken);
                localStorage.setItem('northstar_user', JSON.stringify(d.user));
                setAuthToken(d.accessToken);
                setUser(d.user);
              } else if (authMode === 'REGISTER') {
                const res = await fetch('/api/auth/register', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ fullName: authForm.fullName, email: authForm.email, password: authForm.password })
                });
                const d = await res.json();
                if (!res.ok) throw new Error(d.message || d.detail || 'Registration failed');
                localStorage.setItem('northstar_token', d.accessToken);
                localStorage.setItem('northstar_user', JSON.stringify(d.user));
                setAuthToken(d.accessToken);
                setUser(d.user);
              } else if (authMode === 'BOOTSTRAP') {
                const res = await fetch('/api/auth/bootstrap-admin', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ fullName: authForm.fullName, email: authForm.email, password: authForm.password, bootstrapSecret: authForm.bootstrapSecret })
                });
                const d = await res.json();
                if (!res.ok) throw new Error(d.message || d.detail || 'Bootstrap failed');
                setAuthMessage('Admin created. Please sign in now.');
                setAuthMode('LOGIN');
              }
            } catch (err: any) {
              setAuthError(err.message);
            } finally {
              setAuthBusy(false);
            }
          }}>
            {authMode !== 'LOGIN' && (
              <label className="field">
                <span>Full name</span>
                <input required value={authForm.fullName} onChange={e => setAuthForm({ ...authForm, fullName: e.target.value })} placeholder="Alex Morgan" />
              </label>
            )}
            <label className="field">
              <span>Email address</span>
              <input type="email" required value={authForm.email} onChange={e => setAuthForm({ ...authForm, email: e.target.value })} placeholder="user@northstar.local" />
            </label>
            <label className="field">
              <span>Password</span>
              <input type="password" required minLength={8} value={authForm.password} onChange={e => setAuthForm({ ...authForm, password: e.target.value })} placeholder="••••••••••••" />
            </label>
            {authMode === 'BOOTSTRAP' && (
              <label className="field">
                <span>Bootstrap Secret</span>
                <input type="password" required value={authForm.bootstrapSecret} onChange={e => setAuthForm({ ...authForm, bootstrapSecret: e.target.value })} placeholder="Configured bootstrap token" />
              </label>
            )}

            <button className="primary" style={{ marginTop: '8px' }} disabled={authBusy}>
              {authBusy ? 'Authenticating…' : authMode === 'LOGIN' ? 'Sign in to workspace' : authMode === 'REGISTER' ? 'Create Customer Account' : 'Initialize Administrator'} <ChevronRight size={17} />
            </button>
          </form>

          <div className="auth-links">
            {authMode === 'LOGIN' && (
              <>
                <button type="button" onClick={() => { setAuthMode('REGISTER'); setAuthError(''); }}>New customer? Register here</button>
                <button type="button" onClick={() => { setAuthMode('BOOTSTRAP'); setAuthError(''); }}>System bootstrap</button>
                <button type="button" onClick={() => setShowGoogleConfig(true)}>Configure Google OAuth</button>
              </>
            )}
            {authMode !== 'LOGIN' && (
              <button type="button" onClick={() => { setAuthMode('LOGIN'); setAuthError(''); }}>Back to sign in</button>
            )}
          </div>

          <div className="info-box" style={{ marginTop: '22px' }}>
            <ShieldCheck size={18} />
            <div>
              <b>Role-Based Seed Credentials:</b>
              <div style={{ marginTop: '4px', fontSize: '9px', lineHeight: '1.5' }}>
                • Admin: <code>admin@northstar.local</code> / <code>AdminPass1234</code><br />
                • Manager: <code>manager@northstar.local</code> / <code>ManagerPass1234</code><br />
                • Staff: <code>staff@northstar.local</code> / <code>StaffPass1234</code><br />
                • Customer: <code>customer@northstar.local</code> / <code>CustomerPass1234</code>
              </div>
            </div>
          </div>
        </div>

        {/* Direct Google Sign In Modal */}
        {showDirectGoogleModal && (
          <div className="modal-overlay" onClick={() => setShowDirectGoogleModal(false)}>
            <div className="modal-card" onClick={e => e.stopPropagation()}>
              <div className="modal-head">
                <h3>Direct Google Sign-In</h3>
                <button className="iconbtn" onClick={() => setShowDirectGoogleModal(false)}>×</button>
              </div>
              <p style={{ fontSize: '12px', color: '#64748b', marginBottom: '14px' }}>
                Enter your Google email address to sign in or register instantly as a verified customer.
              </p>
              <form onSubmit={handleDirectGoogleLogin}>
                <Field label="Google Email Address">
                  <input
                    type="email"
                    required
                    autoFocus
                    placeholder="e.g. yourname@gmail.com"
                    value={directGoogleEmail}
                    onChange={e => setDirectGoogleEmail(e.target.value)}
                  />
                </Field>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                  <button type="button" className="secondary" onClick={() => setShowDirectGoogleModal(false)}>Cancel</button>
                  <button type="submit" className="primary" disabled={authBusy}>Sign In with Google</button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Google OAuth Client ID Configuration Modal */}
        {showGoogleConfig && (
          <div className="modal-overlay" onClick={() => setShowGoogleConfig(false)}>
            <div className="modal-card" onClick={e => e.stopPropagation()}>
              <div className="modal-head">
                <h3>Google OAuth Web Client ID</h3>
                <button className="iconbtn" onClick={() => setShowGoogleConfig(false)}>×</button>
              </div>
              <p style={{ fontSize: '12px', color: '#64748b', marginBottom: '14px' }}>
                Configure your Google OAuth 2.0 Web Client ID to render the official one-tap button:
              </p>
              <form onSubmit={saveGoogleClientId}>
                <Field label="Client ID">
                  <input
                    placeholder="e.g. 123456-abcdef.apps.googleusercontent.com"
                    value={clientIdInput || googleClientId}
                    onChange={e => setClientIdInput(e.target.value)}
                    required
                  />
                </Field>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                  <button type="button" className="secondary" onClick={() => setShowGoogleConfig(false)}>Cancel</button>
                  <button type="submit" className="primary">Save Configuration</button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ---------------- Main Application Workspace ----------------
  return (
    <div className="shell">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brandmark"><Landmark size={22} /></div>
          <div><b>northstar</b><small> DIGITAL BANK</small></div>
        </div>

        <div className="profile">
          <div className="avatar">
            {role === 'ADMIN' ? 'SA' : role === 'MANAGER' ? 'BM' : isStaff ? 'ST' : 'CU'}
          </div>
          <div>
            <b>{role === 'ADMIN' ? 'System Admin' : role === 'MANAGER' ? 'Branch Manager' : isStaff ? 'Banking Staff' : 'Customer Workspace'}</b>
            <small>{role}{user?.branch ? ` · ${user.branch}` : ''}</small>
          </div>
        </div>

        <div className="navlabel">HIERARCHY · {role}</div>
        <nav>
          {navItems.map(([label, Icon]) => {
            const isApprovals = label === 'Approval Queue';
            const pendingCount = Number(summary.pendingApprovals || approvals.length);
            return (
              <button key={label} className={'navitem ' + (tab === label ? 'active' : '')} onClick={() => setTab(label)}>
                <Icon size={18} />
                <span>{label}</span>
                {isApprovals && pendingCount > 0 && <span className="badge-count">{pendingCount}</span>}
                {label === 'Deposit Requests' && Number(summary.pendingDeposits) > 0 && <i>{summary.pendingDeposits}</i>}
                {label === 'Notifications' && notifications.filter(n => !n.is_read).length > 0 && (
                  <span className="badge-count">{notifications.filter(n => !n.is_read).length}</span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <div className="secure">
            <ShieldCheck size={18} />
            <div><b>Role Enforcement</b><small>Level {role === 'ADMIN' ? '1: Admin' : role === 'MANAGER' ? '2: Manager' : isStaff ? '3: Staff' : '4: Customer'}</small></div>
          </div>
          <small className="buildtag">ENTERPRISE CORE · RBAC ENABLED</small>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">DIGITAL BANKING / {role} / {tab.toUpperCase()}</div>
            <h1>{tab === 'Overview' ? `Welcome, ${user?.fullName || user?.full_name}` : tab}</h1>
            <p>
              {role === 'ADMIN'
                ? 'System administration, user governance, operational policies, and audit logs.'
                : role === 'MANAGER'
                  ? 'Branch supervision, high-value transfer authorization, and complaint escalations.'
                  : isStaff
                    ? 'Customer onboarding, verification, and authorized banking services.'
                    : 'Manage your verified accounts, fund transfers, and financial statements.'}
            </p>
          </div>
          <div className="top-actions">
            <div className="signed-in">
              <b>{user?.fullName || user?.full_name || user?.email}</b>
              <small>{role} · authenticated</small>
            </div>
            <button className="iconbtn" title="Refresh data" onClick={load}><RefreshCw size={18} /></button>
            <button className="secondary" onClick={logout}>Sign out</button>
          </div>
        </header>

        {notice && <div className="notice success"><CheckCircle2 size={18} />{notice}<button onClick={() => setNotice('')}>×</button></div>}
        {error && <div className="notice error"><AlertTriangle size={18} />{error}<button onClick={() => setError('')}>×</button></div>}

        {/* ======================================================== */}
        {/* ==================== 1. OVERVIEW TAB =================== */}
        {/* ======================================================== */}
        {tab === 'Overview' && (
          <>
            <section className="hero">
              <div className="hero-copy">
                <div className="hero-kicker"><span className="live-dot" /> {role} WORKSPACE</div>
                <div className="hero-label">
                  {role === 'CUSTOMER' ? 'Total available balance' : 'Monitored Bank Accounts'}
                </div>
                <div className="hero-balance">
                  {role === 'CUSTOMER'
                    ? money(accounts.filter(a => a.status === 'ACTIVE').reduce((n, a) => n + Number(a.balance), 0))
                    : `${accounts.length} Accounts`}
                </div>
                <div className="hero-foot">
                  <span><CheckCircle2 size={15} /> Authoritative Microservices State</span>
                  <span>INR · Indian Rupee</span>
                </div>
              </div>
              <div className="hero-art">
                <div className="orbit orbit1" /><div className="orbit orbit2" />
                <div className="hero-emblem"><Landmark size={58} /></div>
                <div className="float-card">
                  <span>ORGANIZATIONAL ROLE</span>
                  <b><i /> Level {role === 'ADMIN' ? '1 (Admin)' : role === 'MANAGER' ? '2 (Manager)' : isStaff ? '3 (Staff)' : '4 (Customer)'}</b>
                </div>
              </div>
            </section>

            <section className="stats">
              <Stat icon={<Wallet />} label={role === 'CUSTOMER' ? 'Active accounts' : 'Total Accounts'} value={accounts.length} sub="Approved & monitored" />
              <Stat icon={<Clock3 />} label="Pending approvals" value={summary.pendingApprovals || approvals.length || 0} sub="Requires Manager review" />
              <Stat icon={<Activity />} label="Total transactions" value={summary.transactions || txns.length || 0} sub="Audited ledger activity" />
              <Stat icon={<AlertTriangle />} label="Complaints / Tickets" value={complaints.filter(c => c.status !== 'RESOLVED').length} sub="Customer service requests" />
            </section>

            <section className="content-grid">
              <div className="panel">
                <div className="panel-head">
                  <div><h2>{role === 'CUSTOMER' ? 'Your accounts' : 'Branch Accounts'}</h2><p>Balances and status</p></div>
                  <button className="textbtn" onClick={() => setTab(role === 'CUSTOMER' ? 'My Accounts' : (isAdmin ? 'Customer Accounts' : 'Branch Accounts'))}>View all <ChevronRight size={15} /></button>
                </div>
                <div className="account-list">
                  {accounts.length === 0 && <Empty text="No active accounts found in this scope." />}
                  {accounts.slice(0, 4).map((a, i) => (
                    <div className="account-row" key={a.id}>
                      <div className={'account-icon tone' + (i % 3)}><Landmark size={20} /></div>
                      <div className="account-info">
                        <b>{a.account_type === 'SAVINGS' ? 'Savings account' : 'Current account'}</b>
                        <small>•••• {String(a.account_number).slice(-4)} · {a.account_number}</small>
                        <small>Min balance {money(a.minimum_balance)} · Daily limit {money(a.daily_limit)}</small>
                      </div>
                      <div className="account-balance">
                        <b>{money(a.balance)}</b>
                        <span className={statusClass(a.status)}>{a.status}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel activity-panel">
                <div className="panel-head">
                  <div><h2>Recent activity</h2><p>Latest requests and status</p></div>
                  <button className="textbtn" onClick={() => setTab('Transactions')}>History <ChevronRight size={15} /></button>
                </div>
                <div className="recent-list">
                  {txns.slice(0, 5).map(t => (
                    <button className="recent-row" key={t.id} onClick={() => openTxn(t)}>
                      <div className="recent-icon"><Activity size={17} /></div>
                      <div className="recent-info">
                        <b>{t.txn_type === 'DEPOSIT' ? 'Deposit request' : t.txn_type === 'TRANSFER' ? 'Internal transfer' : 'Bank transaction'}</b>
                        <small>{t.reference_no} · {fmtDate(t.created_at)}</small>
                      </div>
                      <div className="recent-amount">
                        <b>{money(t.amount)}</b>
                        <span className={statusClass(t.status)}>{t.status}</span>
                      </div>
                    </button>
                  ))}
                  {txns.length === 0 && <Empty text="No transaction records yet." />}
                </div>
              </div>
            </section>
          </>
        )}

        {/* ======================================================== */}
        {/* ==================== 2. ADMIN MODULES ================== */}
        {/* ======================================================== */}
        {isAdmin && tab === 'User Management' && (
          <>
            <div className="section-intro">
              <div><h2>User &amp; Identity Management</h2><p>Create Manager, Staff, and Customer logins; toggle active/inactive status; assign roles.</p></div>
              <span className="pill">{usersList.length} total users</span>
            </div>
            <div className="two-col">
              <div className="panel">
                <div className="panel-head"><div><h2>Create Bank User</h2><p>Add Manager, Staff or Customer</p></div></div>
                <form className="form" onSubmit={e => {
                  e.preventDefault();
                  act(() => request('/auth/users', { method: 'POST', body: JSON.stringify(staffForm) }), `Account created for ${staffForm.email}`).then(() => {
                    setStaffForm({ fullName: '', email: '', password: '', role: 'STAFF', branchName: 'Main Branch' });
                  });
                }}>
                  <Field label="Full name"><input value={staffForm.fullName} onChange={e => setStaffForm({ ...staffForm, fullName: e.target.value })} required /></Field>
                  <Field label="Email address"><input type="email" value={staffForm.email} onChange={e => setStaffForm({ ...staffForm, email: e.target.value })} required /></Field>
                  <Field label="Temporary password (8+ chars)"><input type="password" minLength={8} value={staffForm.password} onChange={e => setStaffForm({ ...staffForm, password: e.target.value })} required /></Field>
                  <Field label="Role">
                    <select value={staffForm.role} onChange={e => setStaffForm({ ...staffForm, role: e.target.value })}>
                      <option value="STAFF">Staff (Level 3)</option>
                      <option value="MANAGER">Branch Manager (Level 2)</option>
                      <option value="CUSTOMER">Customer (Level 4)</option>
                    </select>
                  </Field>
                  <Field label="Assigned branch">
                    <select value={staffForm.branchName} onChange={e => setStaffForm({ ...staffForm, branchName: e.target.value })}>
                      <option>Main Branch</option><option>Guntur Branch</option><option>Vijayawada Branch</option><option>Amaravati Branch</option><option>Visakhapatnam Branch</option><option>Hyderabad Branch</option>
                    </select>
                  </Field>
                  <button className="primary" disabled={busy}>Create User <UserPlus size={16} /></button>
                </form>
              </div>

              <div className="panel table-panel">
                <div className="panel-head" style={{ padding: '16px 20px 0' }}><div><h2>All Registered Users</h2><p>Status toggle &amp; role assignments</p></div></div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr><th>Name / Email</th><th>Role</th><th>Branch</th><th>Status</th><th>Actions</th></tr>
                    </thead>
                    <tbody>
                      {usersList.map(u => (
                        <tr key={u.id}>
                          <td><b>{u.fullName}</b><small>{u.email}</small></td>
                          <td><span className="pill">{u.role}</span></td>
                          <td>{u.branch || '—'}</td>
                          <td><span className={statusClass(u.status)}>{u.status}</span></td>
                          <td>
                            {u.id !== user?.id && (
                              <button
                                className={`btn-toggle-active ${u.status === 'ACTIVE' ? 'active' : 'inactive'}`}
                                onClick={() => toggleUserStatus(u.id, u.status)}
                                disabled={busy}
                              >
                                {u.status === 'ACTIVE' ? 'Deactivate' : 'Activate'}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}

        {isAdmin && tab === 'System Policies' && (
          <>
            <div className="section-intro">
              <div><h2>System Configuration &amp; Policy Thresholds</h2><p>Configure transaction limits, approval thresholds, and banking rules.</p></div>
            </div>
            <div className="two-col">
              <div className="panel">
                <div className="panel-head"><div><h2>Operational Thresholds</h2><p>Authoritative policy configuration</p></div></div>
                <form className="form" onSubmit={e => { e.preventDefault(); saveConfig(); }}>
                  <Field label="Manager Approval Threshold (₹)">
                    <input type="number" min="1000" step="500" value={configForm.approvalThreshold} onChange={e => setConfigForm({ ...configForm, approvalThreshold: e.target.value })} required />
                  </Field>
                  <Field label="Daily Outgoing Transfer Limit (₹)">
                    <input type="number" min="5000" step="1000" value={configForm.dailyLimit} onChange={e => setConfigForm({ ...configForm, dailyLimit: e.target.value })} required />
                  </Field>
                  <Field label="Maximum Single Transfer Limit (₹)">
                    <input type="number" min="10000" step="5000" value={configForm.singleLimit} onChange={e => setConfigForm({ ...configForm, singleLimit: e.target.value })} required />
                  </Field>
                  <Field label="Savings Minimum Balance Rule (₹)">
                    <input type="number" min="100" step="100" value={configForm.minBalance} onChange={e => setConfigForm({ ...configForm, minBalance: e.target.value })} required />
                  </Field>
                  <button className="primary" disabled={busy}>Save Policy Configuration <Check size={16} /></button>
                </form>
              </div>

              <div className="panel">
                <div className="panel-head"><div><h2>Policy Safeguards</h2><p>Current active enforcement</p></div></div>
                <Rule title="High-Value Manager Approval" value={`Above ${money(configForm.approvalThreshold)}`} />
                <Rule title="Daily Outgoing Limit" value={money(configForm.dailyLimit)} />
                <Rule title="Max Single Transfer" value={money(configForm.singleLimit)} />
                <Rule title="Minimum Balance Rule" value={money(configForm.minBalance)} />
                <div className="info-box warning" style={{ marginTop: '20px' }}>
                  <ShieldAlert size={18} />
                  <span>Transfers exceeding the Manager Approval Threshold enter the <b>PENDING_APPROVAL</b> state and require explicit branch manager signoff before any ledger funds are moved.</span>
                </div>
              </div>
            </div>
          </>
        )}

        {isAdmin && tab === 'Audit Logs' && (
          <>
            <div className="section-intro">
              <div><h2>System-Wide Audit Trail</h2><p>Append-only audit records of security events, administrative changes, and financial decisions.</p></div>
              <button className="secondary" onClick={load}><RefreshCw size={15} /> Refresh</button>
            </div>
            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Timestamp</th><th>Event</th><th>Actor</th><th>Role</th><th>Reference</th><th>Details</th></tr>
                  </thead>
                  <tbody>
                    {auditLogs.map(l => (
                      <tr key={l.id}>
                        <td>{fmtDate(l.created_at)}</td>
                        <td><b>{l.event_type}</b></td>
                        <td>{l.actor_email}</td>
                        <td><span className="pill">{l.actor_role}</span></td>
                        <td className="mono">{l.reference_no || '—'}</td>
                        <td><small>{l.details}</small></td>
                      </tr>
                    ))}
                    {auditLogs.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: '30px' }}>No audit events recorded yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {/* ======================================================== */}
        {/* ==================== 3. MANAGER MODULES ================ */}
        {/* ======================================================== */}
        {isManager && tab === 'Approval Queue' && (
          <>
            <div className="section-intro">
              <div><h2>Transaction Approval Queue</h2><p>High-value transactions requiring supervisory signoff before financial execution.</p></div>
              <span className="pill">{approvals.length} pending review</span>
            </div>
            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Reference</th><th>Initiator</th><th>Source → Destination</th><th>Amount</th><th>Risk Flag</th><th>Created</th><th>Actions</th></tr>
                  </thead>
                  <tbody>
                    {approvals.map(a => (
                      <tr key={a.id}>
                        <td className="mono"><b>{a.reference_no}</b></td>
                        <td><b>{a.initiator_name}</b><small>{a.initiator_role}</small></td>
                        <td>{a.source_account_number} → {a.destination_account_number}</td>
                        <td className="amount">{money(a.amount)}</td>
                        <td><span className="risk-tag"><AlertTriangle size={12} /> {a.risk_flag || 'High value'}</span></td>
                        <td>{fmtDate(a.created_at)}</td>
                        <td>
                          <div className="queue-actions">
                            <button className="approve" disabled={busy} onClick={() => handleManagerDecision(a.transaction_id, true)}>Approve</button>
                            <button className="reject" disabled={busy} onClick={() => handleManagerDecision(a.transaction_id, false)}>Reject</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {approvals.length === 0 && <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px' }}>No transactions pending approval.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {isManager && tab === 'Staff Monitoring' && (
          <>
            <div className="section-intro">
              <div><h2>Branch Staff Monitoring</h2><p>View active banking staff officers, branch assignments, and permissions.</p></div>
              <span className="pill">{usersList.filter(u => u.role === 'STAFF' || u.role === 'EMPLOYEE').length} staff officers</span>
            </div>
            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Staff Name</th><th>Email</th><th>Assigned Branch</th><th>Status</th><th>Registered Since</th></tr>
                  </thead>
                  <tbody>
                    {usersList.filter(u => u.role === 'STAFF' || u.role === 'EMPLOYEE').map(s => (
                      <tr key={s.id}>
                        <td><b>{s.fullName}</b></td>
                        <td>{s.email}</td>
                        <td>{s.branch || 'Main Branch'}</td>
                        <td><span className={statusClass(s.status)}>{s.status}</span></td>
                        <td>{fmtDate(s.createdAt)}</td>
                      </tr>
                    ))}
                    {usersList.filter(u => u.role === 'STAFF' || u.role === 'EMPLOYEE').length === 0 && (
                      <tr><td colSpan={5} style={{ textAlign: 'center', padding: '32px' }}>No staff accounts registered in this branch yet.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {isManager && tab === 'Customer Complaints' && (
          <>
            <div className="section-intro">
              <div><h2>Customer Support &amp; Escalations</h2><p>Review customer service inquiries and resolve escalated branch complaints.</p></div>
              <span className="pill">{complaints.length} tickets</span>
            </div>
            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Ticket ID</th><th>Customer</th><th>Subject</th><th>Status</th><th>Notes</th><th>Created</th><th>Action</th></tr>
                  </thead>
                  <tbody>
                    {complaints.map(c => (
                      <tr key={c.id}>
                        <td className="mono">TKT-{c.id}</td>
                        <td><b>{c.customer_name}</b><small>{c.customer_email}</small></td>
                        <td><b>{c.subject}</b><small>{c.description}</small></td>
                        <td><span className={statusClass(c.status)}>{c.status}</span></td>
                        <td><small>{c.manager_notes || c.staff_notes || '—'}</small></td>
                        <td>{fmtDate(c.created_at)}</td>
                        <td>
                          {c.status !== 'RESOLVED' && (
                            <button className="detailbtn" onClick={() => setReplyModal({ open: true, ticketId: c.id, notes: '', status: 'RESOLVED' })}>Resolve Ticket</button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {complaints.length === 0 && <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px' }}>No customer tickets filed.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {/* ======================================================== */}
        {/* ==================== 4. STAFF MODULES ================== */}
        {/* ======================================================== */}
        {isStaff && tab === 'Customer Onboarding' && (
          <>
            <div className="section-intro">
              <div><h2>Customer Registration &amp; Onboarding</h2><p>Assisted customer registration and initial account opening application.</p></div>
            </div>
            <div className="two-col">
              <div className="panel">
                <div className="panel-head"><div><h2>Register New Customer</h2><p>Creates identity &amp; prepares application</p></div></div>
                <form className="form" onSubmit={e => {
                  e.preventDefault();
                  act(() => request('/staff/customer-registration', { method: 'POST', body: JSON.stringify(staffOnboard) }), 'Customer registered and verified! Manager approval required to activate.').then(() => {
                    setStaffOnboard({ fullName: '', email: '', phone: '', dateOfBirth: '', address: '', occupation: '', accountType: 'SAVINGS', initialDeposit: '1000', branchName: 'Main Branch' });
                    setTab('Applications Queue');
                  });
                }}>
                  <Field label="Customer Full Name"><input value={staffOnboard.fullName} onChange={e => setStaffOnboard({ ...staffOnboard, fullName: e.target.value })} required /></Field>
                  <Field label="Email Address"><input type="email" value={staffOnboard.email} onChange={e => setStaffOnboard({ ...staffOnboard, email: e.target.value })} required /></Field>
                  <Field label="Mobile Number"><input value={staffOnboard.phone} onChange={e => setStaffOnboard({ ...staffOnboard, phone: e.target.value })} placeholder="9876543210" required /></Field>
                  <Field label="Date of Birth"><input type="date" value={staffOnboard.dateOfBirth} onChange={e => setStaffOnboard({ ...staffOnboard, dateOfBirth: e.target.value })} required /></Field>
                  <Field label="Address"><input value={staffOnboard.address} onChange={e => setStaffOnboard({ ...staffOnboard, address: e.target.value })} required /></Field>
                  <Field label="Occupation"><input value={staffOnboard.occupation} onChange={e => setStaffOnboard({ ...staffOnboard, occupation: e.target.value })} required /></Field>
                  <Field label="Account Type">
                    <select value={staffOnboard.accountType} onChange={e => setStaffOnboard({ ...staffOnboard, accountType: e.target.value })}>
                      <option value="SAVINGS">Savings Account</option>
                      <option value="CURRENT">Current Account</option>
                    </select>
                  </Field>
                  <Field label="Initial Deposit (₹)">
                    <input type="number" min="1000" value={staffOnboard.initialDeposit} onChange={e => setStaffOnboard({ ...staffOnboard, initialDeposit: e.target.value })} required />
                  </Field>
                  <button className="primary" disabled={busy}>Register &amp; Submit Verification <UserPlus size={16} /></button>
                </form>
              </div>

              <div className="panel">
                <div className="panel-head"><div><h2>Onboarding Workflow</h2><p>Multi-tier approval chain</p></div></div>
                <div className="saga-steps">
                  <Step n="01" title="Staff Data Intake" text="Staff enters identity and residential details." />
                  <Step n="02" title="Staff Verification" text="Staff confirms KYC details and mobile number." />
                  <Step n="03" title="Manager Signoff" text="Branch Manager or Admin verifies and activates account." />
                  <Step n="04" title="Initial Deposit Posting" text="Ledger account is created with opening deposit." />
                </div>
              </div>
            </div>
          </>
        )}

        {isStaff && tab === 'Customer Support' && (
          <>
            <div className="section-intro">
              <div><h2>Branch Customer Support</h2><p>Review customer tickets, provide replies, or escalate to Branch Manager.</p></div>
              <span className="pill">{complaints.length} tickets</span>
            </div>
            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Ticket ID</th><th>Customer</th><th>Subject</th><th>Status</th><th>Notes</th><th>Actions</th></tr>
                  </thead>
                  <tbody>
                    {complaints.map(c => (
                      <tr key={c.id}>
                        <td className="mono">TKT-{c.id}</td>
                        <td><b>{c.customer_name}</b><small>{c.customer_email}</small></td>
                        <td><b>{c.subject}</b><small>{c.description}</small></td>
                        <td><span className={statusClass(c.status)}>{c.status}</span></td>
                        <td><small>{c.staff_notes || '—'}</small></td>
                        <td>
                          <div className="queue-actions">
                            <button className="detailbtn" onClick={() => setReplyModal({ open: true, ticketId: c.id, notes: '', status: 'IN_PROGRESS' })}>Reply</button>
                            {c.status !== 'ESCALATED' && (
                              <button className="reject" onClick={() => act(() => request(`/complaints/${c.id}/escalate`, { method: 'POST' }), 'Ticket escalated to Manager.')}>Escalate</button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {complaints.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: '32px' }}>No customer tickets open.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {/* ======================================================== */}
        {/* ==================== 5. CUSTOMER MODULES =============== */}
        {/* ======================================================== */}
        {role === 'CUSTOMER' && tab === 'Beneficiaries' && (
          <>
            <div className="section-intro">
              <div><h2>Beneficiary Management</h2><p>Add and manage verified recipient bank accounts for quick transfers.</p></div>
              <button className="primary" onClick={() => setBeneficiaryModal(true)}><UserPlus size={16} /> Add Beneficiary</button>
            </div>
            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Nickname</th><th>Beneficiary Name</th><th>Account Number</th><th>Bank</th><th>Status</th><th>Action</th></tr>
                  </thead>
                  <tbody>
                    {beneficiaries.map(b => (
                      <tr key={b.id}>
                        <td><b>{b.nickname}</b></td>
                        <td>{b.beneficiary_name}</td>
                        <td className="mono">{b.account_number}</td>
                        <td>{b.bank_name}</td>
                        <td><span className={statusClass(b.status)}>{b.status}</span></td>
                        <td>
                          <div className="queue-actions">
                            <button className="approve" onClick={() => { setTransfer({ ...transfer, destinationAccountId: b.account_number }); setTab('Transfer Money'); }}>Transfer</button>
                            <button className="reject" onClick={() => act(() => request(`/beneficiaries/${b.id}`, { method: 'DELETE' }), 'Beneficiary removed.')}>Remove</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {beneficiaries.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: '32px' }}>No saved beneficiaries yet. Click "Add Beneficiary" above.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {role === 'CUSTOMER' && tab === 'Account Statements' && (
          <>
            <div className="section-intro">
              <div><h2>Account Statements</h2><p>View running balances, debit/credit summaries, and export statements.</p></div>
            </div>
            <div className="filter-bar">
              <label style={{ fontSize: '12px', fontWeight: 600 }}>Select Account:</label>
              <select value={selectedStatementAcc} onChange={e => { setSelectedStatementAcc(e.target.value); loadStatement(e.target.value); }}>
                {accounts.map(a => <option key={a.id} value={a.account_number}>{a.account_number} · {a.account_type} · {money(a.balance)}</option>)}
              </select>
              <button className="primary" onClick={() => loadStatement(selectedStatementAcc)} disabled={busy || !selectedStatementAcc}><Download size={15} /> Generate Statement</button>
            </div>

            {statementData && (
              <div className="statement-box">
                <div className="statement-header">
                  <div>
                    <h2 style={{ margin: '0 0 6px' }}>Account Statement: {statementData.accountNumber}</h2>
                    <p style={{ margin: 0, color: '#64748b' }}>Account Holder: {statementData.customerName} · Branch: {statementData.branch}</p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <b>Current Balance: {money(statementData.currentBalance)}</b>
                    <small style={{ display: 'block', color: '#64748b' }}>Generated: {fmtDate(statementData.generatedAt)}</small>
                  </div>
                </div>

                <div className="statement-summary">
                  <div><small>Total Inward Credits</small><b>{money(statementData.totalCredits)}</b></div>
                  <div><small>Total Outward Debits</small><b>{money(statementData.totalDebits)}</b></div>
                  <div><small>Minimum Balance</small><b>{money(statementData.minimumBalance)}</b></div>
                  <div><small>Transactions</small><b>{statementData.transactions.length} entries</b></div>
                </div>

                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr><th>Date</th><th>Reference</th><th>Description</th><th>Type</th><th>Amount</th><th>Running Balance</th></tr>
                    </thead>
                    <tbody>
                      {statementData.transactions.map((tx: any) => (
                        <tr key={tx.id}>
                          <td>{fmtDate(tx.date)}</td>
                          <td className="mono">{tx.reference}</td>
                          <td>{tx.description}</td>
                          <td><span className={`status ${tx.type === 'CREDIT' ? 'success' : 'failed'}`}>{tx.type}</span></td>
                          <td className="amount">{money(tx.amount)}</td>
                          <td><b>{money(tx.runningBalance)}</b></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}

        {role === 'CUSTOMER' && tab === 'Help & Support' && (
          <>
            <div className="section-intro">
              <div><h2>Customer Support &amp; Helpdesk</h2><p>Submit service inquiries or complaints and track resolution status.</p></div>
              <button className="primary" onClick={() => setComplaintModal(true)}>Submit New Complaint</button>
            </div>
            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Ticket ID</th><th>Category</th><th>Subject</th><th>Status</th><th>Bank Resolution / Notes</th><th>Created</th></tr>
                  </thead>
                  <tbody>
                    {complaints.map(c => (
                      <tr key={c.id}>
                        <td className="mono">TKT-{c.id}</td>
                        <td><span className="pill">{c.category}</span></td>
                        <td><b>{c.subject}</b><small>{c.description}</small></td>
                        <td><span className={statusClass(c.status)}>{c.status}</span></td>
                        <td><small>{c.manager_notes || c.staff_notes || 'Pending representative review.'}</small></td>
                        <td>{fmtDate(c.created_at)}</td>
                      </tr>
                    ))}
                    {complaints.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: '32px' }}>No complaints filed. Click "Submit New Complaint" to get assistance.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {role === 'CUSTOMER' && tab === 'Notifications' && (
          <>
            <div className="section-intro">
              <div><h2>Security &amp; Account Notifications</h2><p>Real-time transaction alerts, transfer approvals, and one-time codes.</p></div>
              <button className="secondary" onClick={() => act(() => request('/notifications/read-all', { method: 'POST' }), 'All marked as read.')}>Mark all read</button>
            </div>
            <div className="panel">
              {notifications.map(n => (
                <div key={n.id} className={`notification-card ${n.is_read ? '' : 'unread'}`}>
                  <div className="notification-dot" />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <b>{n.title}</b>
                      <small style={{ color: '#8898aa' }}>{fmtDate(n.created_at)}</small>
                    </div>
                    <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#4a5568' }}>{n.message}</p>
                  </div>
                </div>
              ))}
              {notifications.length === 0 && <Empty text="No notifications recorded." />}
            </div>
          </>
        )}

        {/* ======================================================== */}
        {/* ==================== 6. SHARED BANKING TABS ============ */}
        {/* ======================================================== */}
        {(tab === 'My Accounts' || tab === 'Accounts' || tab === 'Branch Accounts' || tab === 'Customer Accounts') && (
          <>
            <div className="section-intro">
              <div><h2>All Accounts &amp; Applications</h2><p>View balances, policies, and submit applications.</p></div>
              <div style={{ display: 'flex', gap: '8px' }}>
                {role === 'CUSTOMER' && (
                  <button className="primary" onClick={() => setShowNewApp(!showNewApp)}>
                    <Plus size={15} /> {showNewApp ? 'Hide Application Form' : 'Apply for New Account'}
                  </button>
                )}
                <button className="secondary" onClick={load}><RefreshCw size={15} /> Refresh</button>
              </div>
            </div>
            <div className="panel" style={{ marginBottom: '24px' }}>
              <div className="panel-head">
                <div><h2>Bank Accounts</h2><p>Active and approved accounts in scope</p></div>
                <span className="count-bubble">{accounts.length}</span>
              </div>
              <div className="account-list">
                {accounts.length === 0 && <Empty text="No accounts found in this scope." />}
                {accounts.map((a, i) => (
                  <div className="account-row" key={a.id}>
                    <div className={'account-icon tone' + (i % 3)}><Landmark size={20} /></div>
                    <div className="account-info">
                      <b>{a.account_type === 'SAVINGS' ? 'Savings account' : 'Current account'}</b>
                      <small>Account No: {a.account_number} · Owner ID: #{a.owner_user_id}</small>
                      <small>Min balance {money(a.minimum_balance)} · Daily limit {money(a.daily_limit)} · Opened {fmtDate(a.created_at)}</small>
                    </div>
                    <div className="account-balance">
                      <b>{money(a.balance)}</b>
                      <span className={statusClass(a.status)}>{a.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Applications under review for Customer */}
            {role === 'CUSTOMER' && apps.length > 0 && (
              <div className="panel" style={{ marginBottom: '24px' }}>
                <div className="panel-head">
                  <div><h2>Your Submitted Applications</h2><p>Track verification and activation progress</p></div>
                  <span className="count-bubble">{apps.length}</span>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr><th>Product</th><th>Initial Deposit</th><th>Status</th><th>Submitted</th><th>Review Stage</th></tr>
                    </thead>
                    <tbody>
                      {apps.map(ap => (
                        <tr key={ap.id}>
                          <td><b>{ap.account_type} Account</b><small>{ap.reason}</small></td>
                          <td>{money(ap.initial_deposit)}</td>
                          <td><span className={statusClass(ap.status)}>{ap.status}</span></td>
                          <td>{fmtDate(ap.created_at)}</td>
                          <td>
                            {ap.status === 'PENDING_REVIEW' && <span className="muted">Stage 1: Awaiting Staff KYC verification</span>}
                            {ap.status === 'VERIFIED' && <span className="muted">Stage 2: Staff verified; awaiting Manager approval</span>}
                            {ap.status === 'APPROVED' && <span className="status success">Activated (Account #{ap.account_id})</span>}
                            {ap.status === 'REJECTED' && <span className="status failed">Application rejected</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {role === 'CUSTOMER' && (showNewApp || accounts.length === 0) && (
              <div className="two-col">
                <div className="panel">
                  <div className="panel-head"><div><h2>Open a new account</h2><p>Submit for multi-tier verification</p></div></div>
                  <form className="form" onSubmit={e => {
                    e.preventDefault();
                    act(() => request('/applications', { method: 'POST', body: JSON.stringify(application) }), 'Application submitted for staff review.').then(() => {
                      setApplication({ accountType: 'SAVINGS', initialDeposit: '1000', phone: '', dateOfBirth: '', address: '', occupation: '', branchName: 'Main Branch', reason: 'New account application' });
                    });
                  }}>
                    <Field label="Applicant name"><input value={user?.fullName || user?.full_name || ''} readOnly /></Field>
                    <Field label="Mobile number (10 digits)"><input value={application.phone} onChange={e => setApplication({ ...application, phone: e.target.value.replace(/\D/g, '').slice(0, 10) })} placeholder="9876543210" required /></Field>
                    <Field label="Date of birth"><input type="date" value={application.dateOfBirth} onChange={e => setApplication({ ...application, dateOfBirth: e.target.value })} required /></Field>
                    <Field label="Residential address"><input value={application.address} onChange={e => setApplication({ ...application, address: e.target.value })} placeholder="Complete street address" required /></Field>
                    <Field label="Occupation"><input value={application.occupation} onChange={e => setApplication({ ...application, occupation: e.target.value })} placeholder="Employment details" required /></Field>
                    <Field label="Account Type">
                      <select value={application.accountType} onChange={e => setApplication({ ...application, accountType: e.target.value })}>
                        <option value="SAVINGS">Savings Account</option>
                        <option value="CURRENT">Current Account</option>
                      </select>
                    </Field>
                    <Field label="Branch">
                      <select value={application.branchName} onChange={e => setApplication({ ...application, branchName: e.target.value })}>
                        <option>Main Branch</option><option>Guntur Branch</option><option>Vijayawada Branch</option><option>Amaravati Branch</option><option>Visakhapatnam Branch</option><option>Hyderabad Branch</option>
                      </select>
                    </Field>
                    <Field label="Initial deposit (₹)"><input type="number" min="1000" step="500" value={application.initialDeposit} onChange={e => setApplication({ ...application, initialDeposit: e.target.value })} required /></Field>
                    <button className="primary" disabled={busy}>Submit Account Application <ChevronRight size={17} /></button>
                  </form>
                </div>
                <div className="panel">
                  <div className="panel-head"><div><h2>Account Rules &amp; Limits</h2><p>Policy guidelines</p></div></div>
                  <Rule title="Savings Minimum Balance" value="₹1,000" />
                  <Rule title="Daily Outgoing Limit" value="₹50,000" />
                  <Rule title="Approval Threshold" value="Transfers > ₹20,000 require Manager signoff" />
                  <div className="info-box"><ShieldCheck size={18} /><span>Account opening is verified by Staff and approved by Branch Manager before activation.</span></div>
                </div>
              </div>
            )}
          </>
        )}

        {(tab === 'Applications' || tab === 'Applications Queue' || tab === 'Account Applications') && (
          <>
            <div className="section-intro">
              <div><h2>Account Applications Queue</h2><p>Staff verifies customer information; Manager approves to activate account.</p></div>
              <span className="pill">{apps.length} applications</span>
            </div>
            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Applicant</th><th>Product</th><th>Deposit</th><th>Status</th><th>Branch</th><th>Submitted</th><th>Review Action</th></tr>
                  </thead>
                  <tbody>
                    {apps.map(a => (
                      <tr key={a.id}>
                        <td><b>{a.customer_name}</b><small>{a.reason}</small></td>
                        <td>{a.account_type}</td>
                        <td>{money(a.initial_deposit)}</td>
                        <td><span className={statusClass(a.status)}>{a.status}</span></td>
                        <td>{a.branch_name}</td>
                        <td>{fmtDate(a.created_at)}</td>
                        <td>
                          {isStaff && a.status === 'PENDING_REVIEW' && (role === 'STAFF' || role === 'EMPLOYEE') && (
                            <div className="queue-actions">
                              <button className="approve" disabled={busy} onClick={() => act(() => request(`/applications/${a.id}/verify`, { method: 'POST' }), 'Verified by Staff. Awaiting Manager approval.')}>Verify</button>
                              <button className="reject" disabled={busy} onClick={() => setRejectionModal({ open: true, targetId: a.id, targetType: 'APPLICATION', reason: '' })}>Reject</button>
                            </div>
                          )}
                          {isManager && (a.status === 'VERIFIED' || (isAdmin && a.status === 'PENDING_REVIEW')) && (
                            <div className="queue-actions">
                              <button className="approve" disabled={busy} onClick={() => act(() => request(`/applications/${a.id}/approve`, { method: 'POST' }), 'Approved by Manager. Account activated.')}>Approve &amp; Activate</button>
                              <button className="reject" disabled={busy} onClick={() => setRejectionModal({ open: true, targetId: a.id, targetType: 'APPLICATION', reason: '' })}>Reject</button>
                            </div>
                          )}
                          {(a.status === 'APPROVED' || a.status === 'REJECTED') && <span className="muted">{a.account_id ? `Account #${a.account_id}` : a.status}</span>}
                        </td>
                      </tr>
                    ))}
                    {apps.length === 0 && <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px' }}>No applications in queue.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {(tab === 'Deposit Requests' || tab === 'Deposit requests') && (
          <>
            <div className="section-intro">
              <div><h2>Deposit Operations</h2><p>Deposits require authorized review before ledger funds are credited.</p></div>
              <span className="pill">{summary.pendingDeposits || 0} pending review</span>
            </div>
            <div className="two-col">
              <div className="panel">
                <div className="panel-head"><div><h2>Submit Deposit Request</h2><p>Funds remain pending until authorized</p></div></div>
                <form className="form" onSubmit={e => { e.preventDefault(); doDeposit(); }}>
                  <Field label="Credit Account">
                    <select value={deposit.accountId} onChange={e => setDeposit({ ...deposit, accountId: e.target.value })} required>
                      <option value="">Select an active account</option>
                      {accounts.map(a => <option key={a.id} value={a.id}>{a.account_number} · {a.account_type} · {money(a.balance)}</option>)}
                    </select>
                  </Field>
                  <Field label="Deposit Amount (₹)">
                    <input type="number" min="1" max="100000" step="0.01" value={deposit.amount} onChange={e => setDeposit({ ...deposit, amount: e.target.value })} required />
                  </Field>
                  <button className="primary" disabled={busy || accounts.length === 0 || !deposit.accountId}><ArrowDownLeft size={16} /> Submit Deposit</button>
                </form>
              </div>

              <div className="panel">
                <div className="panel-head">
                  <div>
                    <h2>{isStaff ? 'Pending Deposit Approvals' : 'My Deposit History'}</h2>
                    <p>{isStaff ? 'Review queue for customer deposits' : 'Track status of your submitted deposits'}</p>
                  </div>
                </div>
                {(isStaff 
                  ? txns.filter(t => t.txn_type === 'DEPOSIT' && t.status === 'PENDING_APPROVAL')
                  : txns.filter(t => t.txn_type === 'DEPOSIT')
                ).map(t => (
                  <div className="queue-row" key={t.id}>
                    <div>
                      <b>{money(t.amount)} deposit</b>
                      <small>{t.reference_no} · Account #{t.destination_account_id}</small>
                      <small>{fmtDate(t.created_at)}</small>
                      {t.rejection_reason && <small style={{ color: '#ef4444' }}>Reason: {t.rejection_reason}</small>}
                    </div>
                    {isStaff ? (
                      <div className="queue-actions">
                        <button className="approve" disabled={busy} onClick={() => act(() => request('/deposits/' + t.id + '/approve', { method: 'POST' }), 'Deposit approved & balance credited.')}>Approve</button>
                        <button className="reject" disabled={busy} onClick={() => setRejectionModal({ open: true, targetId: t.id, targetType: 'DEPOSIT', reason: '' })}>Reject</button>
                      </div>
                    ) : (
                      <span className={statusClass(t.status)}>{t.status}</span>
                    )}
                  </div>
                ))}
                {(isStaff 
                  ? txns.filter(t => t.txn_type === 'DEPOSIT' && t.status === 'PENDING_APPROVAL')
                  : txns.filter(t => t.txn_type === 'DEPOSIT')
                ).length === 0 && <Empty text={isStaff ? "No deposits awaiting approval." : "No deposits submitted yet."} />}
              </div>
            </div>
          </>
        )}

        {(tab === 'Transfer Money' || tab === 'Transfer money') && (
          <>
            <div className="section-intro">
              <div><h2>Transfer Between Accounts</h2><p>Saga-orchestrated fund transfer with OTP verification and threshold approval.</p></div>
              <span className="pill">Approval threshold: ₹20,000</span>
            </div>
            <div className="two-col">
              <div className="panel">
                <div className="panel-head"><div><h2>Initiate Fund Transfer</h2><p>Secure atomic transfer</p></div></div>
                <form className="form" onSubmit={e => { e.preventDefault(); doTransfer(); }}>
                  <Field label="From Account">
                    <select value={transfer.sourceAccountId} onChange={e => setTransfer({ ...transfer, sourceAccountId: e.target.value })} required>
                      <option value="">Select source account</option>
                      {accounts.map(a => <option key={a.id} value={a.id}>{a.account_number} · {money(a.balance)}</option>)}
                    </select>
                  </Field>

                  {beneficiaries.length > 0 && (
                    <Field label="Choose Saved Beneficiary (Optional)">
                      <select onChange={e => { if (e.target.value) setTransfer({ ...transfer, destinationAccountId: e.target.value }); }}>
                        <option value="">-- Or enter account number below --</option>
                        {beneficiaries.map(b => <option key={b.id} value={b.account_number}>{b.nickname} ({b.beneficiary_name} - {b.account_number})</option>)}
                      </select>
                    </Field>
                  )}

                  <Field label="Recipient Account Number">
                    <input value={transfer.destinationAccountId} onChange={e => setTransfer({ ...transfer, destinationAccountId: e.target.value })} placeholder="Enter 16-digit account number" required />
                  </Field>
                  <Field label="Amount (₹)">
                    <input type="number" min="1" step="0.01" value={transfer.amount} onChange={e => setTransfer({ ...transfer, amount: e.target.value })} required />
                  </Field>
                  <Field label="Description / Purpose">
                    <input value={transfer.description} onChange={e => setTransfer({ ...transfer, description: e.target.value })} placeholder="Rent, services, family transfer..." />
                  </Field>

                  {Number(transfer.amount) > 20000 && (
                    <div className="risk-tag" style={{ margin: '4px 0' }}>
                      <AlertTriangle size={14} /> Transfer exceeds ₹20,000 threshold and will be submitted for Manager approval.
                    </div>
                  )}

                  <button type="button" className="secondary" disabled={busy} onClick={requestTransferOtp}>
                    {transferOtpSent ? 'Resend transfer OTP' : 'Send transfer OTP to email'}
                  </button>
                  {transferOtpSent && (
                    <Field label="Transfer OTP (6 digits)">
                      <input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={transferOtp} onChange={e => setTransferOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="Enter 6-digit code" required />
                    </Field>
                  )}
                  <button className="primary" disabled={busy || accounts.length === 0 || !transfer.sourceAccountId || !transfer.destinationAccountId.trim() || !transferOtpSent || transferOtp.length !== 6}>
                    Start Transfer Workflow <ArrowLeftRight size={16} />
                  </button>
                </form>
              </div>

              <div className="panel">
                <div className="panel-head"><div><h2>Saga Orchestration Rules</h2><p>Consistent distributed transactions</p></div></div>
                <div className="saga-steps">
                  <Step n="01" title="Validate Ownership &amp; Balance" text="Account ownership, minimum balance, and daily limits checked." />
                  <Step n="02" title="Approval Threshold Evaluation" text="Transfers above policy threshold are held for Manager signoff." />
                  <Step n="03" title="Atomic Source Debit" text="Source funds debited with idempotency protection." />
                  <Step n="04" title="Destination Credit" text="Recipient account credited in the ledger." />
                  <Step n="05" title="Saga Compensation" text="If destination credit fails, compensating refund restores source balance." />
                </div>
              </div>
            </div>
          </>
        )}

        {(tab === 'Transactions' || tab === 'Transaction Monitor') && (
          <>
            <div className="section-intro">
              <div><h2>Transaction History &amp; Audit</h2><p>Click any transaction row to open the complete Saga event timeline.</p></div>
              <button className="secondary" onClick={load}><RefreshCw size={15} /> Refresh</button>
            </div>

            <div className="filter-bar">
              <label style={{ fontSize: '12px', fontWeight: 600 }}>Filter by Status:</label>
              <select value={txnFilterStatus} onChange={e => setTxnFilterStatus(e.target.value)}>
                <option value="ALL">All Statuses</option>
                <option value="SUCCESS">SUCCESS</option>
                <option value="PENDING_APPROVAL">PENDING_APPROVAL</option>
                <option value="REJECTED">REJECTED</option>
                <option value="FAILED">FAILED</option>
                <option value="COMPENSATED">COMPENSATED</option>
                <option value="REQUIRES_REVIEW">REQUIRES_REVIEW</option>
              </select>
            </div>

            <div className="panel table-panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Type</th><th>Reference</th><th>Initiator</th><th>Amount</th><th>Status</th><th>Created</th><th>Action</th></tr>
                  </thead>
                  <tbody>
                    {txns.filter(t => txnFilterStatus === 'ALL' || t.status === txnFilterStatus).map(t => (
                      <tr key={t.id}>
                        <td><b>{t.txn_type === 'DEPOSIT' ? 'Deposit' : 'Transfer'}</b><small>{t.description}</small></td>
                        <td className="mono">{t.reference_no}</td>
                        <td>{t.customer_name}</td>
                        <td className="amount">{money(t.amount)}</td>
                        <td><span className={statusClass(t.status)}>{t.status}</span></td>
                        <td>{fmtDate(t.created_at)}</td>
                        <td>
                          <button className="detailbtn" onClick={() => openTxn(t)}>Timeline <ChevronRight size={14} /></button>
                        </td>
                      </tr>
                    ))}
                    {txns.length === 0 && <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px' }}>No transactions recorded.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>

            {selected && (
              <div className="panel timeline-panel">
                <div className="panel-head">
                  <div><h2>Transaction Timeline</h2><p>{selected.reference_no} · {selected.txn_type} · {money(selected.amount)}</p></div>
                  <button className="iconbtn" onClick={() => { setSelected(null); setEvents([]); }}>×</button>
                </div>
                <div className="timeline-summary">
                  <div><small>Current Status</small><span className={statusClass(selected.status)}>{selected.status}</span></div>
                  <div><small>Initiated</small><b>{fmtDate(selected.created_at)}</b></div>
                  <div><small>Rejection Reason</small><b>{selected.rejection_reason || '—'}</b></div>
                </div>
                <div className="timeline">
                  {events.map(ev => (
                    <div className="timeline-item" key={ev.id}>
                      <div className={'timeline-marker ' + (ev.status === 'SUCCESS' ? 'good' : ev.status === 'COMPENSATED' ? 'warn' : ev.status.includes('FAIL') || ev.status === 'REJECTED' ? 'bad' : '')}>
                        {ev.status === 'SUCCESS' ? <CheckCircle2 size={16} /> : ev.status === 'REJECTED' || ev.status.includes('FAIL') ? <XCircle size={16} /> : <Activity size={16} />}
                      </div>
                      <div className="timeline-body">
                        <div className="timeline-title"><b>{ev.title}</b><span className={statusClass(ev.status)}>{ev.status}</span></div>
                        <p>{ev.details}</p>
                        <small>{fmtDate(ev.created_at)}</small>
                      </div>
                    </div>
                  ))}
                </div>
                {selected.status === 'REQUIRES_REVIEW' && isStaff && (
                  <button className="primary" disabled={busy} onClick={() => act(() => request(`/transactions/${selected.id}/resolve-review`, { method: 'POST' }), 'Reconciliation resolved; compensation recorded.').then(() => openTxn(selected))}>
                    <ShieldCheck size={16} /> Resolve Reconciliation &amp; Restore Funds
                  </button>
                )}
              </div>
            )}
          </>
        )}

        {/* Saga Admin Test Runner */}
        {isAdmin && tab === 'Saga Test Runner' && (
          <>
            <div className="section-intro">
              <div><h2>Admin Saga Test Runner</h2><p>Simulate controlled failure and compensation scenarios for resilience testing.</p></div>
            </div>
            <div className="two-col">
              <div className="panel">
                <div className="panel-head"><div><h2>Run Scenario</h2><p>Simulate distributed transaction outcomes</p></div></div>
                <form className="form" onSubmit={e => {
                  e.preventDefault();
                  act(() => request('/admin/saga-test-transfers', {
                    method: 'POST',
                    body: JSON.stringify({
                      sourceAccountId: Number(transfer.sourceAccountId),
                      destinationAccountNumber: transfer.destinationAccountId.trim(),
                      amount: Number(transfer.amount),
                      outcome: transfer.demoOutcome
                    })
                  }), 'Saga test finished. Open timeline to inspect recorded stages.').then(() => setTab('Transaction Monitor'));
                }}>
                  <Field label="Source Account">
                    <select value={transfer.sourceAccountId} onChange={e => setTransfer({ ...transfer, sourceAccountId: e.target.value })} required>
                      <option value="">Select source account</option>
                      {accounts.map(a => <option key={a.id} value={a.id}>{a.account_number} · {money(a.balance)}</option>)}
                    </select>
                  </Field>
                  <Field label="Destination Account Number">
                    <input value={transfer.destinationAccountId} onChange={e => setTransfer({ ...transfer, destinationAccountId: e.target.value })} placeholder="Recipient account number" required />
                  </Field>
                  <Field label="Amount (₹)">
                    <input type="number" min="1" step="0.01" value={transfer.amount} onChange={e => setTransfer({ ...transfer, amount: e.target.value })} required />
                  </Field>
                  <Field label="Failure Scenario">
                    <select value={transfer.demoOutcome} onChange={e => setTransfer({ ...transfer, demoOutcome: e.target.value })}>
                      <option value="SUCCESS">Success — Debit and credit confirmed</option>
                      <option value="FAIL_CREDIT_COMPENSATE">Destination credit fails — Saga compensation succeeds</option>
                      <option value="FAIL_CREDIT_REVIEW">Destination credit &amp; compensation fail — Escalates to REQUIRES_REVIEW</option>
                    </select>
                  </Field>
                  <button className="primary" disabled={busy || accounts.length === 0 || !transfer.sourceAccountId || !transfer.destinationAccountId.trim()}>
                    Execute Scenario <ArrowLeftRight size={16} />
                  </button>
                </form>
              </div>
              <div className="panel">
                <div className="panel-head"><div><h2>Compensation Verification</h2><p>Saga resilience guarantees</p></div></div>
                <div className="saga-steps">
                  <Step n="01" title="FAIL_CREDIT_COMPENSATE" text="Source debit confirmed; destination credit blocked; Saga executes compensation credit to restore source funds." />
                  <Step n="02" title="FAIL_CREDIT_REVIEW" text="Destination credit blocked; compensation fails; marked REQUIRES_REVIEW for manual reconciliation." />
                </div>
              </div>
            </div>
          </>
        )}

        {/* Fixed Deposits Tab */}
        {tab === 'Fixed Deposits' && (
          <>
            <div className="section-intro">
              <div><h2>Fixed Deposits</h2><p>Lock funds for a term and receive guaranteed interest at maturity.</p></div>
            </div>
            <div className="two-col">
              <div className="panel">
                <div className="panel-head"><div><h2>Open Term Deposit</h2><p>6.5% annual rate</p></div></div>
                <form className="form" onSubmit={e => {
                  e.preventDefault();
                  act(() => request('/fixed-deposits', { method: 'POST', body: JSON.stringify({ accountId: Number(fdForm.accountId), amount: Number(fdForm.amount), tenureMonths: Number(fdForm.tenureMonths) }) }), 'Fixed deposit opened.').then(() => {
                    setFdForm({ ...fdForm, amount: '' });
                  });
                }}>
                  <Field label="Fund from account">
                    <select value={fdForm.accountId} onChange={e => setFdForm({ ...fdForm, accountId: e.target.value })} required>
                      <option value="">Select account</option>
                      {accounts.filter(a => a.owner_user_id === user?.id).map(a => <option key={a.id} value={a.id}>{a.account_number} · {money(a.balance)}</option>)}
                    </select>
                  </Field>
                  <Field label="Principal Amount (₹)"><input type="number" min="1000" step="100" value={fdForm.amount} onChange={e => setFdForm({ ...fdForm, amount: e.target.value })} required /></Field>
                  <Field label="Tenure">
                    <select value={fdForm.tenureMonths} onChange={e => setFdForm({ ...fdForm, tenureMonths: e.target.value })}>
                      <option value="3">3 Months</option><option value="6">6 Months</option><option value="12">12 Months</option><option value="24">24 Months</option><option value="36">36 Months</option>
                    </select>
                  </Field>
                  <button className="primary" disabled={busy || !fdForm.accountId}>Open Fixed Deposit <Banknote size={16} /></button>
                </form>
              </div>

              <div className="panel table-panel">
                <div className="panel-head" style={{ padding: '16px 20px 0' }}><div><h2>Your Active Deposits</h2><p>Term status and payout</p></div></div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr><th>Reference</th><th>Principal</th><th>Tenure</th><th>Maturity</th><th>Status</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                      {fixedDeposits.map(fd => (
                        <tr key={fd.id}>
                          <td className="mono">{fd.reference_no}</td>
                          <td>{money(fd.principal)}</td>
                          <td>{fd.tenure_months} mos</td>
                          <td>{fd.maturity_date}</td>
                          <td><span className={statusClass(fd.status)}>{fd.status}</span></td>
                          <td>
                            {fd.status === 'ACTIVE' && (
                              <button className="secondary" disabled={busy} onClick={() => act(() => request(`/fixed-deposits/${fd.id}/close`, { method: 'POST' }), 'Fixed deposit matured and paid out.')}>Mature / Close</button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {fixedDeposits.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: '32px' }}>No fixed deposits opened.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}

        {/* Loans Tab & Loan Approvals for Manager */}
        {(tab === 'Loans' || tab === 'Loan Approvals') && (
          <>
            <div className="section-intro">
              <div><h2>Loan Applications &amp; Review</h2><p>Submit a loan request or review and disburse loan funds.</p></div>
            </div>
            <div className="two-col">
              {role === 'CUSTOMER' && (
                <div className="panel">
                  <div className="panel-head"><div><h2>Apply for Loan</h2><p>Educational loan product</p></div></div>
                  <form className="form" onSubmit={e => {
                    e.preventDefault();
                    act(() => request('/loans', { method: 'POST', body: JSON.stringify({ accountId: Number(loanForm.accountId), amount: Number(loanForm.amount), purpose: loanForm.purpose, monthlyIncome: Number(loanForm.monthlyIncome) }) }), 'Loan application submitted for review.').then(() => {
                      setLoanForm({ accountId: '', amount: '', purpose: '', monthlyIncome: '' });
                    });
                  }}>
                    <Field label="Credit destination account">
                      <select value={loanForm.accountId} onChange={e => setLoanForm({ ...loanForm, accountId: e.target.value })} required>
                        <option value="">Select account</option>
                        {accounts.filter(a => a.owner_user_id === user?.id).map(a => <option key={a.id} value={a.id}>{a.account_number}</option>)}
                      </select>
                    </Field>
                    <Field label="Loan Amount (₹5,000–₹10,00,000)"><input type="number" min="5000" max="1000000" value={loanForm.amount} onChange={e => setLoanForm({ ...loanForm, amount: e.target.value })} required /></Field>
                    <Field label="Monthly Income (₹)"><input type="number" min="1" value={loanForm.monthlyIncome} onChange={e => setLoanForm({ ...loanForm, monthlyIncome: e.target.value })} required /></Field>
                    <Field label="Detailed Purpose"><input minLength={10} value={loanForm.purpose} onChange={e => setLoanForm({ ...loanForm, purpose: e.target.value })} placeholder="Education, home improvement..." required /></Field>
                    <button className="primary" disabled={busy || !loanForm.accountId}>Submit Loan Application <ChevronRight size={16} /></button>
                  </form>
                </div>
              )}

              <div className="panel table-panel" style={{ gridColumn: role === 'CUSTOMER' ? 'auto' : '1 / -1' }}>
                <div className="panel-head" style={{ padding: '16px 20px 0' }}><div><h2>Loan Applications Queue</h2><p>Approval status</p></div></div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr><th>Loan ID</th><th>Amount</th><th>Purpose</th><th>Status</th><th>Review Action</th></tr>
                    </thead>
                    <tbody>
                      {loans.map(l => (
                        <tr key={l.id}>
                          <td className="mono">LN-{l.id}</td>
                          <td>{money(l.amount)}</td>
                          <td>{l.purpose}</td>
                          <td><span className={statusClass(l.status)}>{l.status}</span></td>
                          <td>
                            {isManager && l.status === 'PENDING_REVIEW' && (
                              <div className="queue-actions">
                                <button className="approve" disabled={busy} onClick={() => act(() => request(`/loans/${l.id}/approve`, { method: 'POST', body: JSON.stringify({ reason: 'Approved by Branch Manager' }) }), 'Loan approved & disbursed.')}>Approve &amp; Disburse</button>
                                <button className="reject" disabled={busy} onClick={() => setRejectionModal({ open: true, targetId: l.id, targetType: 'LOAN', reason: '' })}>Reject</button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {loans.length === 0 && <tr><td colSpan={5} style={{ textAlign: 'center', padding: '32px' }}>No loan applications recorded.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}

        <footer>
          <span>Northstar Bank · Online Banking Transaction Management System</span>
          <span><ShieldCheck size={14} /> Full 4-Role Hierarchy &amp; Saga Distributed Processing</span>
        </footer>
      </main>

      {/* ======================================================== */}
      {/* ==================== MODALS & DIALOGS ================== */}
      {/* ======================================================== */}

      {/* Rejection Reason Modal */}
      {rejectionModal.open && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-head">
              <h3>Specify Rejection Reason</h3>
              <button className="iconbtn" onClick={() => setRejectionModal({ open: false, targetId: null, targetType: 'TRANSACTION', reason: '' })}>×</button>
            </div>
            <p style={{ fontSize: '12px', color: '#64748b', marginBottom: '14px' }}>
              Every rejection must record an auditable reason for compliance and customer notification.
            </p>
            <form onSubmit={e => { e.preventDefault(); submitRejection(); }}>
              <Field label="Rejection Decision Reason">
                <input
                  required
                  autoFocus
                  value={rejectionModal.reason}
                  onChange={e => setRejectionModal({ ...rejectionModal, reason: e.target.value })}
                  placeholder="e.g. Transaction value exceeds unverified merchant limits"
                />
              </Field>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="secondary" onClick={() => setRejectionModal({ open: false, targetId: null, targetType: 'TRANSACTION', reason: '' })}>Cancel</button>
                <button type="submit" className="reject">Confirm Rejection</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Beneficiary Modal */}
      {beneficiaryModal && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-head">
              <h3>Add Verified Beneficiary</h3>
              <button className="iconbtn" onClick={() => setBeneficiaryModal(false)}>×</button>
            </div>
            <form onSubmit={e => {
              e.preventDefault();
              act(() => request('/beneficiaries', { method: 'POST', body: JSON.stringify(beneficiaryForm) }), 'Beneficiary verified & added.').then(() => {
                setBeneficiaryModal(false);
                setBeneficiaryForm({ accountNumber: '', beneficiaryName: '', nickname: '' });
              });
            }}>
              <Field label="Beneficiary Account Number">
                <input required value={beneficiaryForm.accountNumber} onChange={e => setBeneficiaryForm({ ...beneficiaryForm, accountNumber: e.target.value })} placeholder="Enter 16-digit account number" />
              </Field>
              <Field label="Beneficiary Full Name">
                <input required value={beneficiaryForm.beneficiaryName} onChange={e => setBeneficiaryForm({ ...beneficiaryForm, beneficiaryName: e.target.value })} placeholder="Account holder name" />
              </Field>
              <Field label="Nickname / Alias">
                <input required value={beneficiaryForm.nickname} onChange={e => setBeneficiaryForm({ ...beneficiaryForm, nickname: e.target.value })} placeholder="e.g. Landlord, Priya" />
              </Field>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="secondary" onClick={() => setBeneficiaryModal(false)}>Cancel</button>
                <button type="submit" className="primary">Save Beneficiary</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Customer Complaint Modal */}
      {complaintModal && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-head">
              <h3>Submit Customer Support Ticket</h3>
              <button className="iconbtn" onClick={() => setComplaintModal(false)}>×</button>
            </div>
            <form onSubmit={e => {
              e.preventDefault();
              act(() => request('/complaints', { method: 'POST', body: JSON.stringify(complaintForm) }), 'Support ticket submitted. A representative will review it.').then(() => {
                setComplaintModal(false);
                setComplaintForm({ accountNumber: '', category: 'TRANSACTION', subject: '', description: '' });
              });
            }}>
              <Field label="Related Account">
                <select value={complaintForm.accountNumber} onChange={e => setComplaintForm({ ...complaintForm, accountNumber: e.target.value })}>
                  <option value="">General inquiry</option>
                  {accounts.map(a => <option key={a.id} value={a.account_number}>{a.account_number} ({a.account_type})</option>)}
                </select>
              </Field>
              <Field label="Category">
                <select value={complaintForm.category} onChange={e => setComplaintForm({ ...complaintForm, category: e.target.value })}>
                  <option value="TRANSACTION">Transaction &amp; Transfer</option>
                  <option value="ACCOUNT">Account Management</option>
                  <option value="SECURITY">Security &amp; OTP</option>
                  <option value="GENERAL">General Banking</option>
                </select>
              </Field>
              <Field label="Subject">
                <input required value={complaintForm.subject} onChange={e => setComplaintForm({ ...complaintForm, subject: e.target.value })} placeholder="Brief summary of inquiry" />
              </Field>
              <Field label="Detailed Message">
                <textarea rows={3} required minLength={10} value={complaintForm.description} onChange={e => setComplaintForm({ ...complaintForm, description: e.target.value })} placeholder="Describe the issue with specific transaction references..." />
              </Field>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="secondary" onClick={() => setComplaintModal(false)}>Cancel</button>
                <button type="submit" className="primary">Submit Ticket</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Staff/Manager Reply Modal */}
      {replyModal.open && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-head">
              <h3>{replyModal.status === 'RESOLVED' ? 'Resolve Support Ticket' : 'Reply to Support Ticket'}</h3>
              <button className="iconbtn" onClick={() => setReplyModal({ open: false, ticketId: null, notes: '', status: 'IN_PROGRESS' })}>×</button>
            </div>
            <form onSubmit={e => {
              e.preventDefault();
              const endpoint = replyModal.status === 'RESOLVED'
                ? `/complaints/${replyModal.ticketId}/resolve`
                : `/complaints/${replyModal.ticketId}/reply`;
              act(() => request(endpoint, { method: 'POST', body: JSON.stringify({ notes: replyModal.notes, status: replyModal.status }) }), 'Ticket updated successfully.').then(() => {
                setReplyModal({ open: false, ticketId: null, notes: '', status: 'IN_PROGRESS' });
              });
            }}>
              <Field label="Response / Resolution Notes">
                <textarea rows={3} required value={replyModal.notes} onChange={e => setReplyModal({ ...replyModal, notes: e.target.value })} placeholder="Enter response to customer..." />
              </Field>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="secondary" onClick={() => setReplyModal({ open: false, ticketId: null, notes: '', status: 'IN_PROGRESS' })}>Cancel</button>
                <button type="submit" className="primary">{replyModal.status === 'RESOLVED' ? 'Mark Resolved' : 'Post Reply'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ icon, label, value, sub }: { icon: any; label: string; value: any; sub: string }) {
  return (
    <div className="stat">
      <div className="stat-icon">{icon}</div>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <span>{sub}</span>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: any }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

function Rule({ title, value }: { title: string; value: string }) {
  return <div className="rule"><span>{title}</span><b>{value}</b></div>;
}

function Step({ n, title, text }: { n: string; title: string; text: string }) {
  return (
    <div className="saga-step">
      <div>{n}</div>
      <section><b>{title}</b><small>{text}</small></section>
      <ChevronRight size={16} />
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="empty"><FileText size={23} /><span>{text}</span></div>;
}
