# Action parser and execution engine for translating string actions to state changes.
from __future__ import annotations
import re
from enum import Enum
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel


class ActionType(str, Enum):
    READ_FILE = "READ_FILE"
    LIST_DIR = "LIST_DIR"
    EDIT_CONFIG = "EDIT_CONFIG"
    RESTART_SERVICE = "RESTART_SERVICE"
    RUN_SHELL = "RUN_SHELL"
    CHECK_SERVICE = "CHECK_SERVICE"
    VIEW_LOGS = "VIEW_LOGS"
    UNKNOWN = "UNKNOWN"


class ParsedAction(BaseModel):
    action_type: ActionType
    args: Dict[str, Any] = {}
    raw: str = ""


def parse_action(raw: str) -> ParsedAction:
    """Parse a raw LLM action string into a structured ParsedAction."""
    raw = raw.strip()
    if not raw:
        return ParsedAction(action_type=ActionType.UNKNOWN, raw=raw)

    # Try to match each action type
    patterns = [
        (ActionType.READ_FILE,       r"^READ_FILE\s+(.+)$"),
        (ActionType.LIST_DIR,        r"^LIST_DIR\s+(.+)$"),
        (ActionType.EDIT_CONFIG,     r"^EDIT_CONFIG\s+(\S+)\s+(\S+)=(.+)$"),
        (ActionType.RESTART_SERVICE, r"^RESTART_SERVICE\s+(\S+)$"),
        (ActionType.RUN_SHELL,       r"^RUN_SHELL\s+(.+)$"),
        (ActionType.CHECK_SERVICE,   r"^CHECK_SERVICE\s+(\S+)$"),
        (ActionType.VIEW_LOGS,       r"^VIEW_LOGS(?:\s+(\S+))?$"),
    ]

    for action_type, pattern in patterns:
        m = re.match(pattern, raw, re.IGNORECASE)
        if m:
            groups = m.groups()
            args: Dict[str, Any] = {}

            if action_type == ActionType.READ_FILE:
                args = {"path": groups[0].strip()}
            elif action_type == ActionType.LIST_DIR:
                args = {"path": groups[0].strip()}
            elif action_type == ActionType.EDIT_CONFIG:
                args = {"file": groups[0].strip(), "key": groups[1].strip(), "value": groups[2].strip()}
            elif action_type == ActionType.RESTART_SERVICE:
                args = {"service": groups[0].strip()}
            elif action_type == ActionType.RUN_SHELL:
                args = {"command": groups[0].strip()}
            elif action_type == ActionType.CHECK_SERVICE:
                args = {"service": groups[0].strip()}
            elif action_type == ActionType.VIEW_LOGS:
                args = {"service": groups[0].strip() if groups[0] else "all"}

            return ParsedAction(action_type=action_type, args=args, raw=raw)

    return ParsedAction(action_type=ActionType.UNKNOWN, raw=raw)


def execute_action(action: ParsedAction, state: Dict[str, Any]) -> Tuple[str, float, Dict[str, Any]]:
    """
    Execute an action against the environment state.
    Returns: (result_text, reward_delta, updated_state)
    """
    state = dict(state)  # shallow copy

    if action.action_type == ActionType.READ_FILE:
        return _read_file(action.args["path"], state)

    elif action.action_type == ActionType.LIST_DIR:
        return _list_dir(action.args["path"], state)

    elif action.action_type == ActionType.EDIT_CONFIG:
        return _edit_config(action.args["file"], action.args["key"], action.args["value"], state)

    elif action.action_type == ActionType.RESTART_SERVICE:
        return _restart_service(action.args["service"], state)

    elif action.action_type == ActionType.RUN_SHELL:
        return _run_shell(action.args["command"], state)

    elif action.action_type == ActionType.CHECK_SERVICE:
        return _check_service(action.args["service"], state)

    elif action.action_type == ActionType.VIEW_LOGS:
        return _view_logs(action.args.get("service", "all"), state)

    else:
        return (
            f"ERROR: Unknown action '{action.raw}'. Valid actions: READ_FILE, LIST_DIR, "
            "EDIT_CONFIG, RESTART_SERVICE, RUN_SHELL, CHECK_SERVICE, VIEW_LOGS",
            -0.1,
            state,
        )


