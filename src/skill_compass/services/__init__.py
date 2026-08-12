"""Expose reusable application services that coordinate pipeline use cases.

Services compose mapping, cleaning, and adapters but must not contain their
business rules or presentation-only behavior.
"""

from skill_compass.services.clean_csv import CleaningRunResult, process_csv
from skill_compass.services.clean_jsonl import process_jsonl

__all__ = ["CleaningRunResult", "process_csv", "process_jsonl"]
