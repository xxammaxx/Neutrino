"""Evidence Oracle — Issue #20.

This package implements the EvidenceOracle: a deterministic, fail-closed
quality evaluator for evidence bundles produced by the
ValidationRecipeExecutor and other local lab data sources.

Key components:
    - ``EvidenceOracle`` — Core evaluator performing minimum quality
      checks (scope, reproducibility, minimal data, sensitive fields,
      content presence).
    - ``EvidenceItem`` — A single atomic piece of evidence.
    - ``EvidenceBundle`` — A collection of items for a finding or run.
    - ``EvidenceCheckResult`` — Result of a single oracle check.
    - ``EvidenceOracleResult`` — Aggregated oracle outcome.
    - ``ReasonCode`` — Deterministic reason codes for every check.

Design invariants:
    - Deterministic: same inputs → same outputs.
    - Fail-closed: any FAIL → overall FAIL.
    - No network I/O, shell, subprocess, DNS, or scanners.
    - No real targets, no active validation.
    - No #21 Evidence-State-Diffing.
    - No report submission, upload, or remote logging.
    - Sensitive field detection is recursive and case-insensitive.
    - Logs never contain raw evidence data.
"""

from neutrino.evidence_oracle.models import (
    HARD_ITEM_CONTENT_BYTES,
    SENSITIVE_FIELDS,
    SOFT_ITEM_CONTENT_BYTES,
    CheckStatus,
    EvidenceBundle,
    EvidenceCheckResult,
    EvidenceItem,
    EvidenceOracleResult,
    OracleStatus,
    ReasonCode,
)
from neutrino.evidence_oracle.oracle import EvidenceOracle

__all__ = [
    "EvidenceOracle",
    "EvidenceItem",
    "EvidenceBundle",
    "EvidenceCheckResult",
    "EvidenceOracleResult",
    "ReasonCode",
    "CheckStatus",
    "OracleStatus",
    "SENSITIVE_FIELDS",
    "SOFT_ITEM_CONTENT_BYTES",
    "HARD_ITEM_CONTENT_BYTES",
]
