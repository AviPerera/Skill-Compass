"""Define controlled failures for the role-classification feature.

These exceptions separate configuration, input, and reconciliation failures;
they must not implement retry, network, persistence, or classification logic.
"""


class RoleClassificationError(Exception):
    """Base exception for controlled role-classification failures."""


class RoleConfigurationError(RoleClassificationError):
    """Report an invalid or unreadable governed role-rule document."""


class RoleInputError(RoleClassificationError):
    """Report an invalid or unreadable cleaned-job input."""


class RoleReconciliationError(RoleClassificationError):
    """Report output counts that do not reconcile to classifier input."""
