"""
inference.py - Baseline inference script for SRE OpenEnv
Uses OpenAI-compatible client to run an LLM agent against all 3 tasks.
Emits structured [START] / [STEP] / [END] logs as required by evaluator.

Environment variables:
  API_BASE_URL  - LLM API base URL (default: https://api.openai.com/v1)
  MODEL_NAME    - Model identifier (default: gpt-4o-mini)
  HF_TOKEN      - API key (used as OpenAI API key)
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

# ── Configuration ─────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN = os.getenv("HF_TOKEN")

# Optional - if you use from_docker_image():
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:7860")

MAX_STEPS_PER_TASK = 20
TEMPERATURE = 0.0
MAX_TOKENS = 256

TASKS = ["easy", "medium", "hard"]

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) diagnosing and fixing server incidents.

You interact with a simulated Linux server environment. At each step you receive:
- Service statuses (which services are running/crashed)
- Recent system logs
- Result of your last action
- List of files you can read

You must respond with EXACTLY ONE action per step, in this exact format:
  ACTION_TYPE [arguments]

Available actions:
  READ_FILE <path>           - Read the contents of a file
  LIST_DIR <path>            - List files in a directory
  EDIT_CONFIG <file> <key>=<value>  - Edit a config key in a file
  RESTART_SERVICE <name>     - Restart a service
  RUN_SHELL <command>        - Run a shell command
  CHECK_SERVICE <name>       - Check service status and recent logs
  VIEW_LOGS <service>        - View logs for a service (or "all")

RULES:
- Output ONLY the action, nothing else. No explanation, no preamble.
- Do NOT restart services that are already running and healthy.
- Read config files before editing them.
- After editing a config, restart the affected service.
- One action per response — no multi-line actions.

Examples of valid actions:
  READ_FILE /etc/nginx/nginx.conf
  VIEW_LOGS nginx
  CHECK_SERVICE backend
  EDIT_CONFIG backend.env PORT=8080
  RESTART_SERVICE backend
  RUN_SHELL netstat -tlnp
"""


# ── Logging helpers (REQUIRED FORMAT) ────────────────────────────────────────

def log_start(task: str, model: str) -> None:
    print(json.dumps({
        "event": "START",
        "task": task,
        "model": model,
        "timestamp": time.time(),
    }), flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str] = None) -> None:
    print(json.dumps({
        "event": "STEP",
        "step": step,
        "action": action,
        "reward": reward,
        "done": done,
        "error": error,
    }), flush=True)


def log_end(task: str, success: bool, steps: int, score: float, rewards: List[float]) -> None:
    print(json.dumps({
        "event": "END",
        "task": task,
        "success": success,
        "steps": steps,
        "score": score,
        "total_reward": sum(rewards),
        "rewards": rewards,
        "timestamp": time.time(),
    }), flush=True)


# ── API helpers ───────────────────────────────────────────────────────────────

def call_server(endpoint: str, payload: Dict) -> Dict:
    """Call the SRE env server."""
    url = f"{SERVER_URL}{endpoint}"
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def call_server_get(endpoint: str, params: Dict = None) -> Dict:
    url = f"{SERVER_URL}{endpoint}"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_llm_action(client: OpenAI, obs: Dict, history: List[str]) -> str:
    """Ask the LLM what action to take next."""
    services = obs.get("service_statuses", {})
    logs = obs.get("recent_logs", [])
    last_result = obs.get("last_action_result", "")
    files = obs.get("files_visible", [])
    hint = obs.get("hint")
    step = obs.get("step_number", 0)

    user_content = f"""=== STEP {step} ===

SERVICE STATUSES:
{json.dumps(services, indent=2)}

RECENT LOGS (last 10):
{chr(10).join(logs)}

LAST ACTION RESULT:
{last_result}

AVAILABLE FILES:
{chr(10).join(files[:20])}

ACTION HISTORY (last 5):
{chr(10).join(history[-5:])}
"""
    if hint:
        user_content += f"\nHINT: {hint}"

    user_content += "\n\nWhat is your next action?"

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        text = (completion.choices[0].message.content or "").strip()
        # Take only the first line (one action)
        return text.split("\n")[0].strip() if text else "VIEW_LOGS all"
    except Exception as e:
        print(f"[DEBUG] LLM call failed: {e}", flush=True)
        return "VIEW_LOGS all"


