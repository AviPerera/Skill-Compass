"""Expose application-layer data contracts for the Skill Compass pipeline.

This schema package defines typed boundaries and must not perform source
mapping, cleaning, persistence, or presentation work.
"""

from skill_compass.schemas.jobs import CleanedJob, MappedJob, RejectedRecord
from skill_compass.schemas.quality import QualityMetric

__all__ = ["CleanedJob", "MappedJob", "QualityMetric", "RejectedRecord"]
