#!/bin/bash
set -e

PORT=${PORT:-10000}
DATA_DIR=${DATA_DIR:-/data}
mkdir -p "$DATA_DIR"

# Substitute PORT into Nginx configuration
mkdir -p /etc/nginx/conf.d
envsubst '${PORT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

# In Debian/Ubuntu, default site might be in /etc/nginx/sites-enabled/default
if [ -d /etc/nginx/sites-enabled ]; then
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    envsubst '${PORT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/sites-enabled/default 2>/dev/null || true
fi

# Set default security secrets if not provided
export PYTHONPATH=/app
export BANK_JWT_SECRET=${BANK_JWT_SECRET:-northstar-super-secret-jwt-token-key-32-chars-long}
export BANK_BOOTSTRAP_SECRET=${BANK_BOOTSTRAP_SECRET:-admin-bootstrap-secret-northstar-2026}
export INTERNAL_SECRET=${INTERNAL_SECRET:-internal-microservice-shared-secret-key-32}
export GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID:-}

echo "Starting Northstar Bank microservices..."
DB_PATH="$DATA_DIR/ledger.db" python -m uvicorn services.ledger.app.main:app --host 127.0.0.1 --port 8005 &
DB_PATH="$DATA_DIR/notification.db" python -m uvicorn services.notification.app.main:app --host 127.0.0.1 --port 8002 &
DB_PATH="$DATA_DIR/identity.db" NOTIFICATION_URL=http://127.0.0.1:8002 python -m uvicorn services.identity.app.main:app --host 127.0.0.1 --port 8001 &
DB_PATH="$DATA_DIR/account.db" LEDGER_URL=http://127.0.0.1:8005 TRANSACTION_URL=http://127.0.0.1:8004 python -m uvicorn services.account.app.main:app --host 127.0.0.1 --port 8003 &
DB_PATH="$DATA_DIR/transaction.db" ACCOUNT_URL=http://127.0.0.1:8003 LEDGER_URL=http://127.0.0.1:8005 NOTIFICATION_URL=http://127.0.0.1:8002 python -m uvicorn services.transaction.app.main:app --host 127.0.0.1 --port 8004 &

sleep 2

echo "Starting Nginx on port $PORT..."
nginx -g "daemon off;"
