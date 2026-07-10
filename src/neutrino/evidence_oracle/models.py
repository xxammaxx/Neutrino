"""Evidence Oracle domain models — Issue #20.

This module defines all data models for the EvidenceOracle: evidence
items, bundles, check results, and the oracle's aggregated outcome.

Key invariants:
    - ALL models use ``extra="forbid"`` (no bypass fields).
    - ALL models are ``frozen=True`` (immutable).
    - ``EvidenceItem.scope_reference`` must not be empty.
    - ``EvidenceBundle.scope_reference`` must not be empty.
    - ``EvidenceOracleResult.status`` is deterministic: any FAIL → FAIL,
      else any WARN → WARN, else PASS.
    - No network I/O. No persistence. Pure domain models.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ------------------------------------------------------------------
# Reason Codes
# ------------------------------------------------------------------


class ReasonCode(StrEnum):
    """Deterministic reason codes for every oracle check.

    These are used in ``EvidenceCheckResult.reason_code`` and map
    directly to the checks performed in ``EvidenceOracle.evaluate``.

    FAIL codes:
        - MISSING_BUNDLE (bundle is None)
        - MISSING_ITEMS (no items in bundle)
        - MISSING_CONTENT (item has empty content)
        - MISSING_SCOPE_REFERENCE (scope_reference empty)
        - SCOPE_MISMATCH (item scope != bundle scope)
        - UNKNOWN_SCOPE (scope_reference is "UNKNOWN")
        - NO_REPRODUCIBILITY_MARKER (item has no reproducibility_marker)
        - EMPTY_REPRODUCIBILITY_MARKER (marker dict is empty)
        - MINIMAL_DATA_VIOLATION (item.minimal is not True)
        - SENSITIVE_DATA_DETECTED (item contains sensitive field)
        - EXCESSIVE_PAYLOAD (item exceeds byte limit)
        - UNKNOWN_DATA_CLASSIFICATION (kind is not known)

    PASS code:
        - OK

    WARN codes:
        - PAYLOAD_WARN (item exceeds soft limit but not hard limit)
    """

    MISSING_BUNDLE = "MISSING_BUNDLE"
    MISSING_ITEMS = "MISSING_ITEMS"
    MISSING_CONTENT = "MISSING_CONTENT"
    MISSING_SCOPE_REFERENCE = "MISSING_SCOPE_REFERENCE"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    UNKNOWN_SCOPE = "UNKNOWN_SCOPE"
    NO_REPRODUCIBILITY_MARKER = "NO_REPRODUCIBILITY_MARKER"
    EMPTY_REPRODUCIBILITY_MARKER = "EMPTY_REPRODUCIBILITY_MARKER"
    MINIMAL_DATA_VIOLATION = "MINIMAL_DATA_VIOLATION"
    SENSITIVE_DATA_DETECTED = "SENSITIVE_DATA_DETECTED"
    EXCESSIVE_PAYLOAD = "EXCESSIVE_PAYLOAD"
    UNKNOWN_DATA_CLASSIFICATION = "UNKNOWN_DATA_CLASSIFICATION"
    OK = "OK"
    PAYLOAD_WARN = "PAYLOAD_WARN"


# ------------------------------------------------------------------
# Sensitive Field Detection
# ------------------------------------------------------------------

#: Case-insensitive list of known sensitive field names.
#: Matching is recursive in dict keys, list elements, and tuples.
SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "passphrase",
        "secret",
        "secret_key",
        "token",
        "access_token",
        "access_token_secret",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "x-api-key",
        "x_api_key",
        "api-token",
        "api_token",
        "authorization",
        "proxy_authorization",
        "auth",
        "bearer",
        "jwt",
        "cookie",
        "set-cookie",
        "set_cookie",
        "session",
        "session_id",
        "csrf",
        "xsrf",
        "credential",
        "credentials",
        "private_key",
        "private",
        "pem",
        "signature",
        "signing_key",
        "encryption_key",
        "client_secret",
        "client_id_secret",
        "access_key",
        "access_key_id",
        "aws_access_key_id",
        "aws_secret_access_key",
        "database_url",
        "db_url",
        "dsn",
        "connection_string",
        "webhook_secret",
        "slack_token",
        "github_token",
        "gitlab_token",
        "ssh_key",
    }
)

# ------------------------------------------------------------------
# Payload Limits
# ------------------------------------------------------------------

#: Soft limit: items exceeding this get a WARN (PAYLOAD_WARN).
SOFT_ITEM_CONTENT_BYTES: int = 32 * 1024  # 32 KiB

#: Hard limit: items exceeding this get a FAIL (EXCESSIVE_PAYLOAD).
HARD_ITEM_CONTENT_BYTES: int = 64 * 1024  # 64 KiB

# ------------------------------------------------------------------
# Check Status
# ------------------------------------------------------------------


class CheckStatus(StrEnum):
    """Status of a single oracle check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


