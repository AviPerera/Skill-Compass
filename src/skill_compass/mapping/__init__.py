"""Expose canonical source-mapping services and configuration contracts.

This package is the source-specific mapping boundary and must not read CSV
files, clean canonical values, or write pipeline outputs.
"""

from skill_compass.mapping.config import SourceMappingConfig, load_mapping_config
from skill_compass.mapping.service import MappingOutcome, map_source_row

__all__ = [
    "MappingOutcome",
    "SourceMappingConfig",
    "load_mapping_config",
    "map_source_row",
]
