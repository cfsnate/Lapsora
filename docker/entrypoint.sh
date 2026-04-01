#!/bin/sh
chown -R lapsora:lapsora /app/data

# Determine the data directory (default: /app/data)
DATA_DIR="${LAPSORA_DATA_DIR:-/app/data}"
FULLCHAIN="$DATA_DIR/certs/fullchain.pem"
PRIVKEY="$DATA_DIR/certs/privkey.pem"

# Conditionally enable TLS if certs exist and TLS is not explicitly disabled
if [ -f "$FULLCHAIN" ] && [ -f "$PRIVKEY" ] && [ "${LAPSORA_TLS_ENABLED:-true}" != "false" ]; then
    # Launch a background HTTP listener on port 80 for:
    #   - ACME challenge validation during certificate renewal
    #   - HTTP → HTTPS redirects (handled by the app's redirect middleware)
    gosu lapsora uvicorn app.main:app --host 0.0.0.0 --port 80 &

    # Primary HTTPS listener on port 443
    exec gosu lapsora uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 443 \
        --ssl-certfile "$FULLCHAIN" \
        --ssl-keyfile "$PRIVKEY"
else
    # No TLS certs yet — plain HTTP on port 80.
    # Docker Compose maps host port 8000 → container port 80,
    # so the app is reachable on both :80 and :8000 externally.
    # Port 80 is required for ACME HTTP-01 challenge validation.
    exec gosu lapsora "$@"
fi