# ------------------------------------------------------------------
# Oracle Result Status
# ------------------------------------------------------------------


class OracleStatus(StrEnum):
    """Aggregated status of the oracle evaluation."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


# ------------------------------------------------------------------
# EvidenceItem
# ------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """A single, atomic piece of evidence.

    Carries the evidence payload, scope reference, reproducibility
    marker, and a ``minimal`` flag indicating whether only strictly
    necessary data is included.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, description="Unique evidence item identifier")
    kind: str = Field(
        min_length=1,
        description="Evidence kind (http_response, file_hash, screenshot, log_entry, …)",
    )
    scope_reference: str = Field(min_length=1, description="Scope reference for this evidence")
    source: str = Field(
        min_length=1, description="Origin of this evidence (recipe_id, step_id, run_id)"
    )
    content: dict[str, Any] = Field(default_factory=dict, description="The actual evidence payload")
    collected_at: str = Field(min_length=1, description="ISO 8601 collection timestamp")
    minimal: bool = Field(
        default=False, description="True if only strictly necessary data is included"
    )
    reproducibility_marker: dict[str, str] = Field(
        default_factory=dict,
        description="Marker for reproducibility (run_id, step_id, recipe_id, fixture_hash, …)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional non-decisional metadata"
    )


# ------------------------------------------------------------------
# EvidenceBundle
# ------------------------------------------------------------------


class EvidenceBundle(BaseModel):
    """A collection of EvidenceItems for a finding or validation run.

    The bundle's ``scope_reference`` is the expected scope; every item
    must carry a matching ``scope_reference``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, description="Unique bundle identifier")
    finding_id: str | None = Field(default=None, description="Associated finding ID, if any")
    scope_reference: str = Field(
        min_length=1, description="Expected scope for all items in this bundle"
    )
    items: list[EvidenceItem] = Field(
        default_factory=list, description="Evidence items in this bundle"
    )
    created_at: str = Field(min_length=1, description="ISO 8601 bundle creation timestamp")


# ------------------------------------------------------------------
# EvidenceCheckResult
# ------------------------------------------------------------------


class EvidenceCheckResult(BaseModel):
    """Result of a single oracle check against one (or more) items."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_name: str = Field(
        min_length=1, description="Name of the check (e.g. 'scope_check', 'reproducibility_check')"
    )
    status: CheckStatus = Field(description="PASS, FAIL, or WARN")
    reason_code: ReasonCode = Field(description="Machine-readable reason code")
    detail: str = Field(
        default="", description="Human-readable detail (never contains raw evidence)"
    )
    item_id: str | None = Field(
        default=None, description="Item ID this check applies to, if per-item"
    )


# ------------------------------------------------------------------
# EvidenceOracleResult
# ------------------------------------------------------------------


class EvidenceOracleResult(BaseModel):
    """Aggregated result of an EvidenceOracle evaluation.

    The ``status`` field is deterministically derived:
        - Any FAIL in ``checks`` → FAIL
        - Else any WARN → WARN
        - Else PASS
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: OracleStatus = Field(description="Aggregated oracle status: PASS, FAIL, or WARN")
    bundle_id: str = Field(default="", description="Bundle ID that was evaluated")
    checks: list[EvidenceCheckResult] = Field(
        default_factory=list, description="All individual check results"
    )
    errors: list[str] = Field(
        default_factory=list, description="Error descriptions (non-sensitive)"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Warning descriptions (non-sensitive)"
    )
    timestamp: str = Field(min_length=1, description="ISO 8601 evaluation timestamp")
