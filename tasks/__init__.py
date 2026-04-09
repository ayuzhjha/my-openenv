"""
tasks/__init__.py - Task registry for SRE OpenEnv
"""
from tasks.task_easy import TASK_EASY
from tasks.task_medium import TASK_MEDIUM
from tasks.task_hard import TASK_HARD
from tasks.task_custom import TASK_CUSTOM

TASK_REGISTRY = {
    "easy": TASK_EASY,
    "medium": TASK_MEDIUM,
    "hard": TASK_HARD,
    "custom": TASK_CUSTOM,
}

__all__ = ["TASK_REGISTRY", "TASK_EASY", "TASK_MEDIUM", "TASK_HARD", "TASK_CUSTOM"]
