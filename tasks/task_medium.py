"""
tasks/task_medium.py
MEDIUM: Two-layer failure — wrong DB host + missing required environment variable.
The API service is returning 500 errors. Investigation reveals:
  1. DB_HOST points to wrong hostname (db-old.internal instead of db.internal)
  2. SECRET_KEY env var is missing entirely (causes startup crash in auth middleware)
Fix requires reading multiple files, identifying both issues, fixing both, and restarting.
"""


def _grade_medium(state: dict, history: list) -> float:
    """
    Grade the medium task.
    Requires fixing BOTH: DB_HOST and adding SECRET_KEY.
    Partial credit for each layer fixed.
    """
    score = 0.0
    files = state.get("files", {})
    services = state.get("services", {})
    files_read = set(state.get("files_read", []))

    # Discovery rewards
    if "/app/api.env" in files_read:
        score += 0.05
    if "/app/config/database.yml" in files_read:
        score += 0.05
    if "/var/log/api.log" in files_read:
        score += 0.05

    # Fix 1: DB_HOST corrected
    api_env = files.get("/app/api.env", "")
    db_fixed = "DB_HOST=db.internal" in api_env and "DB_HOST=db-old.internal" not in api_env
    if db_fixed:
        score += 0.25

    # Fix 2: SECRET_KEY added
    secret_added = "SECRET_KEY=" in api_env and "SECRET_KEY=\n" not in api_env
    if secret_added:
        score += 0.25

    # Service restarted after fixes
    api_running = services.get("api") == "running"
    if db_fixed and secret_added and api_running:
        score += 0.35

    return min(score, 1.0)


