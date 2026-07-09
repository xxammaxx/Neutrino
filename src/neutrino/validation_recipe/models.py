"""Validation Recipe domain models for Issue #18.

This module defines the core Pydantic models for the Validation Recipe
schema. All models use strict validation with ``extra="forbid"`` to
prevent unknown fields from being silently accepted.

Key invariants:
    - NO execution — purely descriptive models.
    - Default-Deny: unknown fields, types, or values → rejection.
    - Lab-only: targets are validated conservatively.
    - Non-destructive: ``destructive=True`` → rejection.
    - No free shell: forbidden field names rejected by validators module.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ------------------------------------------------------------------
# Enum Types
# ------------------------------------------------------------------


class ValidationStepType(StrEnum):
    """Allowed step types for validation recipes.

    This is a NARROW allowlist. Unknown step types must fail validation.
    No generic command, scanner, exploit, or script types are permitted.

    Step types:
        http_check:
            A safe HTTP GET/HEAD request against a localhost target.
            No body, no auth, no redirects.
        tcp_check:
            A connect-only TCP check against a localhost target.
            No data sent, no banner-grabbing.
        evidence_check:
            Checks existing local evidence by ID. No external URLs.
        manual_observation:
            Human-readable checklist item — never auto-executed.
        local_fixture_check:
            Validates a local test fixture by ID. No arbitrary paths.
    """

    HTTP_CHECK = "http_check"
    TCP_CHECK = "tcp_check"
    EVIDENCE_CHECK = "evidence_check"
    MANUAL_OBSERVATION = "manual_observation"
    LOCAL_FIXTURE_CHECK = "local_fixture_check"


class ValidationSafetyClass(StrEnum):
    """Safety classification for recipes and steps.

    Only ``non_destructive`` is accepted. All other values or
    missing classification → validation failure.
    """

    NON_DESTRUCTIVE = "non_destructive"


class ValidationReasonCode(StrEnum):
    """Deterministic reason codes for validation results.

    Only ``VALID_RECIPE`` yields ``valid=True``.
    All other codes yield ``valid=False`` (Default-Deny / fail-closed).
    """

    VALID_RECIPE = "VALID_RECIPE"

    # Structural failures
    INVALID_FORBIDDEN_FIELD = "INVALID_FORBIDDEN_FIELD"
    INVALID_MISSING_REQUIRED = "INVALID_MISSING_REQUIRED"
    INVALID_UNKNOWN_FIELD = "INVALID_UNKNOWN_FIELD"
    INVALID_SCHEMA_VERSION = "INVALID_SCHEMA_VERSION"
    INVALID_MODEL_PARSE = "INVALID_MODEL_PARSE"

    # Step type failures
    INVALID_UNKNOWN_STEP_TYPE = "INVALID_UNKNOWN_STEP_TYPE"

    # Target failures
    INVALID_EXTERNAL_TARGET = "INVALID_EXTERNAL_TARGET"
    INVALID_TARGET_FORMAT = "INVALID_TARGET_FORMAT"

    # Scope failures
    INVALID_SCOPE_REFERENCE = "INVALID_SCOPE_REFERENCE"
    INVALID_STEP_SCOPE_NOT_IN_RECIPE = "INVALID_STEP_SCOPE_NOT_IN_RECIPE"
    INVALID_SCOPE_FORMAT = "INVALID_SCOPE_FORMAT"

    # Safety failures
    INVALID_DESTRUCTIVE_STEP = "INVALID_DESTRUCTIVE_STEP"
    INVALID_MISSING_SAFETY_CLASS = "INVALID_MISSING_SAFETY_CLASS"
    INVALID_UNKNOWN_SAFETY_CLASS = "INVALID_UNKNOWN_SAFETY_CLASS"

    # Step semantics
    INVALID_UNSAFE_PARAMETER = "INVALID_UNSAFE_PARAMETER"
    INVALID_DESTRUCTIVE_HTTP_METHOD = "INVALID_DESTRUCTIVE_HTTP_METHOD"
    INVALID_MISSING_APPROVAL_REQUIREMENT = "INVALID_MISSING_APPROVAL_REQUIREMENT"
    INVALID_MISSING_EVIDENCE = "INVALID_MISSING_EVIDENCE"

    # Bounds
    INVALID_RECIPE_TOO_LARGE = "INVALID_RECIPE_TOO_LARGE"
    INVALID_TOO_MANY_STEPS = "INVALID_TOO_MANY_STEPS"
    INVALID_NESTING_TOO_DEEP = "INVALID_NESTING_TOO_DEEP"


# ------------------------------------------------------------------
# ValidationResult
# ------------------------------------------------------------------


class ValidationResult(BaseModel):
    """Immutable, deterministic result of recipe validation.

    This is the output of ``validate_recipe()``. It contains a binary
    valid/invalid flag, a list of deterministic reason codes, human-
    readable error messages, warnings, and the recipe ID (if parseable).

    Fields:
        valid: Binary flag — True only when reason is VALID_RECIPE.
        errors: Human-readable error messages.
        warnings: Non-blocking warnings (e.g., deprecated patterns).
        recipe_id: The recipe ID if it could be safely extracted, else None.
        reasons: Deterministic reason codes explaining the decision.
    """

    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(default=False, description="True only for VALID_RECIPE")
    errors: list[str] = Field(default_factory=list, description="Human-readable error messages")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings")
    recipe_id: str | None = Field(default=None, description="Recipe ID if extractable")
    reasons: list[ValidationReasonCode] = Field(
        default_factory=list, description="Deterministic reason codes"
    )


# ------------------------------------------------------------------
# ValidationStep (Pydantic)
# ------------------------------------------------------------------


class ValidationStep(BaseModel):
    """A single structured validation step within a recipe.

    Each step describes exactly ONE non-destructive validation action.
    Every step requires a scope reference, approval requirement, and
    expected evidence specification.

    Fields:
        id: Unique step identifier within the recipe.
        name: Human-readable step name.
        step_type: Allowlisted step type (see ValidationStepType).
        target: The target of the validation. Must be loopback or
            scope-referenced lab placeholder.
        scope_reference: Reference to the scope policy permitting this
            target. Must be non-empty and present in recipe scope.
        requires_approval: Whether human approval is required before
            executing this step. Must be True for all target-touching steps.
        expected_evidence: Non-empty list of evidence IDs expected from
            this step.
        description: Optional human-readable description.
        parameters: Optional structured parameters. Must not contain
            forbidden keys. Validated by the recursive scanner.
        timeout_seconds: Optional bounded timeout (1-300).
        destructive: Must be explicitly False.
        safety_class: Must be "non_destructive".
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Unique step identifier")
    name: str = Field(min_length=1, description="Human-readable step name")
    step_type: ValidationStepType = Field(description="Allowlisted step type")
    target: str = Field(min_length=1, description="Target of the validation step")
    scope_reference: str = Field(
        min_length=1, description="Scope policy reference (must be in recipe scope)"
    )
    requires_approval: bool = Field(
        default=True, description="Whether human approval is required before execution"
    )
    expected_evidence: list[str] = Field(
        min_length=1, description="Non-empty list of expected evidence IDs"
    )
    description: str | None = Field(default=None, description="Optional description")
    parameters: dict[str, Any] | None = Field(
        default=None, description="Optional structured parameters"
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=300,
        description="Optional bounded timeout in seconds (1-300)",
    )
    destructive: bool = Field(
        default=False,
        description="Must be False — destructive steps are always rejected",
    )
    safety_class: ValidationSafetyClass = Field(
        default=ValidationSafetyClass.NON_DESTRUCTIVE,
        description="Safety classification — must be non_destructive",
    )

    @field_validator("destructive")
    @classmethod
    def destructive_must_be_false(cls, v: bool) -> bool:
        """Reject destructive steps at the model level."""
        if v is True:
            raise ValueError("destructive must be False")
        return v


