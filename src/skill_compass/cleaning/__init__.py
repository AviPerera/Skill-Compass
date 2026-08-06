"""Expose source-independent deterministic cleaning for canonical job records.

This package accepts typed mapped records and must not understand source CSV
column names, perform file I/O, or implement classification and extraction.
"""

from skill_compass.cleaning.service import clean_mapped_job

__all__ = ["clean_mapped_job"]
