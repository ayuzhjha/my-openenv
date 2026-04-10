"""
tasks/task_hard.py
HARD: Cascade failure with misleading logs.
Symptoms: Payment service is down. Logs show DB errors (red herring).
Real cause: 
  1. A certificate expired (SSL_CERT_PATH points to expired cert)
  2. Payment gateway URL changed (PAYMENT_GW_URL is outdated)
  3. Worker queue is overloaded because retry logic loops (MAX_RETRIES=0 means infinite)
Multi-step reasoning required. Logs deliberately mislead toward DB issues.
"""
import re


def _grade_hard(state: dict, history: list) -> float:
    """
    Grade the hard task. Three independent fixes required.
    """
    score = 0.0
    files = state.get("files", {})
    services = state.get("services", {})
    files_read = set(state.get("files_read", []))

    # Discovery bonuses
    if "/app/payment/config.env" in files_read:
        score += 0.05
    if "/etc/ssl/certs/payment.crt" in files_read:
        score += 0.05
    if "/var/log/payment.log" in files_read:
        score += 0.05
    if "/app/payment/worker.py" in files_read:
        score += 0.05

    payment_env = files.get("/app/payment/config.env", "")

    # Fix 1: SSL cert path fixed
    ssl_fixed = "SSL_CERT_PATH=/etc/ssl/certs/payment-new.crt" in payment_env
    if ssl_fixed:
        score += 0.15

    # Fix 2: Payment gateway URL updated
    gw_fixed = "PAYMENT_GW_URL=https://api.stripe.com/v2" in payment_env
    if gw_fixed:
        score += 0.15

    # Fix 3: MAX_RETRIES set to non-zero reasonable value
    retry_match = re.search(r"MAX_RETRIES=(\d+)", payment_env)
    retry_fixed = retry_match and 1 <= int(retry_match.group(1)) <= 10
    if retry_fixed:
        score += 0.15

    # Services restarted
    payment_up = services.get("payment") == "running"
    worker_up = services.get("worker") == "running"

    if ssl_fixed and gw_fixed and retry_fixed:
        if payment_up:
            score += 0.15
        if worker_up:
            score += 0.15

    return max(0.001, min(score, 0.999))


