"""Define controlled failures for extraction configuration and publication.

These exceptions cross application boundaries safely and must not include job
descriptions, contact details, source URLs, or raw input payloads.
"""


class ExtractionConfigurationError(ValueError):
    """Report an invalid profile or requirement dictionary contract."""


class ExtractionReconciliationError(RuntimeError):
    """Report extraction counts that cannot be reconciled safely."""


class ExtractionInputError(ValueError):
    """Report an invalid or duplicate cleaned-job input contract."""
