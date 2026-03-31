#!/bin/sh
chown -R lapsora:lapsora /app/data

# Determine the data directory (default: /app/data)
DATA_DIR="${LAPSORA_DATA_DIR:-/app/data}"
FULLCHAIN="$DATA_DIR/certs/fullchain.pem"
PRIVKEY="$DATA_DIR/certs/privkey.pem"

# Conditionally enable TLS if certs exist and TLS is not explicitly disabled
if [ -f "$FULLCHAIN" ] && [ -f "$PRIVKEY" ] && [ "${LAPSORA_TLS_ENABLED:-true}" != "false" ]; then
    # Launch HTTPS on port 443
    exec gosu lapsora uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 443 \
        --ssl-certfile "$FULLCHAIN" \
        --ssl-keyfile "$PRIVKEY"
else
    # Default: plain HTTP on port 8000 (or pass-through CMD args)
    exec gosu lapsora "$@"
fi
