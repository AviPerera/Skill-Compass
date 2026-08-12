"""Expose deterministic, configuration-driven requirement extraction.

The extraction package consumes typed cleaned jobs and must not perform file
I/O, chart rendering, database persistence, or role/seniority classification.
"""

from skill_compass.extraction.dictionary import load_requirement_dictionary
from skill_compass.extraction.matcher import extract_job_evidence
from skill_compass.extraction.profile import load_extraction_profile

__all__ = [
    "extract_job_evidence",
    "load_extraction_profile",
    "load_requirement_dictionary",
]
