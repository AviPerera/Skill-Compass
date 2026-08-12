"""Expose reusable deterministic classification capabilities.

This package owns generic explainable classification logic and must not contain
source-specific field paths, dashboard rendering, or network integrations.
"""

from skill_compass.classification.config import load_role_rules
from skill_compass.classification.roles import classify_job_role, classify_roles
from skill_compass.classification.seniority import (
    classify_job_seniority,
    classify_seniority,
)
from skill_compass.classification.seniority_config import load_seniority_rules

__all__ = [
    "classify_job_role",
    "classify_job_seniority",
    "classify_roles",
    "classify_seniority",
    "load_role_rules",
    "load_seniority_rules",
]