# Action Implementations

def _read_file(path: str, state: Dict) -> Tuple[str, float, Dict]:
    files = state.get("files", {})
    # Normalize path
    if path not in files:
        # Try with/without leading slash
        alt = path.lstrip("/") if path.startswith("/") else f"/{path}"
        if alt in files:
            path = alt
        else:
            return f"ERROR: File not found: {path}", -0.1, state

    content = files[path]
    reward = 0.0

    # Give reward for discovering relevant files
    relevant_files = state.get("relevant_files", [])
    already_read = state.get("files_read", set())
    if isinstance(already_read, list):
        already_read = set(already_read)

    if path in relevant_files and path not in already_read:
        reward = 0.2
        already_read.add(path)
        state["files_read"] = list(already_read)

    state["last_action_result"] = f"Contents of {path}:\n{content}"
    return f"Contents of {path}:\n{content}", reward, state


def _list_dir(path: str, state: Dict) -> Tuple[str, float, Dict]:
    files = state.get("files", {})
    dirs = state.get("directories", {})

    if path in dirs:
        listing = dirs[path]
        state["last_action_result"] = f"Directory listing of {path}:\n" + "\n".join(listing)
        return f"Directory listing of {path}:\n" + "\n".join(listing), 0.0, state

    # Auto-generate listing from files
    matching = [f for f in files.keys() if f.startswith(path.rstrip("/") + "/") or f == path]
    if matching:
        listing_str = "\n".join(matching)
        state["last_action_result"] = f"Directory listing of {path}:\n{listing_str}"
        return f"Directory listing of {path}:\n{listing_str}", 0.0, state

    return f"ERROR: Directory not found: {path}", -0.1, state


def _edit_config(file: str, key: str, value: str, state: Dict) -> Tuple[str, float, Dict]:
    files = state.get("files", {})

    if file not in files:
        alt = file.lstrip("/") if file.startswith("/") else f"/{file}"
        if alt in files:
            file = alt
        else:
            return f"ERROR: File not found: {file}", -0.1, state

    content = files[file]
    success_edits = state.get("success_edits", {})

    # Check if this is a correct edit
    correct = success_edits.get(file, {}).get(key) == value
    wrong_value_keys = success_edits.get(file, {}).get("__wrong_keys__", [])

    if key in wrong_value_keys and not correct:
        # Editing a critical key with wrong value — destructive
        state["last_action_result"] = f"ERROR: Invalid value '{value}' for key '{key}' in {file}"
        return f"Config {file}: Set {key}={value} (WARNING: value may be incorrect)", -0.5, state

    # Check for destructive patterns
    destructive_patterns = ["rm ", "delete", "null", "none", "disabled"]
    if any(p in value.lower() for p in destructive_patterns):
        return f"ERROR: Potentially destructive value '{value}' rejected.", -0.5, state

    # Apply the edit — update line in file content
    lines = content.split("\n")
    new_lines = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}")

    state["files"][file] = "\n".join(new_lines)

    reward = 0.3 if correct else -0.1
    msg = f"Successfully updated {file}: {key}={value}"
    if correct:
        msg += " ✓ (correct fix)"

    state["last_action_result"] = msg
    return msg, reward, state


