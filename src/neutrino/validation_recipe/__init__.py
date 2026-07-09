"""Validation Recipe Schema — Issue #18.

This module defines the schema, models, and validation logic for
structured, non-destructive Validation Recipes. Recipes describe
declarative validation steps that may LATER be executed by a separate
executor (Issue #19).

Key invariants:
    - NO execution: this module validates schema ONLY.
    - Default-Deny: unknown fields, types, or targets → invalid.
    - Fail-closed: validation exceptions → invalid.
    - Lab-only: targets must be localhost, loopback, or explicitly
      scope-referenced lab placeholders.
    - No free shell: forbidden field names are detected recursively.
    - Non-destructive by construction: destructive=True → invalid.

Exports:
    ValidationRecipe          — top-level recipe model
    ValidationStep            — individual step model
    ValidationStepType        — allowed step type enum
    ValidationSafetyClass     — safety classification enum
    ValidationResult          — validator output model
    ValidationReasonCode      — deterministic reason codes
    validate_recipe           — main entry point
    export_json_schema        — JSON Schema export helper
    FORBIDDEN_FIELD_NAMES     — blocklist for recursive scan
"""

from neutrino.validation_recipe.models import (
    ValidationReasonCode,
    ValidationRecipe,
    ValidationResult,
    ValidationSafetyClass,
    ValidationStep,
    ValidationStepType,
)
from neutrino.validation_recipe.schema import export_json_schema
from neutrino.validation_recipe.validators import (
    FORBIDDEN_FIELD_NAMES,
    validate_recipe,
)

__all__ = [
    "ValidationRecipe",
    "ValidationStep",
    "ValidationStepType",
    "ValidationSafetyClass",
    "ValidationResult",
    "ValidationReasonCode",
    "validate_recipe",
    "export_json_schema",
    "FORBIDDEN_FIELD_NAMES",
]
