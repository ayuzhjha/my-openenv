"""
app.py - Gradio UI for SRE OpenEnv
Provides an interactive interface to run the SRE environment.
Launched alongside the FastAPI server via main.py.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
import requests

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:7860")

# ── API helpers ───────────────────────────────────────────────────────────────

def api_reset(task_id: str) -> Dict:
    resp = requests.post(f"{SERVER_URL}/reset", json={"task_id": task_id}, timeout=10)
    return resp.json()


def api_step(session_id: str, action: str) -> Dict:
    resp = requests.post(f"{SERVER_URL}/step", json={"session_id": session_id, "action": action}, timeout=10)
    return resp.json()


def api_score(session_id: str) -> float:
    resp = requests.get(f"{SERVER_URL}/score", params={"session_id": session_id}, timeout=10)
    return resp.json().get("score", 0.0)


# ── UI logic ──────────────────────────────────────────────────────────────────

def start_task(task_choice: str) -> Tuple[str, str, str, str, str, str]:
    """Reset the environment and return initial UI state."""
    task_map = {"🟢 Easy — Wrong Port": "easy", "🟡 Medium — Double Failure": "medium", "🔴 Hard — Cascade Incident": "hard"}
    task_id = task_map.get(task_choice, "easy")

    try:
        resp = api_reset(task_id)
    except Exception as e:
        return "", "", f"❌ Server error: {e}", "", "", ""

    session_id = resp["session_id"]
    obs = resp["observation"]
    description = resp["task_description"]

    services_text = "\n".join(
        f"  {'🟢' if v == 'running' else '🔴' if v in ('crashed','failed') else '🟡'} {k}: {v}"
        for k, v in obs["service_statuses"].items()
    )

    logs_text = "\n".join(obs["recent_logs"]) if obs["recent_logs"] else "(no logs yet)"
    files_text = "\n".join(obs["files_visible"][:15])

    initial_log = f"""╔══════════════════════════════════════╗
║  SRE INCIDENT — {task_id.upper():^20} ║
╚══════════════════════════════════════╝

{description}

SESSION: {session_id[:8]}...
"""

    return session_id, initial_log, services_text, logs_text, files_text, "Score: 0.00"


def take_action(
    session_id: str,
    action_input: str,
    history_log: str,
) -> Tuple[str, str, str, str, str]:
    """Execute an action and update UI."""
    if not session_id:
        return history_log, "⚠️ Start a task first", "", "", "Score: ?"

    action = action_input.strip()
    if not action:
        return history_log, "⚠️ Enter an action", "", "", "Score: ?"

    try:
        resp = api_step(session_id, action)
    except Exception as e:
        return history_log, f"❌ Error: {e}", "", "", "Score: ?"

    obs = resp["observation"]
    reward = resp["reward"]
    done = resp["done"]
    step = obs["step_number"]

    reward_val = reward["value"]
    reward_emoji = "✅" if reward_val > 0.3 else "⚠️" if reward_val >= 0 else "❌"

    new_entry = (
        f"\n── Step {step} ──────────────────────────\n"
        f"Action: {action}\n"
        f"Result: {obs['last_action_result'][:200]}\n"
        f"Reward: {reward_emoji} {reward_val:+.2f}  ({reward.get('message', '')})\n"
    )

    if done:
        score = reward.get("cumulative", 0.0)
        new_entry += f"\n{'='*40}\n🏁 EPISODE DONE — Score: {score:.3f}\n{'='*40}\n"

    updated_log = history_log + new_entry

    services_text = "\n".join(
        f"  {'🟢' if v == 'running' else '🔴' if v in ('crashed','failed') else '🟡'} {k}: {v}"
        for k, v in obs["service_statuses"].items()
    )

    logs_text = "\n".join(obs["recent_logs"][-10:])
    score_text = f"Score: {reward.get('cumulative', 0.0):.3f}"

    hint = obs.get("hint")
    if hint:
        logs_text += f"\n\n💡 {hint}"

    return updated_log, services_text, logs_text, score_text, ""


# ── Gradio layout ─────────────────────────────────────────────────────────────

with gr.Blocks(
    title="SRE OpenEnv — AI Incident Response",
    theme=gr.themes.Base(
        primary_hue="red",
        secondary_hue="orange",
        neutral_hue="slate",
        font=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    ),
    css="""
        .header-text { font-family: 'JetBrains Mono', monospace; }
        .score-display { font-size: 1.5em; font-weight: bold; }
        .terminal-box textarea { font-family: 'JetBrains Mono', monospace; font-size: 12px; }
        #action-row { border: 2px solid #ef4444; border-radius: 8px; padding: 4px; }
    """,
) as demo:

    session_state = gr.State("")

    gr.Markdown(
        """# 🚨 SRE OpenEnv — AI Incident Response Simulator
        