# ------------------------------------------------------------------
# ValidationRecipe (Pydantic)
# ------------------------------------------------------------------

# Maximum safe limits for recipe inputs
MAX_RECIPE_SIZE = 65536  # 64 KB
MAX_STEPS = 20
MAX_NESTING_DEPTH = 8
MAX_STRING_LENGTH = 4096

# Allowed scope reference patterns
SCOPE_PATTERN_PREFIXES = ("scope:", "program:")
SCOPE_PATTERN_SEPARATORS = ("/", "#target:")


class ValidationRecipe(BaseModel):
    """Top-level validation recipe model.

    A recipe is a declarative container for structured, non-destructive
    validation steps. It defines the scope context and safety boundaries
    within which all steps operate.

    Fields:
        id: Unique recipe identifier.
        name: Human-readable recipe name.
        version: Structured version string (e.g., "1.0").
        description: Human-readable description.
        scope_references: Non-empty list of scope policy references.
            All step scopes must be subsets of these.
        steps: Non-empty list of validation steps.
        created_at: ISO 8601 timestamp.
        safety_class: Must be "non_destructive".
        destructive: Must be False.
        schema_version: Explicit schema version for this recipe format.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Unique recipe identifier")
    name: str = Field(min_length=1, description="Human-readable recipe name")
    version: str = Field(min_length=1, description="Structured version (e.g., '1.0')")
    description: str = Field(min_length=1, description="Human-readable description")
    scope_references: list[str] = Field(
        min_length=1, description="Non-empty list of scope policy references"
    )
    steps: list[ValidationStep] = Field(
        min_length=1, description="Non-empty list of validation steps"
    )
    created_at: str = Field(min_length=1, description="ISO 8601 creation timestamp")
    safety_class: ValidationSafetyClass = Field(
        default=ValidationSafetyClass.NON_DESTRUCTIVE,
        description="Must be non_destructive",
    )
    destructive: bool = Field(
        default=False,
        description="Must be False — destructive recipes are always rejected",
    )
    schema_version: str = Field(
        default="1.0",
        min_length=1,
        description="Schema version for this recipe format",
    )

    @field_validator("destructive")
    @classmethod
    def destructive_must_be_false(cls, v: bool) -> bool:
        """Reject destructive recipes at the model level."""
        if v is True:
            raise ValueError("destructive must be False")
        return v

    @field_validator("scope_references")
    @classmethod
    def scope_references_not_empty_strings(cls, v: list[str]) -> list[str]:
        """Ensure every scope reference is non-empty and non-whitespace."""
        for i, ref in enumerate(v):
            if not ref or not ref.strip():
                raise ValueError(f"scope_references[{i}] must be non-empty")
        return v
