"""
env.py - SRE OpenEnv Environment Engine
Implements the full OpenEnv spec with typed Pydantic models.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from actions import ParsedAction, parse_action, execute_action, ActionType
from tasks import TASK_REGISTRY


# ─── Pydantic Models (OpenEnv spec) ──────────────────────────────────────────

class SREObservation(BaseModel):
    """What the agent can see at each step."""
    task_id: str
    task_description: str
    service_statuses: Dict[str, str]
    recent_logs: List[str]
    last_action_result: str
    step_number: int
    files_visible: List[str]  # file paths available to read (not contents)
    hint: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_easy",
                "task_description": "Fix the backend service",
                "service_statuses": {"nginx": "running", "backend": "crashed"},
                "recent_logs": ["502 Bad Gateway"],
                "last_action_result": "No action yet",
                "step_number": 0,
                "files_visible": ["backend.env", "/etc/nginx/nginx.conf"],
            }
        }


class SREAction(BaseModel):
    """Structured action from the agent."""
    raw: str = Field(..., description="Raw action string from the agent LLM")

    class Config:
        json_schema_extra = {
            "example": {"raw": "EDIT_CONFIG backend.env PORT=8080"}
        }


class SREReward(BaseModel):
    """Reward signal with breakdown."""
    value: float = Field(..., ge=-1.0, le=1.0)
    cumulative: float
    breakdown: Dict[str, float] = {}
    message: str = ""


class StepResult(BaseModel):
    """Full result of a step() call."""
    observation: SREObservation
    reward: SREReward
    done: bool
    info: Dict[str, Any] = {}


class ResetResult(BaseModel):
    """Result of a reset() call."""
    observation: SREObservation
    task_id: str
    task_description: str
    max_steps: int


# ─── Environment ─────────────────────────────────────────────────────────────

class SREEnvironment:
    """
    SRE Simulation Environment following OpenEnv spec.
    Simulates a Linux server with services, config files, and logs.
    An AI agent must diagnose and fix failures through iterative actions.
    """

    VERSION = "1.0.0"
    NAME = "sre-env"

    def __init__(self, task_id: str = "easy"):
        self._task_id = task_id
        self._task_def = None
        self._state: Dict[str, Any] = {}
        self._step_count = 0
        self._cumulative_reward = 0.0
        self._done = False
        self._action_history: List[str] = []
        self._reward_history: List[float] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def reset(self) -> ResetResult:
        """Initialize environment with a fresh task state."""
        task_key = self._task_id.replace("task_", "") if self._task_id.startswith("task_") else self._task_id
        if task_key not in TASK_REGISTRY:
            raise ValueError(f"Unknown task: {self._task_id}. Available: {list(TASK_REGISTRY.keys())}")

        self._task_def = TASK_REGISTRY[task_key]
        self._state = copy.deepcopy(self._task_def["initial_state"])
        self._step_count = 0
        self._cumulative_reward = 0.0
        self._done = False
        self._action_history = []
        self._reward_history = []
        self._state["last_action_result"] = "Environment initialized. Investigate the system."

        obs = self._build_observation()
        return ResetResult(
            observation=obs,
            task_id=self._task_def["id"],
            task_description=self._task_def["description"],
            max_steps=self._task_def["max_steps"],
        )

    def step(self, action: SREAction) -> StepResult:
        """Execute one action and return (observation, reward, done, info)."""
        if self._done:
            obs = self._build_observation()
            return StepResult(
                observation=obs,
                reward=SREReward(value=0.0, cumulative=self._cumulative_reward, message="Episode already done"),
                done=True,
                info={"warning": "step() called after episode ended"},
            )

        self._step_count += 1
        max_steps = self._task_def["max_steps"]

        # Parse and execute action
        parsed = parse_action(action.raw)
        result_text, reward_delta, new_state = execute_action(parsed, self._state)
        self._state = new_state

        # Additional reward shaping
        reward_delta, reward_msg = self._shape_reward(parsed, reward_delta, result_text)

        self._cumulative_reward += reward_delta
        self._cumulative_reward = max(-5.0, min(5.0, self._cumulative_reward))  # soft clamp
        self._action_history.append(action.raw)
        self._reward_history.append(reward_delta)

        # Check completion
        done = self._check_done()
        if self._step_count >= max_steps:
            done = True

        self._done = done

        obs = self._build_observation()
        normalized_score = self._compute_normalized_score()

        reward = SREReward(
            value=max(-1.0, min(1.0, reward_delta)),
            cumulative=normalized_score,
            breakdown={"step_reward": reward_delta, "total_raw": self._cumulative_reward},
            message=reward_msg,
        )

        info = {
            "step": self._step_count,
            "max_steps": max_steps,
            "action_type": parsed.action_type.value,
            "normalized_score": normalized_score,
            "task_solved": self._state.get("task_solved", False),
        }

        return StepResult(observation=obs, reward=reward, done=done, info=info)

    def state(self) -> Dict[str, Any]:
        """Return the full internal state (for debugging/evaluation)."""
        return copy.deepcopy(self._state)

    def get_task_score(self) -> float:
        """Run the task grader and return score 0.0–1.0."""
        if self._task_def is None:
            return 0.0
        grader = self._task_def["grader"]
        return grader(self._state, self._action_history)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_observation(self) -> SREObservation:
        """Build a limited observation from full state (don't expose everything)."""
        files = self._state.get("files", {})
        services = self._state.get("services", {})
        logs = self._state.get("logs", [])

        # Only show last 10 logs
        recent_logs = logs[-10:] if logs else []

        # Show file paths but not contents
        files_visible = list(files.keys())

        # Hint system: give contextual hints every 5 steps
        hint = None
        if self._step_count > 0 and self._step_count % 5 == 0:
            hint = self._generate_hint()

        return SREObservation(
            task_id=self._task_def["id"] if self._task_def else "unknown",
            task_description=self._task_def["description"] if self._task_def else "",
            service_statuses=dict(services),
            recent_logs=recent_logs,
            last_action_result=self._state.get("last_action_result", ""),
            step_number=self._step_count,
            files_visible=files_visible,
            hint=hint,
        )

    def _shape_reward(self, action: ParsedAction, base_reward: float, result: str) -> tuple[float, str]:
        """Apply additional reward shaping rules."""
        msg = ""

        # Penalize repeated identical actions
        if len(self._action_history) >= 2:
            if action.raw == self._action_history[-1] == self._action_history[-2]:
                return -0.1, "Repeated action — no progress"

        # Penalize UNKNOWN actions
        if action.action_type == ActionType.UNKNOWN:
            return -0.1, f"Unrecognized action format: '{action.raw}'"

        # Reward discovering root cause
        if base_reward > 0:
            msg = "Good — discovered relevant information"
        elif base_reward < -0.3:
            msg = "Warning: potentially harmful action"
        elif base_reward < 0:
            msg = "No useful progress"

        # Check if task is now solved
        score = self.get_task_score()
        if score >= 0.95 and not self._state.get("task_solved"):
            self._state["task_solved"] = True
            bonus = 0.5
            msg = "🎉 Task solved! Full fix applied."
            return base_reward + bonus, msg

        return base_reward, msg

    def _check_done(self) -> bool:
        """Check if the episode should end."""
        if self._state.get("task_solved"):
            return True
        score = self.get_task_score()
        if score >= 0.95:
            self._state["task_solved"] = True
            return True
        return False

    def _compute_normalized_score(self) -> float:
        """Compute normalized score 0.0–1.0 from grader."""
        if self._task_def is None:
            return 0.0
        return self.get_task_score()

    def _generate_hint(self) -> str:
        """Generate contextual hints based on progress."""
        score = self.get_task_score()
        task_id = self._task_def["id"]
        services = self._state.get("services", {})

        if score < 0.1:
            return "Hint: Start by checking service statuses and reading relevant log files."
        elif score < 0.3:
            crashed = [s for s, v in services.items() if v in ("crashed", "failed", "overloaded")]
            if crashed:
                return f"Hint: Focus on why {crashed[0]} is not running. Check its config files."
        elif score < 0.6:
            return "Hint: You've made some progress. Make sure all config changes are saved and services restarted."
        else:
            return "Hint: Almost there — verify all services are running after your fixes."

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self._task_id,
            "step_count": self._step_count,
            "cumulative_reward": self._cumulative_reward,
            "done": self._done,
            "score": self.get_task_score(),
        }