**An OpenEnv-compliant environment where AI agents diagnose and resolve real-world backend failures.**

> Use the action interface below or run `inference.py` for automated evaluation.
        """,
        elem_classes=["header-text"],
    )

    with gr.Row():
        with gr.Column(scale=1):
            task_dropdown = gr.Dropdown(
                choices=[
                    "🟢 Easy — Wrong Port",
                    "🟡 Medium — Double Failure",
                    "🔴 Hard — Cascade Incident",
                ],
                value="🟢 Easy — Wrong Port",
                label="Select Task",
            )
            start_btn = gr.Button("🚀 Start Incident", variant="primary", size="lg")

            gr.Markdown("### 📊 Services")
            services_box = gr.Textbox(
                value="(not started)",
                label="",
                lines=8,
                interactive=False,
                elem_classes=["terminal-box"],
            )

            gr.Markdown("### 📁 Available Files")
            files_box = gr.Textbox(
                value="(not started)",
                label="",
                lines=8,
                interactive=False,
                elem_classes=["terminal-box"],
            )

            score_display = gr.Textbox(
                value="Score: 0.00",
                label="Current Score",
                interactive=False,
                elem_classes=["score-display"],
            )

        with gr.Column(scale=2):
            gr.Markdown("### 📋 System Logs")
            logs_box = gr.Textbox(
                value="(start a task to see logs)",
                label="",
                lines=6,
                interactive=False,
                elem_classes=["terminal-box"],
            )

            gr.Markdown("### 🖥️ Agent Terminal")
            history_box = gr.Textbox(
                value="",
                label="",
                lines=18,
                interactive=False,
                elem_classes=["terminal-box"],
            )

            with gr.Row(elem_id="action-row"):
                action_input = gr.Textbox(
                    placeholder="e.g.  READ_FILE backend.env  |  EDIT_CONFIG backend.env PORT=8080  |  RESTART_SERVICE backend",
                    label="",
                    scale=4,
                )
                submit_btn = gr.Button("⚡ Execute", variant="primary", scale=1)

            gr.Markdown(
                """**Quick actions:** `VIEW_LOGS all` · `CHECK_SERVICE nginx` · `LIST_DIR /etc` · `RUN_SHELL ps aux`
                
**Fix actions:** `READ_FILE <path>` · `EDIT_CONFIG <file> <key>=<val>` · `RESTART_SERVICE <name>`"""
            )

    # ── Event handlers ─────────────────────────────────────────────────────────

    start_btn.click(
        fn=start_task,
        inputs=[task_dropdown],
        outputs=[session_state, history_box, services_box, logs_box, files_box, score_display],
    )

    submit_btn.click(
        fn=take_action,
        inputs=[session_state, action_input, history_box],
        outputs=[history_box, services_box, logs_box, score_display, action_input],
    )

    action_input.submit(
        fn=take_action,
        inputs=[session_state, action_input, history_box],
        outputs=[history_box, services_box, logs_box, score_display, action_input],
    )


if __name__ == "__main__":
    # Standalone Gradio mode (for testing)
    demo.launch(server_port=7861)
