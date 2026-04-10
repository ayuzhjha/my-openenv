"""
tasks/task_easy.py
EASY: Backend service fails because PORT env var is set to 5000 but nginx expects 8080.
Fix: Read backend.env, find PORT=5000, change to PORT=8080, restart backend.
"""


def _grade_easy(state: dict, history: list) -> float:
    """
    Grade the easy task.
    Full score (1.0) requires:
      1. PORT changed to 8080 in backend.env
      2. backend service restarted after the fix
    Partial credit for discovery and partial fixes.
    """
    score = 0.0
    files = state.get("files", {})
    services = state.get("services", {})

    # Check if backend.env was read (discovery)
    files_read = set(state.get("files_read", []))
    if "backend.env" in files_read:
        score += 0.1

    # Check if nginx config was read
    if "/etc/nginx/nginx.conf" in files_read:
        score += 0.1

    # Check if PORT was fixed
    backend_env = files.get("backend.env", "")
    port_fixed = "PORT=8080" in backend_env
    if port_fixed:
        score += 0.4

    # Check if backend was restarted after fix
    backend_running = services.get("backend") == "running"
    if port_fixed and backend_running:
        score += 0.4

    return max(0.001, min(score, 0.999))


TASK_EASY = {
    "id": "task_easy",
    "name": "Wrong Port Configuration",
    "difficulty": "easy",
    "description": (
        "The backend service is crashed. Users are seeing 502 Bad Gateway errors. "
        "Nginx is configured to proxy to port 8080 but the backend is listening on the wrong port. "
        "Find and fix the misconfiguration."
    ),
    "max_steps": 15,
    "initial_state": {
        "services": {
            "nginx": "running",
            "backend": "crashed",
            "redis": "running",
        },
        "env_vars": {
            "PORT": "5000",
            "APP_ENV": "production",
            "LOG_LEVEL": "info",
        },
        "files": {
            "/etc/nginx/nginx.conf": (
                "worker_processes auto;\n"
                "events { worker_connections 1024; }\n"
                "http {\n"
                "    upstream backend {\n"
                "        server 127.0.0.1:8080;\n"
                "    }\n"
                "    server {\n"
                "        listen 80;\n"
                "        location / {\n"
                "            proxy_pass http://backend;\n"
                "            proxy_set_header Host $host;\n"
                "        }\n"
                "    }\n"
                "}\n"
            ),
            "backend.env": (
                "# Backend service configuration\n"
                "PORT=5000\n"
                "APP_ENV=production\n"
                "LOG_LEVEL=info\n"
                "DB_HOST=localhost\n"
                "DB_PORT=5432\n"
            ),
            "/var/log/nginx/error.log": (
                "2024-01-15 10:23:01 [error] connect() failed (111: Connection refused) "
                "while connecting to upstream, upstream: \"http://127.0.0.1:8080/\"\n"
                "2024-01-15 10:23:02 [error] no live upstreams while connecting to upstream\n"
                "2024-01-15 10:23:03 [error] 502 Bad Gateway\n"
            ),
            "/var/log/backend.log": (
                "2024-01-15 10:22:55 INFO  Starting backend server...\n"
                "2024-01-15 10:22:55 INFO  Listening on port 5000\n"
                "2024-01-15 10:22:55 INFO  Backend ready\n"
                "2024-01-15 10:23:00 ERROR Cannot connect to nginx upstream\n"
                "2024-01-15 10:23:01 FATAL Port binding conflict -- shutting down\n"
            ),
            "/etc/systemd/system/backend.service": (
                "[Unit]\n"
                "Description=Backend API Service\n"
                "After=network.target\n\n"
                "[Service]\n"
                "Type=simple\n"
                "EnvironmentFile=/app/backend.env\n"
                "ExecStart=/usr/bin/node /app/server.js\n"
                "Restart=on-failure\n\n"
                "[Install]\n"
                "WantedBy=multi-user.target\n"
            ),
        },
        "logs": [
            "Jan 15 10:23:01 prod-server nginx[1234]: 502 Bad Gateway",
            "Jan 15 10:23:01 prod-server nginx[1234]: upstream connect error on 127.0.0.1:8080",
            "Jan 15 10:23:01 prod-server systemd[1]: backend.service: Main process exited",
            "Jan 15 10:23:01 prod-server systemd[1]: backend.service: Failed with result exit-code",
            "Jan 15 10:22:55 prod-server backend[5678]: Listening on port 5000",
        ],
        "directories": {
            "/etc/nginx": ["/etc/nginx/nginx.conf", "/etc/nginx/sites-enabled/"],
            "/var/log": ["/var/log/nginx/", "/var/log/backend.log", "/var/log/syslog"],
            "/app": ["backend.env", "/etc/systemd/system/backend.service"],
        },
        "relevant_files": ["backend.env", "/etc/nginx/nginx.conf", "/var/log/nginx/error.log"],
        "relevant_service_checks": ["backend", "nginx"],
        "relevant_log_services": ["nginx", "backend"],
        "relevant_commands": {
            "netstat": True,
            "ss -tlnp": True,
            "ps aux": True,
        },
        "allowed_shell_commands": {
            "netstat -tlnp": (
                "Proto Recv-Q Send-Q Local Address  State   PID/Program\n"
                "tcp   0      0     0.0.0.0:5000   LISTEN  5678/node\n"
                "tcp   0      0     0.0.0.0:80     LISTEN  1234/nginx\n"
            ),
            "ss -tlnp": (
                "State  Recv-Q Send-Q Local Address:Port\n"
                "LISTEN 0      128    0.0.0.0:5000        users:((node,pid=5678))\n"
                "LISTEN 0      128    0.0.0.0:80          users:((nginx,pid=1234))\n"
            ),
            "ps aux": (
                "USER  PID  %CPU %MEM COMMAND\n"
                "nginx 1234  0.1  0.5 nginx: master process\n"
                "node  5678  0.0  1.2 node /app/server.js\n"
                "redis 9012  0.2  2.1 redis-server *:6379\n"
            ),
            "curl localhost": "curl: (7) Failed to connect to localhost port 80",
            "curl localhost:8080": "curl: (7) Failed to connect to localhost port 8080",
            "curl localhost:5000": '{"status":"ok","message":"Backend running on port 5000"}',
        },
        "success_edits": {
            "backend.env": {"PORT": "8080"},
        },
        "critical_healthy_services": ["nginx", "redis"],
        "restart_effects": {
            "backend": {
                "new_status": "running",
                "logs": [
                    "Jan 15 10:30:00 prod-server systemd[1]: Starting backend.service...",
                    "Jan 15 10:30:01 prod-server backend[6789]: Loaded config from /app/backend.env",
                    "Jan 15 10:30:01 prod-server backend[6789]: Listening on port 8080",
                    "Jan 15 10:30:01 prod-server systemd[1]: Started backend.service",
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
    "grader": _grade_easy,
}
