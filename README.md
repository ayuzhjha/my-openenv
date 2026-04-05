---
title: SRE OpenEnv
emoji: 🚨
colorFrom: red
colorTo: yellow
sdk: gradio
sdk_version: "4.31.0"
app_file: main.py
pinned: false
tags:
  - openenv
  - sre
  - devops
  - incident-response
  - reinforcement-learning
  - ai-agent
license: mit
---

# 🚨 SRE OpenEnv — AI Incident Response Simulator

An **OpenEnv-compliant** environment where AI agents autonomously diagnose and resolve real-world backend service failures through iterative reasoning and action.

## 🎯 Overview

This environment simulates a Linux production server with real-world failure scenarios. An AI agent must investigate the system — reading logs, checking configs, and taking corrective actions — to restore service health.

**Why this matters:** SRE incident response is a high-value, time-critical skill. Training agents to handle real infrastructure failures could dramatically reduce MTTR (Mean Time To Recover) for production systems.

---

## 📋 Environment Description

The environment maintains an internal server state including:
- **Services**: nginx, backend, api, payment, worker, postgres, redis
- **Config files**: nginx.conf, .env files, systemd service definitions
- **Logs**: Realistic nginx, systemd, application logs (with noise!)
- **Shell commands**: netstat, ps, curl, ping, openssl, etc.

Observations are **limited** — the agent cannot see everything at once and must investigate.

---

## ⚡ Action Space

| Action | Format | Description |
|--------|--------|-------------|
| `READ_FILE` | `READ_FILE <path>` | Read a config/log file |
| `LIST_DIR` | `LIST_DIR <path>` | List directory contents |
| `EDIT_CONFIG` | `EDIT_CONFIG <file> <key>=<val>` | Edit a config key |
| `RESTART_SERVICE` | `RESTART_SERVICE <name>` | Restart a service |
| `RUN_SHELL` | `RUN_SHELL <command>` | Run a shell command |
| `CHECK_SERVICE` | `CHECK_SERVICE <name>` | Check service status + recent logs |
| `VIEW_LOGS` | `VIEW_LOGS <service\|all>` | View service logs |

---

## 👁️ Observation Space

Each step returns:
```json
{
  "task_id": "task_easy",
  "task_description": "Fix the backend service...",
  "service_statuses": {"nginx": "running", "backend": "crashed"},
  "recent_logs": ["502 Bad Gateway", "..."],
  "last_action_result": "Contents of backend.env:\nPORT=5000\n...",
  "step_number": 3,
  "files_visible": ["backend.env", "/etc/nginx/nginx.conf", "..."],
  "hint": null
}
```

---

## 📊 Tasks

### 🟢 Easy — Wrong Port Configuration
- **Scenario**: Backend crashed. 502 errors everywhere.
- **Root Cause**: `PORT=5000` in backend.env but nginx upstream expects `:8080`
- **Fix**: Read config → change PORT → restart backend
- **Max Steps**: 15
- **Expected Score**: 0.7–1.0

### 🟡 Medium — Double-Layer API Failure
- **Scenario**: API service in crash loop. Auth and DB both failing.
- **Root Causes**: (1) `DB_HOST=db-old.internal` (decommissioned) (2) `SECRET_KEY` missing from env
- **Fix**: Fix DB hostname AND add SECRET_KEY → restart api
- **Max Steps**: 20
- **Expected Score**: 0.4–0.85

### 🔴 Hard — Payment System Cascade Failure
- **Scenario**: Payment processing down. $50k/hour revenue loss. Logs mislead toward DB.
- **Root Causes**: (1) SSL cert expired (new cert available) (2) Stripe v1 API deprecated → v2 (3) `MAX_RETRIES=0` causes infinite loop in worker
- **Fix**: Update SSL path + gateway URL + retries → restart payment + worker
- **Max Steps**: 30
- **Expected Score**: 0.2–0.7

---

## 🎁 Reward System

| Signal | Reward |
|--------|--------|
| Discovering a relevant file | +0.2 |
| Correct config edit | +0.3 |
| Service restart (relevant) | +0.1 |
| Task fully solved | +0.5 bonus |
| Useless/repeated action | −0.1 |
| Wrong config value | −0.5 |
| Stopping healthy service | −1.0 |

Rewards are **continuous and informative** — the agent gets signal throughout the episode, not just at the end.

---

## 🚀 Setup & Usage

### Local Development

```bash
git clone https://huggingface.co/spaces/<your-username>/sre-env
cd sre-env

pip install -r requirements.txt

# Start server
python main.py
# Open http://localhost:7860/ui
```

### API Usage

```bash
# Reset environment
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "easy"}'

# Take an action
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<sid>", "action": "READ_FILE backend.env"}'

# Get score
curl "http://localhost:7860/score?session_id=<sid>"
```

### Docker

```bash
docker build -t sre-env .
docker run -p 7860:7860 \
  -e HF_TOKEN=your_key \
  -e MODEL_NAME=gpt-4o-mini \
  sre-env
```

### Running Inference

```bash
export API_BASE_URL=https://api.openai.com/v1
export MODEL_NAME=gpt-4o-mini
export HF_TOKEN=sk-your-key
export SERVER_URL=http://localhost:7860

# Start server in background first
python main.py &
sleep 5

# Run baseline
python inference.py
```

---

## 📈 Baseline Scores

| Task | Model | Score | Steps |
|------|-------|-------|-------|
| Easy | gpt-4o-mini | 0.85 | 8 |
| Medium | gpt-4o-mini | 0.62 | 14 |
| Hard | gpt-4o-mini | 0.41 | 22 |
| **Average** | | **0.63** | |

---

## 📂 Project Structure

```
sre-openenv/
├── env.py              # OpenEnv environment engine (Pydantic models + logic)
├── actions.py          # Structured action system (parse + execute)
├── tasks/
│   ├── __init__.py     # Task registry
│   ├── task_easy.py    # Easy: wrong port config
│   ├── task_medium.py  # Medium: double failure
│   └── task_hard.py    # Hard: cascade failure + misleading logs
├── server.py           # FastAPI REST server (/reset, /step, /state)
├── app.py              # Gradio UI
├── main.py             # Entry point (FastAPI + Gradio combined)
├── inference.py        # Baseline LLM agent (OpenAI client)
├── openenv.yaml        # OpenEnv spec metadata
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 🏆 OpenEnv Compliance

- ✅ Typed Pydantic models: `SREObservation`, `SREAction`, `SREReward`
- ✅ `reset()` → clean initial state
- ✅ `step(action)` → observation, reward, done, info
- ✅ `state()` → full internal state
- ✅ `openenv.yaml` with full metadata
- ✅ 3+ tasks with graders (0.0–1.0 scores)
- ✅ Deterministic graders
- ✅ Continuous reward signal
- ✅ Working Dockerfile
- ✅ HF Space deployment
- ✅ Baseline inference script

---

## 📄 License

MIT License — see LICENSE for details.