TASK_HARD = {
    "id": "task_hard",
    "name": "Payment System Cascade Failure",
    "difficulty": "hard",
    "description": (
        "CRITICAL: Payment processing is completely down. Revenue impact: $50k/hour. "
        "Initial logs suggest database connectivity issues, but the DB team confirms postgres is healthy. "
        "Multiple independent misconfigurations are causing a cascade failure. "
        "Misleading error messages will attempt to divert your investigation. "
        "Identify all root causes and restore full payment processing capability."
    ),
    "max_steps": 30,
    "initial_state": {
        "services": {
            "nginx": "running",
            "api": "running",
            "payment": "crashed",
            "postgres": "running",
            "redis": "running",
            "worker": "overloaded",
            "monitoring": "running",
        },
        "env_vars": {},
        "files": {
            "/app/payment/config.env": (
                "# Payment Service Configuration\n"
                "SERVICE_PORT=4000\n"
                "PAYMENT_GW_URL=https://api.stripe.com/v1\n"
                "PAYMENT_GW_TIMEOUT=30\n"
                "SSL_CERT_PATH=/etc/ssl/certs/payment.crt\n"
                "SSL_KEY_PATH=/etc/ssl/private/payment.key\n"
                "DB_HOST=localhost\n"
                "DB_PORT=5432\n"
                "DB_NAME=payments\n"
                "MAX_RETRIES=0\n"
                "RETRY_DELAY=5\n"
                "LOG_LEVEL=info\n"
            ),
            "/etc/ssl/certs/payment.crt": (
                "Certificate:\n"
                "  Subject: CN=payment.internal\n"
                "  Issuer: Let's Encrypt Authority X3\n"
                "  Validity:\n"
                "    Not Before: Jan 01 2023\n"
                "    Not After:  Jan 01 2024  <-- EXPIRED\n"
                "  SHA256 Fingerprint: AB:CD:EF:...\n"
            ),
            "/etc/ssl/certs/payment-new.crt": (
                "Certificate:\n"
                "  Subject: CN=payment.internal\n"
                "  Issuer: Let's Encrypt Authority X3\n"
                "  Validity:\n"
                "    Not Before: Jan 01 2024\n"
                "    Not After:  Jan 01 2025  <-- VALID\n"
                "  SHA256 Fingerprint: 12:34:56:...\n"
            ),
            "/app/payment/worker.py": (
                "import os, time\n"
                "MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))\n"
                "# BUG: If MAX_RETRIES=0, range(0) = empty, falls through to while True\n"
                "def process_payment(job):\n"
                "    for attempt in range(MAX_RETRIES):\n"
                "        result = submit_to_gateway(job)\n"
                "        if result.success: return result\n"
                "    # Fallback: infinite retry (DANGEROUS when MAX_RETRIES=0)\n"
                "    while True:\n"
                "        result = submit_to_gateway(job)\n"
                "        if result.success: return result\n"
                "        time.sleep(RETRY_DELAY)\n"
            ),
            "/app/payment/gateway.py": (
                "GATEWAY_URL = os.getenv('PAYMENT_GW_URL')\n"
                "# Stripe deprecated v1 endpoint Jan 2024\n"
                "# New endpoint: https://api.stripe.com/v2\n"
                "def submit_to_gateway(job):\n"
                "    resp = requests.post(f'{GATEWAY_URL}/charges', ...)\n"
                "    if resp.status_code == 410:  # Gone\n"
                "        raise DeprecatedEndpointError('API endpoint deprecated')\n"
                "    return resp\n"
            ),
            "/var/log/payment.log": (
                "2024-01-15 09:00:01 INFO  Payment service starting...\n"
                "2024-01-15 09:00:02 ERROR SSL: certificate verify failed: certificate has expired\n"
                "2024-01-15 09:00:02 WARN  Falling back to non-SSL (INSECURE MODE)\n"
                "2024-01-15 09:00:03 ERROR Connection to stripe: 410 Gone\n"
                "2024-01-15 09:00:03 ERROR DeprecatedEndpointError: API endpoint deprecated\n"
                "2024-01-15 09:00:04 WARN  Retrying payment job a7f3... (attempt ∞)\n"
                "2024-01-15 09:00:09 WARN  Retrying payment job a7f3... (attempt ∞)\n"
                "2024-01-15 09:00:14 WARN  Retrying payment job a7f3... (attempt ∞)\n"
                "2024-01-15 09:00:19 ERROR Worker queue at 100% capacity — dropping new jobs\n"
                "2024-01-15 09:00:20 FATAL Service entering crash loop\n"
            ),
            "/var/log/postgres.log": (
                "2024-01-15 09:00:01 LOG  database system is ready to accept connections\n"
                "2024-01-15 09:00:03 LOG  connection received: host=127.0.0.1\n"
                "2024-01-15 09:00:03 LOG  connection authorized: user=payments\n"
                "2024-01-15 09:00:04 ERROR could not connect to server: Connection refused\n"
                "2024-01-15 09:00:04 DETAIL: Is the server running on host 'localhost' (127.0.0.1)\n"
                "             and accepting TCP/IP connections on port 5432?\n"
                "# ^ This error is from a DIFFERENT service attempting connection, not postgres itself\n"
            ),
            "/var/log/worker.log": (
                "2024-01-15 09:00:04 INFO  Worker starting job queue processing\n"
                "2024-01-15 09:00:04 INFO  Picked up job a7f3 (payment_charge)\n"
                "2024-01-15 09:00:05 WARN  Job a7f3 failed, retrying... (∞ loop)\n"
                "2024-01-15 09:01:00 ERROR Queue depth: 847 pending jobs\n"
                "2024-01-15 09:01:30 ERROR Queue depth: 1203 pending jobs\n"
                "2024-01-15 09:02:00 FATAL Worker OOM — queue depth 2000+, killing processes\n"
            ),
            "/var/log/nginx/error.log": (
                "2024-01-15 09:00:20 [error] connect() failed: upstream: http://127.0.0.1:4000\n"
                "2024-01-15 09:00:20 [error] 502 Bad Gateway /api/payment\n"
            ),
            "/etc/systemd/system/payment.service": (
                "[Unit]\n"
                "Description=Payment Processing Service\n"
                "After=network.target postgresql.service\n\n"
                "[Service]\n"
                "Type=simple\n"
                "EnvironmentFile=/app/payment/config.env\n"
                "ExecStart=/usr/bin/python3 /app/payment/server.py\n"
                "Restart=on-failure\n"
                "RestartSec=10\n\n"
                "[Install]\n"
                "WantedBy=multi-user.target\n"
            ),
            "/etc/systemd/system/worker.service": (
                "[Unit]\n"
                "Description=Payment Worker Service\n\n"
                "[Service]\n"
                "Type=simple\n"
                "EnvironmentFile=/app/payment/config.env\n"
                "ExecStart=/usr/bin/python3 /app/payment/worker.py\n"
                "Restart=on-failure\n\n"
                "[Install]\n"
                "WantedBy=multi-user.target\n"
            ),
            "/app/README.md": (
                "# Production Services\n\n"
                "## Recent Changes (Jan 2024)\n"
                "- Stripe migrated from v1 to v2 API endpoint\n"
                "- SSL certificates renewed — new cert at /etc/ssl/certs/payment-new.crt\n"
                "- DB team confirmed postgres is healthy (check app configs, not DB)\n"
                "- Worker retry logic: set MAX_RETRIES >= 1 to prevent infinite loops\n"
            ),
        },
        "logs": [
            "Jan 15 09:00:02 prod-pay payment[3333]: ERROR SSL certificate has expired",
            "Jan 15 09:00:03 prod-pay payment[3333]: ERROR 410 Gone — Stripe v1 deprecated",
            "Jan 15 09:00:04 prod-pay postgres[5432]: ERROR could not connect (misleading — see logs)",
            "Jan 15 09:00:04 prod-pay worker[4444]: WARN infinite retry loop detected",
            "Jan 15 09:00:19 prod-pay worker[4444]: FATAL queue at 100% capacity",
            "Jan 15 09:00:20 prod-pay systemd[1]: payment.service: Failed",
            "Jan 15 09:00:20 prod-pay nginx[1234]: 502 /api/payment",
        ],
        "directories": {
            "/app/payment": [
                "/app/payment/config.env",
                "/app/payment/server.py",
                "/app/payment/worker.py",
                "/app/payment/gateway.py",
            ],
            "/etc/ssl/certs": [
                "/etc/ssl/certs/payment.crt",
                "/etc/ssl/certs/payment-new.crt",
            ],
            "/var/log": [
                "/var/log/payment.log",
                "/var/log/worker.log",
                "/var/log/postgres.log",
                "/var/log/nginx/",
            ],
            "/app": ["/app/payment/", "/app/README.md"],
        },
        "relevant_files": [
            "/app/payment/config.env",
            "/var/log/payment.log",
            "/etc/ssl/certs/payment.crt",
            "/etc/ssl/certs/payment-new.crt",
            "/app/payment/worker.py",
            "/app/payment/gateway.py",
            "/app/README.md",
        ],
        "relevant_service_checks": ["payment", "worker", "postgres"],
        "relevant_log_services": ["payment", "worker"],
        "relevant_commands": {
            "openssl": True,
            "curl.*stripe": True,
        },
        "allowed_shell_commands": {
            "openssl x509 -in /etc/ssl/certs/payment.crt -noout -dates": (
                "notBefore=Jan  1 00:00:00 2023 GMT\n"
                "notAfter=Jan  1 00:00:00 2024 GMT\n"
                "Certificate has EXPIRED"
            ),
            "openssl x509 -in /etc/ssl/certs/payment-new.crt -noout -dates": (
                "notBefore=Jan  1 00:00:00 2024 GMT\n"
                "notAfter=Jan  1 00:00:00 2025 GMT\n"
                "Certificate is VALID"
            ),
            "curl https://api.stripe.com/v1/charges": (
                "HTTP/1.1 410 Gone\n"
                "{\"error\": \"API version v1 has been deprecated. Please use v2.\"}"
            ),
            "curl https://api.stripe.com/v2/charges": "HTTP/1.1 401 Unauthorized (expected — no API key)",
            "psql -U payments -c 'SELECT 1'": "psql: error: connection to server failed: no pg_hba.conf",
            "systemctl status postgres": (
                "● postgresql.service - PostgreSQL Database\n"
                "   Active: active (running) since Mon 2024-01-15\n"
                "   Note: DB is HEALTHY — issue is in application config"
            ),
        },
        "success_edits": {
            "/app/payment/config.env": {
                "SSL_CERT_PATH": "/etc/ssl/certs/payment-new.crt",
                "PAYMENT_GW_URL": "https://api.stripe.com/v2",
                "__wrong_keys__": ["PAYMENT_GW_URL"],
            },
        },
        "critical_healthy_services": ["nginx", "api", "postgres", "redis", "monitoring"],
        "restart_effects": {
            "payment": {
                "new_status": "running",
                "logs": [
                    "Jan 15 10:00:00 prod-pay systemd[1]: Starting payment.service...",
                    "Jan 15 10:00:01 prod-pay payment[8888]: SSL cert loaded: VALID (expires 2025)",
                    "Jan 15 10:00:01 prod-pay payment[8888]: Connected to Stripe v2 API: OK",
                    "Jan 15 10:00:01 prod-pay payment[8888]: Listening on port 4000",
                ],
                "reward": 0.0,
            },
            "worker": {
                "new_status": "running",
                "logs": [
                    "Jan 15 10:00:02 prod-pay worker[9999]: Starting with MAX_RETRIES from config",
                    "Jan 15 10:00:02 prod-pay worker[9999]: Queue cleared, processing normally",
                ],
                "reward": 0.0,
            },
        },
        "task_solved": False,
        "files_read": [],
        "services_checked": [],
        "logs_viewed": [],
        "edits_made": {},
    },
    "grader": _grade_hard,
}