def _restart_service(service: str, state: Dict) -> Tuple[str, float, Dict]:
    services = state.get("services", {})

    if service not in services:
        return f"ERROR: Unknown service '{service}'", -0.1, state

    # Check if restarting a healthy service (destructive)
    critical_healthy = state.get("critical_healthy_services", [])
    if service in critical_healthy and services[service] == "running":
        services[service] = "restarting"
        state["services"] = services
        state["logs"] = state.get("logs", []) + [
            f"systemd[1]: Stopping {service}...",
            f"systemd[1]: {service} stopped unexpectedly",
            f"WARNING: {service} was healthy — unnecessary restart may cause instability",
        ]
        return (
            f"WARNING: {service} was running and healthy. Restart may cause issues.",
            -1.0,
            state,
        )

    # Normal restart
    restart_effects = state.get("restart_effects", {})
    current_status = services[service]

    if service in restart_effects:
        effect = restart_effects[service]
        services[service] = effect.get("new_status", "running")
        new_logs = effect.get("logs", [f"systemd[1]: {service} restarted successfully"])
        state["logs"] = state.get("logs", []) + new_logs
        state["services"] = services

        reward = effect.get("reward", 0.0)
        msg = f"Service {service} restarted. Status: {services[service]}"
        state["last_action_result"] = msg
        return msg, reward, state

    # Default: if service was crashed and we restart, it might succeed
    if current_status in ["crashed", "failed", "stopped"]:
        services[service] = "running"
        state["services"] = services
        state["logs"] = state.get("logs", []) + [
            f"systemd[1]: Starting {service}...",
            f"systemd[1]: {service} started successfully",
        ]
        state["last_action_result"] = f"Service {service} restarted. Status: running"
        return f"Service {service} restarted. Status: running", 0.1, state

    services[service] = "running"
    state["services"] = services
    state["last_action_result"] = f"Service {service} restarted. Status: running"
    return f"Service {service} restarted. Status: running", 0.0, state


def _run_shell(command: str, state: Dict) -> Tuple[str, float, Dict]:
    allowed_cmds = state.get("allowed_shell_commands", {})

    # Check for destructive commands
    destructive = ["rm -rf", "mkfs", "dd if=", "shutdown", "reboot", "kill -9 1", "> /dev/sda"]
    for d in destructive:
        if d in command:
            return f"ERROR: Destructive command '{command}' blocked by safety policy.", -1.0, state

    # Check predefined outputs
    for pattern, output in allowed_cmds.items():
        if pattern in command:
            state["last_action_result"] = output
            reward = 0.1 if state.get("relevant_commands", {}).get(pattern) else 0.0
            return output, reward, state

    # Generic fallback
    result = f"$ {command}\n[no output]"
    state["last_action_result"] = result
    return result, -0.05, state


def _check_service(service: str, state: Dict) -> Tuple[str, float, Dict]:
    services = state.get("services", {})

    if service not in services:
        return f"ERROR: Unknown service '{service}'. Known services: {list(services.keys())}", -0.1, state

    status = services[service]
    logs = state.get("logs", [])
    recent = [l for l in logs if service in l.lower()][-5:]

    result = (
        f"● {service}.service\n"
        f"   Loaded: loaded (/etc/systemd/system/{service}.service)\n"
        f"   Active: {'active (running)' if status == 'running' else status}\n"
        f"   Recent logs:\n" + "\n".join(f"     {l}" for l in recent)
    )

    reward = 0.0
    relevant_checks = state.get("relevant_service_checks", [])
    already_checked = state.get("services_checked", set())
    if isinstance(already_checked, list):
        already_checked = set(already_checked)

    if service in relevant_checks and service not in already_checked:
        reward = 0.1
        already_checked.add(service)
        state["services_checked"] = list(already_checked)

    state["last_action_result"] = result
    return result, reward, state


def _view_logs(service: str, state: Dict) -> Tuple[str, float, Dict]:
    logs = state.get("logs", [])

    if service == "all":
        result = "System logs (recent):\n" + "\n".join(logs[-20:])
    else:
        filtered = [l for l in logs if service.lower() in l.lower()]
        result = f"Logs for {service}:\n" + ("\n".join(filtered[-15:]) if filtered else "(no logs found)")

    relevant_logs = state.get("relevant_log_services", [])
    already_viewed = state.get("logs_viewed", set())
    if isinstance(already_viewed, list):
        already_viewed = set(already_viewed)

    reward = 0.0
    if service in relevant_logs and service not in already_viewed:
        reward = 0.1
        already_viewed.add(service)
        state["logs_viewed"] = list(already_viewed)

    state["last_action_result"] = result
    return result, reward, state
