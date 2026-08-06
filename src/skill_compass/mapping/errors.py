"""Define controlled failures for source-mapping configuration and execution.

These exceptions belong to the mapping boundary and must not format terminal
output or conceal unexpected programming errors.
"""


class MappingConfigurationError(ValueError):
    """Report a fatal invalid or unsafe mapping configuration."""
