"""Define controlled failures for deterministic classification features.

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


class SeniorityClassificationError(Exception):
    """Base exception for controlled seniority-classification failures."""


class SeniorityConfigurationError(SeniorityClassificationError):
    """Report an invalid or unreadable seniority-rule document."""


class SeniorityInputError(SeniorityClassificationError):
    """Report an invalid or unreadable cleaned-job input."""


class SeniorityReconciliationError(SeniorityClassificationError):
    """Report seniority outputs that do not reconcile to classifier input."""


class RelevanceClassificationError(Exception):
    """Base exception for controlled profile-relevance failures."""


class RelevanceConfigurationError(RelevanceClassificationError):
    """Report an invalid or unreadable governed relevance-rule document."""


class RelevanceInputError(RelevanceClassificationError):
    """Report incomplete, duplicate, or unreadable relevance input."""


class RelevanceReconciliationError(RelevanceClassificationError):
    """Report relevance outputs that do not reconcile to classifier input."""