TASK_MEDIUM = {
    "id": "task_medium",
    "name": "Double-Layer API Failure",
    "difficulty": "medium",
    "description": (
        "The API service is returning 500 Internal Server Error for all requests. "
        "The monitoring dashboard shows intermittent DB connection failures AND auth middleware crashes. "
        "Two separate misconfigurations must be identified and fixed to restore service."
    ),
    "max_steps": 20,
    "initial_state": {
        "services": {
            "nginx": "running",
            "api": "crashed",
            "postgres": "running",
            "redis": "running",
            "worker": "running",
        },
        "env_vars": {
            "DB_HOST": "db-old.internal",
            "DB_PORT": "5432",
            "APP_PORT": "3000",
        },
        "files": {
            "/app/api.env": (
                "# API Service Environment\n"
                "APP_PORT=3000\n"
                "APP_ENV=production\n"
                "DB_HOST=db-old.internal\n"
                "DB_PORT=5432\n"
                "DB_NAME=appdb\n"
                "DB_USER=apiuser\n"
                "DB_PASS=s3cr3t\n"
                "REDIS_HOST=localhost\n"
                "REDIS_PORT=6379\n"
                "LOG_LEVEL=info\n"
                "# SECRET_KEY=  <-- removed during migration, forgot to re-add\n"
            ),
            "/app/config/database.yml": (
                "default: &default\n"
                "  adapter: postgresql\n"
                "  pool: 5\n"
                "  timeout: 5000\n"
                "\n"
                "production:\n"
                "  <<: *default\n"
                "  host: <%= ENV['DB_HOST'] %>\n"
                "  port: <%= ENV['DB_PORT'] %>\n"
                "  database: appdb\n"
                "  username: apiuser\n"
            ),
            "/app/config/app.rb": (
                "# Application configuration\n"
                "module App\n"
                "  class Config\n"
                "    def initialize\n"
                "      @secret_key = ENV.fetch('SECRET_KEY') { raise 'SECRET_KEY not set!' }\n"
                "      @db_host = ENV['DB_HOST']\n"
                "    end\n"
                "  end\n"
                "end\n"
            ),
            "/var/log/api.log": (
                "2024-01-15 14:00:01 INFO  Starting API server v2.3.1\n"
                "2024-01-15 14:00:02 INFO  Loading configuration...\n"
                "2024-01-15 14:00:02 ERROR KeyError: SECRET_KEY not set!\n"
                "2024-01-15 14:00:02 FATAL App::Config initialization failed\n"
                "2024-01-15 14:00:02 FATAL Server startup aborted\n"
                "2024-01-15 14:00:05 INFO  Retry attempt 1/3...\n"
                "2024-01-15 14:00:05 ERROR KeyError: SECRET_KEY not set!\n"
                "2024-01-15 14:00:08 INFO  Retry attempt 2/3...\n"
                "2024-01-15 14:00:08 ERROR KeyError: SECRET_KEY not set!\n"
                "2024-01-15 14:00:11 FATAL Max retries exceeded, giving up\n"
            ),
            "/var/log/nginx/access.log": (
                "127.0.0.1 - - [15/Jan/2024:14:00:15] \"GET /api/health HTTP/1.1\" 502 0\n"
                "127.0.0.1 - - [15/Jan/2024:14:00:16] \"GET /api/users HTTP/1.1\" 502 0\n"
                "127.0.0.1 - - [15/Jan/2024:14:00:17] \"POST /api/login HTTP/1.1\" 502 0\n"
            ),
            "/var/log/postgres.log": (
                "2024-01-15 14:00:01 LOG  database system is ready to accept connections\n"
                "2024-01-15 14:01:00 LOG  connection received: host=127.0.0.1 port=45123\n"
            ),
            "/etc/hosts": (
                "127.0.0.1 localhost\n"
                "::1 localhost\n"
                "10.0.1.5 db.internal\n"
                "10.0.1.8 cache.internal\n"
                "# 10.0.1.3 db-old.internal  <- decommissioned Jan 2024\n"
            ),
            "/etc/systemd/system/api.service": (
                "[Unit]\n"
                "Description=API Application Service\n"
                "After=network.target postgresql.service redis.service\n\n"
                "[Service]\n"
                "Type=simple\n"
                "EnvironmentFile=/app/api.env\n"
                "ExecStart=/usr/bin/ruby /app/server.rb\n"
                "Restart=on-failure\n"
                "RestartSec=3\n\n"
                "[Install]\n"
                "WantedBy=multi-user.target\n"
            ),
        },
        "logs": [
            "Jan 15 14:00:02 prod-api api[2345]: FATAL KeyError: SECRET_KEY not set!",
            "Jan 15 14:00:02 prod-api systemd[1]: api.service: Main process exited with code 1",
            "Jan 15 14:00:05 prod-api systemd[1]: api.service: Scheduled restart job",
            "Jan 15 14:00:11 prod-api systemd[1]: api.service: Start request repeated too quickly",
            "Jan 15 14:00:11 prod-api systemd[1]: api.service: Failed -- see 'journalctl -xe'",
            "Jan 15 14:00:15 prod-api nginx[1234]: 502 Bad Gateway /api/health",
        ],
        "directories": {
            "/app": ["/app/api.env", "/app/config/", "/app/server.rb"],
            "/app/config": ["/app/config/database.yml", "/app/config/app.rb"],
            "/var/log": ["/var/log/api.log", "/var/log/nginx/", "/var/log/postgres.log"],
            "/etc": ["/etc/hosts", "/etc/systemd/system/api.service"],
        },
        "relevant_files": [
            "/app/api.env",
            "/var/log/api.log",
            "/app/config/database.yml",
            "/app/config/app.rb",
            "/etc/hosts",
        ],
        "relevant_service_checks": ["api", "postgres"],
        "relevant_log_services": ["api", "nginx"],
        "relevant_commands": {
            "ping db-old.internal": True,
            "ping db.internal": True,
            "nslookup": True,
        },
        "allowed_shell_commands": {
            "ping db-old.internal": "ping: db-old.internal: Name or service not known",
            "ping db.internal": (
                "PING db.internal (10.0.1.5) 56(84) bytes of data.\n"
                "64 bytes from db.internal (10.0.1.5): icmp_seq=1 ttl=64 time=0.3 ms"
            ),
            "nslookup db-old.internal": "** server can't find db-old.internal: NXDOMAIN",
            "nslookup db.internal": "Server: 127.0.0.53\nAddress: 10.0.1.5\n\nName: db.internal",
            "journalctl -xe": (
                "Jan 15 14:00:02 api[2345]: FATAL KeyError: SECRET_KEY not set!\n"
                "Jan 15 14:00:02 systemd[1]: api.service failed"
            ),
            "ps aux": (
                "USER   PID  %CPU %MEM COMMAND\n"
                "nginx  1234  0.1  0.5 nginx: master process\n"
                "redis  9012  0.2  2.1 redis-server *:6379\n"
                "pgsql  3456  1.2  8.4 postgres: main\n"
            ),
            "env | grep DB": "DB_HOST=db-old.internal\nDB_PORT=5432\nDB_NAME=appdb",
            "cat /etc/resolv.conf": "nameserver 127.0.0.53\noptions edns0 trust-ad\nsearch internal",
        },
        "success_edits": {
            "/app/api.env": {
                "DB_HOST": "db.internal",
                "SECRET_KEY": None,  # Any non-empty value is valid
                "__wrong_keys__": ["DB_HOST"],
            },
        },
        "critical_healthy_services": ["nginx", "postgres", "redis", "worker"],
        "restart_effects": {
            "api": {
                "new_status": "running",
                "logs": [
                    "Jan 15 14:30:00 prod-api systemd[1]: Starting api.service...",
                    "Jan 15 14:30:01 prod-api api[7890]: Loading configuration...",
                    "Jan 15 14:30:01 prod-api api[7890]: DB connection: db.internal:5432 OK",
                    "Jan 15 14:30:01 prod-api api[7890]: Auth middleware initialized",
                    "Jan 15 14:30:01 prod-api api[7890]: Listening on port 3000",
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
    "grader": _grade_medium,
}
