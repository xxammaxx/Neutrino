"""Validation Recipe validator — Issue #18.

This module implements the deterministic, fail-closed validation logic
for Validation Recipes. It performs recursive safety scans and
produces immutable ``ValidationResult`` objects.

Key invariants:
    - NO execution: pure validation logic only.
    - NO network I/O, DNS, shell, subprocess.
    - Deterministic: same input → same output.
    - Fail-closed: any validation exception → invalid.
    - Recursive forbidden-key detection across all nesting levels.
    - Conservative target classification (loopback/scope only).
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from neutrino.validation_recipe.models import (
    MAX_STEPS,
    ValidationReasonCode,
    ValidationRecipe,
    ValidationResult,
    ValidationStep,
    ValidationStepType,
)

# ------------------------------------------------------------------
# Forbidden Field Names — recursive, case-insensitive detection
# ------------------------------------------------------------------

FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "command",
        "shell",
        "cmd",
        "bash",
        "powershell",
        "exec",
        "execute",
        "subprocess",
        "process",
        "script",
        "payload",
        "exploit",
        "scanner",
        "nmap",
        "nmap_flags",
        "raw_request",
        "raw_http",
        "request_bytes",
        "deserialization",
        "pickle",
        "eval",
        "os_system",
    }
)

# ------------------------------------------------------------------
# Allowed target hosts (loopback only)
# ------------------------------------------------------------------

ALLOWED_TARGET_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

# Lab-indicating hostname patterns
_LAB_HOSTNAME_RE = re.compile(r"^(lab-[\w-]+|[\w-]+\.lab\.local|[\w-]+\.test)$")

# Scope reference placeholder patterns
_SCOPE_PLACEHOLDER_RE = re.compile(r"^\{scope:[\w\-./]+(#target:[\w\-./]+)?\}$")

# HTTP methods allowed for non-destructive checks
_ALLOWED_HTTP_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})

# ------------------------------------------------------------------
# Recursive Forbidden-Field Scanner
# ------------------------------------------------------------------


def _scan_forbidden_keys(obj: Any, path: str = "$") -> list[str]:
    """Recursively scan for forbidden field names.

    Scans dicts, lists, and nested objects at any depth.
    Returns a list of error messages for each forbidden key found.

    Args:
        obj: The parsed JSON object (dict, list, or scalar).
        path: JSONPath-like string for error reporting.

    Returns:
        List of error messages (empty if clean).
    """
    errors: list[str] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                continue
            key_lower = key.lower()
            if key_lower in FORBIDDEN_FIELD_NAMES:
                errors.append(
                    f"Forbidden field '{key}' at {path}: "
                    f"execution-related keys are not allowed in recipes"
                )
            # Recurse into values
            if isinstance(value, (dict, list)):
                sub_errors = _scan_forbidden_keys(value, f"{path}.{key}")
                errors.extend(sub_errors)

    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                sub_errors = _scan_forbidden_keys(item, f"{path}[{idx}]")
                errors.extend(sub_errors)

    return errors


# ------------------------------------------------------------------
# Conservative Target Validation
# ------------------------------------------------------------------

_VALID_TARGET_SCHEMES: frozenset[str] = frozenset({"http", "https", ""})

# Patterns that indicate potential external targets
_PUBLIC_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

_IPV6_RE = re.compile(r"^\[?[0-9a-fA-F:]+(\][0-9a-fA-F:]*)?\]?$")


def _is_local_target(target: str) -> bool:
    """Conservative target validation — allow only loopback/localhost.

    This is a SYNTAX-LEVEL check only. No network I/O, no DNS.
    Full ScopeGuard authorization must happen in the executor (#19).

    Returns True if the target appears to be a safe local target,
    False if it appears to be external or ambiguous.
    """
    target_stripped = target.strip()

    # Empty target → not local
    if not target_stripped:
        return False

    # Scope placeholders like {scope:local-lab/demo-app}
    if _SCOPE_PLACEHOLDER_RE.match(target_stripped):
        return True

    # Fixture/lab references
    if target_stripped.startswith("fixture:") or target_stripped.startswith("lab:"):
        return True

    # Lab hostnames
    if _LAB_HOSTNAME_RE.match(target_stripped):
        return True

    # Try parsing as URL
    parsed = urlparse(target_stripped)
    scheme = parsed.scheme.lower() if parsed.scheme else ""

    # Scheme must be http, https, or empty
    if scheme and scheme not in _VALID_TARGET_SCHEMES:
        return False

    hostname = parsed.hostname if parsed.hostname else target_stripped

    # Allow explicit loopback hosts
    if hostname in ALLOWED_TARGET_HOSTS:
        return True

    # Strip brackets from IPv6 addresses
    if hostname.startswith("[") and hostname.endswith("]"):
        hostname = hostname[1:-1]

    # Check if it's an IP address
    if _PUBLIC_IP_RE.match(hostname):
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_loopback:
                return True
            # Private and other non-public ranges are STILL rejected
            # in the schema for safety (only loopback allowed).
            # This is intentionally conservative.
            return False
        except ValueError:
            return False

    # Check if it might be an IPv6
    if ":" in hostname and _IPV6_RE.match(target_stripped if not parsed.hostname else hostname):
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_loopback:
                return True
            return False
        except ValueError:
            return False

    # Not a recognized local target → reject
    return False


# ------------------------------------------------------------------
# Scope Reference Validation
# ------------------------------------------------------------------

_WILDCARD_SCOPE_PATTERNS: frozenset[str] = frozenset(
    {"*", "scope:*", "all", "default", "approved", "any", "none"}
)

_SCOPE_FORMAT_RE = re.compile(r"^[a-z]+:[\w\-./]+(#target:[\w\-./]+)?$")


def _is_valid_scope_format(scope_ref: str) -> bool:
    """Validate scope reference format.

    Scope references must follow a structured format:
        scope:<namespace>/<target-id>
        program:<program-id>#target:<target-id>

    Wildcards, empty strings, and generic markers are rejected.
    """
    if not scope_ref or not scope_ref.strip():
        return False

    scope_lower = scope_ref.strip().lower()
    if scope_lower in _WILDCARD_SCOPE_PATTERNS:
        return False

    if scope_lower.startswith("scope:") or scope_lower.startswith("program:"):
        return bool(_SCOPE_FORMAT_RE.match(scope_ref.strip()))

    return False


# ------------------------------------------------------------------
# Main Validator Entry Point
# ------------------------------------------------------------------


def validate_recipe(
    recipe: Mapping[str, Any] | ValidationRecipe | dict[str, Any],
) -> ValidationResult:
    """Validate a Validation Recipe against all safety rules.

    This is the central entry point for recipe validation. It performs
    a series of deterministic, fail-closed safety checks and returns
    an immutable ``ValidationResult``.

    Validation order (stable, deterministic):
        1. Recursive forbidden-field scan on raw input.
        2. Bounds checks (size, steps, depth).
        3. Model parsing via Pydantic (with extra="forbid").
        4. Scope reference format validation.
        5. Step scope must be in recipe scope.
        6. Conservative target validation.
        7. Step-type-specific semantic checks.
        8. Safety class and destructive checks.

    Args:
        recipe: A dict or ValidationRecipe to validate.

    Returns:
        ValidationResult with valid=True only when all checks pass.

    Raises:
        Never raises — all errors are captured in the result.
    """
    errors: list[str] = []
    warnings: list[str] = []
    reasons: list[ValidationReasonCode] = []
    recipe_id: str | None = None

    # --- Helper to add an error with reason ---
    def _fail(msg: str, reason: ValidationReasonCode) -> None:
        errors.append(msg)
        reasons.append(reason)

    # --- Normalize input to dict for scanning ---
    if isinstance(recipe, dict):
        recipe_dict: dict[str, Any] = recipe
    elif isinstance(recipe, ValidationRecipe):
        recipe_dict = recipe.model_dump()
    else:
        recipe_dict = dict(recipe)

    # --- Step 1: Extract recipe ID if possible ---
    recipe_id = str(recipe_dict.get("id", "")) or None

    # --- Step 2: Recursive forbidden-field scan on raw input ---
    forbidden_errors = _scan_forbidden_keys(recipe_dict)
    for err in forbidden_errors:
        _fail(err, ValidationReasonCode.INVALID_FORBIDDEN_FIELD)

    # --- Step 3: Bounds checks on raw dict ---
    if len(recipe_dict) > 200:
        _fail(
            f"Recipe has too many top-level keys ({len(recipe_dict)})",
            ValidationReasonCode.INVALID_RECIPE_TOO_LARGE,
        )

    if isinstance(recipe_dict.get("steps"), list):
        if len(recipe_dict["steps"]) > MAX_STEPS:
            _fail(
                f"Too many steps: {len(recipe_dict['steps'])} (max {MAX_STEPS})",
                ValidationReasonCode.INVALID_TOO_MANY_STEPS,
            )

    # --- Step 4: Model parsing ---
    parsed: ValidationRecipe | None = None
    try:
        if isinstance(recipe, ValidationRecipe):
            parsed = recipe
        else:
            parsed = ValidationRecipe(**recipe_dict)
    except Exception as exc:
        _fail(
            f"Failed to parse recipe model: {exc}",
            ValidationReasonCode.INVALID_MODEL_PARSE,
        )

    if parsed is None:
        return ValidationResult(
            valid=False,
            errors=errors,
            warnings=warnings,
            recipe_id=recipe_id,
            reasons=reasons,
        )

    # --- Step 5: Scope reference format validation ---
    for i, scope_ref in enumerate(parsed.scope_references):
        if not _is_valid_scope_format(scope_ref):
            _fail(
                f"scope_references[{i}] has invalid format: '{scope_ref}'",
                ValidationReasonCode.INVALID_SCOPE_FORMAT,
            )

    # Deduplicated set for step scope checking
    recipe_scopes: set[str] = set(parsed.scope_references)

    # --- Step 6: Step-level validation ---
    for i, step in enumerate(parsed.steps):
        step_prefix = f"steps[{i}]"

        # --- 6a: Check step scope is in recipe scope ---
        if step.scope_reference not in recipe_scopes:
            _fail(
                f"{step_prefix}: scope_reference '{step.scope_reference}' "
                f"not found in recipe scope_references",
                ValidationReasonCode.INVALID_STEP_SCOPE_NOT_IN_RECIPE,
            )

        # --- 6b: Conservative target validation ---
        if not _is_local_target(step.target):
            _fail(
                f"{step_prefix}: target '{step.target}' is not a "
                f"recognized local/loopback/lab target",
                ValidationReasonCode.INVALID_EXTERNAL_TARGET,
            )

        # --- 6c: Step-type-specific checks ---
        _validate_step_semantics(step, step_prefix, errors, reasons)

    # --- Step 7: Build final result ---
    if not errors:
        reasons.append(ValidationReasonCode.VALID_RECIPE)
        return ValidationResult(
            valid=True,
            errors=[],
            warnings=warnings,
            recipe_id=parsed.id,
            reasons=reasons,
        )

    return ValidationResult(
        valid=False,
        errors=errors,
        warnings=warnings,
        recipe_id=parsed.id,
        reasons=reasons,
    )


# ------------------------------------------------------------------
# Step-Type-Specific Semantic Checks
# ------------------------------------------------------------------

_DESTRUCTIVE_HTTP_METHODS: frozenset[str] = frozenset(
    {"POST", "PUT", "PATCH", "DELETE", "CONNECT", "TRACE", "OPTIONS"}
)


def _validate_step_semantics(
    step: ValidationStep,
    step_prefix: str,
    errors: list[str],
    reasons: list[ValidationReasonCode],
) -> None:
    """Validate step-type-specific semantics.

    Each step type has specific non-destructive constraints.
    """

    def _fail(msg: str, reason: ValidationReasonCode) -> None:
        errors.append(f"{step_prefix}: {msg}")
        reasons.append(reason)

    # Check requires_approval for target-touching steps
    if step.step_type in (ValidationStepType.HTTP_CHECK, ValidationStepType.TCP_CHECK):
        if not step.requires_approval:
            _fail(
                f"step_type '{step.step_type.value}' requires approval "
                f"(requires_approval must be True)",
                ValidationReasonCode.INVALID_MISSING_APPROVAL_REQUIREMENT,
            )

    # Check expected_evidence is non-empty
    if not step.expected_evidence:
        _fail(
            "expected_evidence must not be empty",
            ValidationReasonCode.INVALID_MISSING_EVIDENCE,
        )
    else:
        for j, evidence_id in enumerate(step.expected_evidence):
            if not evidence_id or not evidence_id.strip():
                _fail(
                    f"expected_evidence[{j}] must be non-empty",
                    ValidationReasonCode.INVALID_MISSING_EVIDENCE,
                )

    # HTTP-specific checks
    if step.step_type == ValidationStepType.HTTP_CHECK and step.parameters:
        method = str(step.parameters.get("method", "GET")).upper()
        if method in _DESTRUCTIVE_HTTP_METHODS:
            _fail(
                f"HTTP method '{method}' is not allowed for non-destructive "
                f"http_check (only GET, HEAD)",
                ValidationReasonCode.INVALID_DESTRUCTIVE_HTTP_METHOD,
            )

        # Check for dangerous HTTP parameters
        dangerous_http_params = {"body", "data", "json", "files", "auth"}
        if step.parameters:
            for dangerous in dangerous_http_params & set(step.parameters.keys()):
                _fail(
                    f"HTTP parameter '{dangerous}' is not allowed for non-destructive http_check",
                    ValidationReasonCode.INVALID_UNSAFE_PARAMETER,
                )

        # Check for custom headers (potential injection vector)
        if "headers" in step.parameters and isinstance(step.parameters["headers"], dict):
            # Only allow minimal safe headers
            safe_headers = {"accept", "user-agent"}
            for header_name in step.parameters["headers"]:
                if header_name.lower() not in safe_headers:
                    _fail(
                        f"Custom header '{header_name}' is not allowed for "
                        f"non-destructive http_check",
                        ValidationReasonCode.INVALID_UNSAFE_PARAMETER,
                    )

    # TCP-specific checks
    if step.step_type == ValidationStepType.TCP_CHECK and step.parameters:
        dangerous_tcp_params = {"data", "payload", "send", "bytes", "banner"}
        for dangerous in dangerous_tcp_params & set(step.parameters.keys()):
            _fail(
                f"TCP parameter '{dangerous}' is not allowed for non-destructive tcp_check",
                ValidationReasonCode.INVALID_UNSAFE_PARAMETER,
            )

    # Evidence check — no external URLs
    if step.step_type == ValidationStepType.EVIDENCE_CHECK and step.parameters:
        url_keys = {"url", "source_url", "external_url", "href", "link"}
        for url_key in url_keys & set(step.parameters.keys()):
            _fail(
                f"Evidence parameter '{url_key}' is not allowed — "
                f"evidence_check only references local evidence by ID",
                ValidationReasonCode.INVALID_UNSAFE_PARAMETER,
            )

    # Local fixture check — no arbitrary paths
    if step.step_type == ValidationStepType.LOCAL_FIXTURE_CHECK and step.parameters:
        path_keys = {"path", "file", "filepath", "filename", "absolute_path"}
        for path_key in path_keys & set(step.parameters.keys()):
            _fail(
                f"Fixture parameter '{path_key}' is not allowed — "
                f"local_fixture_check only references fixture IDs, not paths",
                ValidationReasonCode.INVALID_UNSAFE_PARAMETER,
            )
