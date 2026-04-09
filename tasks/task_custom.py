"""
tasks/task_custom.py
CUSTOM: Disk is full — app cannot write logs, DB writes fail, service crashes.
Fix: Read disk usage → delete old log files → restart app service.

HOW TO ADD YOUR OWN TASK:
  1. Copy this file, rename it  task_yourname.py
  2. Edit initial_state: services, files, logs, restart_effects, success_edits
  3. Write your _grade() function — return float 0.0–1.0
  4. Register it in tasks/__init__.py
"""


def _grade_custom(state: dict, history: list) -> float:
    """
    Full score requires:
      1. Ran disk check (df -h or du)
      2. Deleted the bloated log file
      3. Restarted the app service
    """
    score = 0.0
    files = state.get("files", {})
    services = state.get("services", {})
    files_read = set(state.get("files_read", []))
    commands_run = set(state.get("commands_run", []))

    # Partial: checked disk usage
    if any(c in commands_run for c in ["df -h", "du -sh /var/log"]):
        score += 0.2

    # Partial: read the log to understand the problem
    if "/var/log/app/app.log" in files_read:
        score += 0.1

    # Main fix: log file deleted (we simulate by checking if disk_cleared flag set)
    if state.get("disk_cleared"):
        score += 0.3

    # Final: app restarted and running
    if services.get("app") == "running" and state.get("disk_cleared"):
        score += 0.4

    return min(score, 1.0)


TASK_CUSTOM = {
    "id": "task_custom",
    "name": "Disk Full — App Crash",
    "difficulty": "easy",
    "description": (
        "The app service has crashed and DB writes are failing. "
        "Monitoring shows disk usage at 100%. Old log files are filling the disk. "
        "Find the culprit, free up disk space, and restore the service."
    ),
    "max_steps": 15,
    "initial_state": {
        "services": {
            "nginx": "running",
            "app": "crashed",
            "postgres": "running",
            "redis": "running",
        },
        "files": {
            "/var/log/app/app.log": (
                "2024-01-15 09:00:01 INFO  App starting...\n"
                "2024-01-15 09:00:02 INFO  Connected to database\n"
                "2024-01-15 09:10:00 ERROR No space left on device — cannot write log\n"
                "2024-01-15 09:10:01 FATAL Disk full. Shutting down.\n"
            ),
            "/var/log/app/app.log.old": (
                "# 20GB of old rotated logs accumulated here\n"
                "# This file is safe to delete\n"
            ),
            "/etc/app/app.conf": (
                "DB_HOST=localhost\n"
                "DB_PORT=5432\n"
                "LOG_DIR=/var/log/app\n"
                "PORT=3000\n"
            ),
        },
        "logs": [
            "Jan 15 09:10:00 prod-server app[1234]: FATAL: No space left on device",
            "Jan 15 09:10:01 prod-server systemd[1]: app.service: Main process exited",
            "Jan 15 09:10:01 prod-server kernel: EXT4-fs error: no space left",
            "Jan 15 09:10:02 prod-server postgres[5678]: ERROR: could not write to file",
            "Jan 15 09:10:05 prod-server nginx[9012]: 502 Bad Gateway /api",
        ],
        "directories": {
            "/var/log/app": ["/var/log/app/app.log", "/var/log/app/app.log.old"],
            "/etc/app": ["/etc/app/app.conf"],
        },
        "allowed_shell_commands": {
            "df -h": (
                "Filesystem      Size  Used Avail Use% Mounted on\n"
                "/dev/sda1        50G   50G     0 100% /\n"
            ),
            "du -sh /var/log": "48G\t/var/log\n",
            "du -sh /var/log/app": "48G\t/var/log/app\n",
            "ls -lh /var/log/app": (
                "-rw-r--r-- 1 app app  512 Jan 15 app.log\n"
                "-rw-r--r-- 1 app app  20G Jan 14 app.log.old\n"
            ),
            "rm /var/log/app/app.log.old": "__DELETE_FILE__:/var/log/app/app.log.old",
        },
        "restart_effects": {
            "app": {
                "new_status": "running",
                "logs": [
                    "Jan 15 09:30:00 prod-server systemd[1]: Starting app.service...",
                    "Jan 15 09:30:01 prod-server app[2000]: Disk space OK (47% used)",
                    "Jan 15 09:30:01 prod-server app[2000]: Listening on port 3000",
                    "Jan 15 09:30:02 prod-server systemd[1]: Started app.service.",
                ],
                "reward": 0.1,
            }
        },
        "success_edits": {},
        "critical_healthy_services": ["nginx", "postgres", "redis"],
        "relevant_files": ["/var/log/app/app.log", "/var/log/app/app.log.old"],
        "relevant_service_checks": ["app"],
        "relevant_log_services": ["app"],
        "relevant_commands": {"df -h": True, "du -sh /var/log": True},
        "disk_cleared": False,
        "task_solved": False,
        "files_read": [],
        "services_checked": [],
        "logs_viewed": [],
        "commands_run": [],
        "edits_made": {},
    },
    "grader": _grade_custom,
}