# ── Main runner ───────────────────────────────────────────────────────────────

def run_task(client: OpenAI, task_id: str) -> Dict[str, Any]:
    """Run a single task and return results."""
    print(f"\n{'='*60}", flush=True)
    print(f"[DEBUG] Starting task: {task_id}", flush=True)

    log_start(task=task_id, model=MODEL_NAME)

    history: List[str] = []
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    try:
        # Reset environment
        reset_resp = call_server("/reset", {"task_id": task_id})
        session_id = reset_resp["session_id"]
        obs = reset_resp["observation"]
        max_steps = reset_resp["max_steps"]

        print(f"[DEBUG] Session: {session_id}, max_steps: {max_steps}", flush=True)
        print(f"[DEBUG] Task: {reset_resp['task_description'][:100]}...", flush=True)

        # Agent loop
        for step in range(1, min(MAX_STEPS_PER_TASK, max_steps) + 1):
            # Get LLM action
            action = get_llm_action(client, obs, history)
            history.append(f"Step {step}: {action}")

            # Execute action
            step_resp = call_server("/step", {"action": action, "session_id": session_id})
            obs = step_resp["observation"]
            reward_val = step_resp["reward"]["value"]
            done = step_resp["done"]
            error = None

            rewards.append(reward_val)
            steps_taken = step

            log_step(step=step, action=action, reward=reward_val, done=done, error=error)

            print(f"[DEBUG] Step {step}: {action!r} -> reward={reward_val:.2f}, done={done}", flush=True)

            if done:
                break

        # Get final score
        score_resp = call_server_get("/score", {"session_id": session_id})
        score = score_resp.get("score", 0.0)
        success = score >= 0.8

    except Exception as e:
        print(f"[DEBUG] Task {task_id} error: {e}", flush=True)
        import traceback
        traceback.print_exc()

    log_end(task=task_id, success=success, steps=steps_taken, score=score, rewards=rewards)

    return {
        "task_id": task_id,
        "score": score,
        "success": success,
        "steps": steps_taken,
        "rewards": rewards,
    }


def wait_for_server(max_wait: int = 30) -> bool:
    """Wait for server to be ready."""
    for i in range(max_wait):
        try:
            resp = requests.get(f"{SERVER_URL}/health", timeout=5)
            if resp.status_code == 200:
                print(f"[DEBUG] Server ready after {i}s", flush=True)
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    print("[DEBUG] SRE OpenEnv Baseline Inference", flush=True)
    print(f"[DEBUG] API_BASE_URL={API_BASE_URL}", flush=True)
    print(f"[DEBUG] MODEL_NAME={MODEL_NAME}", flush=True)
    print(f"[DEBUG] SERVER_URL={SERVER_URL}", flush=True)

    # Wait for server
    if not wait_for_server():
        print("[ERROR] Server not ready after 30s", flush=True)
        sys.exit(1)

    # Initialize OpenAI client
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    # Run all tasks
    all_results = []
    for task_id in TASKS:
        result = run_task(client, task_id)
        all_results.append(result)

    # Summary
    print("\n" + "="*60, flush=True)
    print("BASELINE RESULTS SUMMARY", flush=True)
    print("="*60, flush=True)
    for r in all_results:
        status = "✓ PASS" if r["success"] else "✗ FAIL"
        print(f"  {status}  {r['task_id']:10s}  score={r['score']:.3f}  steps={r['steps']}", flush=True)

    avg_score = sum(r["score"] for r in all_results) / len(all_results)
    print(f"\n  Average score: {avg_score:.3f}", flush=True)
    print("="*60, flush=True)

    # Emit final summary as structured log
    print(json.dumps({
        "event": "SUMMARY",
        "tasks": all_results,
        "average_score": avg_score,
        "timestamp": time.time(),
    }), flush=True)


if __name__ == "__main__":
    main()
