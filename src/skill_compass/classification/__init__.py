"""Expose reusable deterministic classification capabilities.

This package owns generic explainable classification logic and must not contain
source-specific field paths, dashboard rendering, or network integrations.
"""

from skill_compass.classification.config import load_role_rules
from skill_compass.classification.roles import classify_job_role, classify_roles

__all__ = ["classify_job_role", "classify_roles", "load_role_rules"]
