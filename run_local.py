#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import signal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Read .env if available
env_file = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

JWT_SECRET = os.environ.get('BANK_JWT_SECRET', 'northstar-super-secret-jwt-token-key-32-chars-long')
BOOT_SECRET = os.environ.get('BANK_BOOTSTRAP_SECRET', 'admin-bootstrap-secret-northstar-2026')
INTERNAL_SECRET = os.environ.get('INTERNAL_SECRET', 'internal-microservice-shared-secret-key-32')

python_bin = os.path.join(BASE_DIR, '.venv', 'bin', 'python3')
if not os.path.exists(python_bin):
    python_bin = sys.executable

node_path = "/Users/charrita/.nvm/versions/node/v20.20.2/bin"
current_path = os.environ.get('PATH', '')
if node_path not in current_path:
    os.environ['PATH'] = f"{node_path}:{current_path}"

services = [
    {
        'name': 'ledger-service',
        'cmd': [python_bin, '-m', 'uvicorn', 'services.ledger.app.main:app', '--host', '127.0.0.1', '--port', '8005'],
        'env': {
            'PYTHONPATH': BASE_DIR,
            'DB_PATH': os.path.join(DATA_DIR, 'ledger.db'),
            'INTERNAL_SECRET': INTERNAL_SECRET,
            'BANK_JWT_SECRET': JWT_SECRET,
        }
    },
    {
        'name': 'notification-service',
        'cmd': [python_bin, '-m', 'uvicorn', 'services.notification.app.main:app', '--host', '127.0.0.1', '--port', '8002'],
        'env': {
            'PYTHONPATH': BASE_DIR,
            'DB_PATH': os.path.join(DATA_DIR, 'notification.db'),
            'INTERNAL_SECRET': INTERNAL_SECRET,
            'BANK_JWT_SECRET': JWT_SECRET,
            'SMTP_HOST': os.environ.get('SMTP_HOST', ''),
            'SMTP_PORT': os.environ.get('SMTP_PORT', '587'),
            'SMTP_USER': os.environ.get('SMTP_USER', ''),
            'SMTP_PASSWORD': os.environ.get('SMTP_PASSWORD', ''),
            'SMTP_FROM': os.environ.get('SMTP_FROM', ''),
            'SMTP_STARTTLS': os.environ.get('SMTP_STARTTLS', 'true'),
        }
    },
    {
        'name': 'identity-service',
        'cmd': [python_bin, '-m', 'uvicorn', 'services.identity.app.main:app', '--host', '127.0.0.1', '--port', '8001'],
        'env': {
            'PYTHONPATH': BASE_DIR,
            'DB_PATH': os.path.join(DATA_DIR, 'identity.db'),
            'BANK_JWT_SECRET': JWT_SECRET,
            'BANK_BOOTSTRAP_SECRET': BOOT_SECRET,
            'INTERNAL_SECRET': INTERNAL_SECRET,
            'NOTIFICATION_URL': 'http://127.0.0.1:8002',
            'GOOGLE_CLIENT_ID': os.environ.get('GOOGLE_CLIENT_ID', ''),
        }
    },
    {
        'name': 'account-service',
        'cmd': [python_bin, '-m', 'uvicorn', 'services.account.app.main:app', '--host', '127.0.0.1', '--port', '8003'],
        'env': {
            'PYTHONPATH': BASE_DIR,
            'DB_PATH': os.path.join(DATA_DIR, 'account.db'),
            'BANK_JWT_SECRET': JWT_SECRET,
            'INTERNAL_SECRET': INTERNAL_SECRET,
            'LEDGER_URL': 'http://127.0.0.1:8005',
            'TRANSACTION_URL': 'http://127.0.0.1:8004',
        }
    },
    {
        'name': 'transaction-service',
        'cmd': [python_bin, '-m', 'uvicorn', 'services.transaction.app.main:app', '--host', '127.0.0.1', '--port', '8004'],
        'env': {
            'PYTHONPATH': BASE_DIR,
            'DB_PATH': os.path.join(DATA_DIR, 'transaction.db'),
            'BANK_JWT_SECRET': JWT_SECRET,
            'INTERNAL_SECRET': INTERNAL_SECRET,
            'ACCOUNT_URL': 'http://127.0.0.1:8003',
            'LEDGER_URL': 'http://127.0.0.1:8005',
            'NOTIFICATION_URL': 'http://127.0.0.1:8002',
            'RABBITMQ_HOST': '127.0.0.1',
        }
    },
    {
        'name': 'frontend',
        'cmd': ['npm', 'run', 'dev'],
        'cwd': os.path.join(BASE_DIR, 'frontend'),
        'env': {}
    }
]

processes = []

def cleanup(sig=None, frame=None):
    print("\nStopping all services...")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(1)
    for p in processes:
        try:
            p.kill()
        except Exception:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

print("Starting Northstar Bank microservices and frontend...")
for svc in services:
    env = os.environ.copy()
    env.update(svc.get('env', {}))
    cwd = svc.get('cwd', BASE_DIR)
    p = subprocess.Popen(
        svc['cmd'],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    processes.append(p)
    print(f"[{svc['name']}] Started (PID: {p.pid})")

time.sleep(2)
print("\nAll services are active.")
print("Web application URL: http://localhost:5173\n")

# Stream logs
import threading
def stream_output(proc, name):
    for line in iter(proc.stdout.readline, ''):
        print(f"[{name}] {line.strip()}", flush=True)

threads = []
for p, svc in zip(processes, services):
    t = threading.Thread(target=stream_output, args=(p, svc['name']), daemon=True)
    t.start()
    threads.append(t)

try:
    while True:
        for p, svc in zip(processes, services):
            if p.poll() is not None:
                print(f"[{svc['name']}] Exited with code {p.returncode}")
                cleanup()
        time.sleep(1)
except KeyboardInterrupt:
    cleanup()
