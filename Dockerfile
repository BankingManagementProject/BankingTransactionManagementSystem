# ==============================================================================
# Stage 1: Build the React Frontend
# ==============================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
ARG VITE_GOOGLE_CLIENT_ID
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
RUN npm run build

# ==============================================================================
# Stage 2: Production Server (Python 3.11 + Nginx)
# ==============================================================================
FROM python:3.11-slim

# Install Nginx, gettext (for envsubst), and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    gettext-base \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install all backend microservice dependencies
RUN pip install --no-cache-dir \
    fastapi==0.115.6 \
    uvicorn[standard]==0.34.0 \
    PyJWT==2.10.1 \
    httpx==0.28.1 \
    pika==1.3.2

# Copy backend application code
COPY services/ /app/services/
COPY shared/ /app/shared/
COPY shared_security.py /app/shared_security.py

# Copy frontend static build artifacts into Nginx html directory
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

# Create data directory for SQLite databases
RUN mkdir -p /data

# Configure Nginx template and startup script
COPY docker-nginx.conf /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENV PORT=10000
ENV PYTHONPATH=/app
ENV DATA_DIR=/data

EXPOSE 10000

CMD ["/app/docker-entrypoint.sh"]
