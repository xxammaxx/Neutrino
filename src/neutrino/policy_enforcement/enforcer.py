"""Program Policy Prohibition Enforcer — deterministic, local enforcement.

The ``ProgramPolicyEnforcer`` evaluates a ``ProgramPolicyIntent`` against a
``ScopePolicy``'s automation policies, prohibited/allowed test types, and
blocking rules, producing an immutable ``ProgramPolicyDecision``.

Core guarantees:
    - DENY can never be overridden. If any check denies, the result is DENY.
    - Missing, incomplete, or unknown policies are treated conservatively: DENY.
    - Prohibited test types always win over allowed test types.
    - Blocking rules always win over allowed test types.
    - No network I/O, no DNS, no scheduler, no persistent audit log.
    - All decisions are deterministic: same inputs → same decision.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from neutrino.policy_enforcement.models import (
    ProgramPolicyDecision,
    ProgramPolicyDecisionStatus,
    ProgramPolicyIntent,
    ProgramPolicyReason,
    ProgramPolicyViolation,
)

if TYPE_CHECKING:
    from neutrino.models.policy import ScopePolicy


class ProgramPolicyEnforcer:
    """Deterministic, local enforcement of program-specific prohibitions.

    Evaluates a ``ProgramPolicyIntent`` against a ``ScopePolicy``'s
    prohibition rules. Does NOT execute requests, DNS lookups, or any
    network I/O.

    Usage::

        enforcer = ProgramPolicyEnforcer()
        intent = ProgramPolicyIntent(
            target="api.example.com",
            test_type="api_testing",
            automation=True,
        )
        decision = enforcer.check_intent(intent, policy)
        if decision.is_allowed:
            # test type is permitted by the policy
        else:
            # blocked — decision.explanation explains why
            # decision.violation contains serializable audit evidence
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_intent(
        self,
        intent: ProgramPolicyIntent,
        policy: ScopePolicy | None,
    ) -> ProgramPolicyDecision:
        """Evaluate a test intent against program-specific prohibition rules.

        Evaluation order (first match determines outcome):
            1. Missing policy → DENY_MISSING_POLICY
            2. Invalid / empty test type → DENY_INVALID_INTENT
            3. Test type normalization
            4. Prohibited test types → DENY_PROHIBITED_TEST_TYPE
            5. Blocking PolicyRules → DENY_BLOCKING_POLICY_RULE
            6. Automation policy → DENY_AUTOMATION_*
            7. Allowed test types → ALLOW or DENY_UNKNOWN_TEST_TYPE

        Args:
            intent: The test intent to evaluate (no I/O performed).
            policy: The ScopePolicy to check against. If None, DENY.

        Returns:
            A ``ProgramPolicyDecision`` — ALLOW if permitted, DENY otherwise.
        """
        # --- 1: Missing policy → immediate DENY ---
        if policy is None:
            return self._deny(
                target=intent.target,
                test_type=intent.test_type,
                reason=ProgramPolicyReason.DENY_MISSING_POLICY,
                explanation="No ScopePolicy provided — all test intents are denied.",
            )

        # --- 2: Validate intent ---
        raw_test_type = intent.test_type
        if not raw_test_type or not raw_test_type.strip():
            return self._deny(
                target=intent.target,
                test_type=raw_test_type,
                reason=ProgramPolicyReason.DENY_INVALID_INTENT,
                explanation=f"Test type is empty or invalid: {raw_test_type!r}.",
                policy_source=policy.source_url,
            )

        # --- 3: Normalize test type ---
        normalized = self._normalize_test_type(raw_test_type)

        # --- 4: Check prohibited test types ---
        for prohibited in policy.prohibited_test_types:
            norm_prohibited = self._normalize_test_type(prohibited)
            if normalized == norm_prohibited:
                return self._deny_with_violation(
                    target=intent.target,
                    test_type=normalized,
                    reason=ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE,
                    matched_policy_item=prohibited,
                    policy_source=policy.source_url,
                    automation=intent.automation,
                    explanation=(
                        f"Test type {normalized!r} is explicitly prohibited "
                        f"by the policy (matched: {prohibited!r})."
                    ),
                )

        # --- 5: Check blocking PolicyRules ---
        for rule in policy.rules:
            if rule.is_blocking and self._rule_matches_test_type(rule.description, normalized):
                return self._deny_with_violation(
                    target=intent.target,
                    test_type=normalized,
                    reason=ProgramPolicyReason.DENY_BLOCKING_POLICY_RULE,
                    matched_policy_item=rule.description,
                    policy_source=policy.source_url,
                    automation=intent.automation,
                    explanation=(
                        f"Test type {normalized!r} is blocked by policy rule: {rule.description!r}."
                    ),
                )

        # --- 6: Check automation policy ---
        if intent.automation:
            auto_status = policy.automation_policy.status
            if auto_status == "prohibited":
                return self._deny_with_violation(
                    target=intent.target,
                    test_type=normalized,
                    reason=ProgramPolicyReason.DENY_AUTOMATION_PROHIBITED,
                    matched_policy_item=f"automation_policy.status={auto_status}",
                    policy_source=policy.source_url,
                    automation=True,
                    explanation=(
                        f"Automated testing is explicitly prohibited by the policy "
                        f"for {intent.target!r}."
                    ),
                )
            if auto_status == "requires_approval":
                return self._deny_with_violation(
                    target=intent.target,
                    test_type=normalized,
                    reason=ProgramPolicyReason.DENY_AUTOMATION_REQUIRES_APPROVAL,
                    matched_policy_item=f"automation_policy.status={auto_status}",
                    policy_source=policy.source_url,
                    automation=True,
                    explanation=(
                        f"Automated testing requires prior approval for "
                        f"{intent.target!r}. No approval workflow implemented."
                    ),
                )
            if auto_status == "unknown":
                return self._deny_with_violation(
                    target=intent.target,
                    test_type=normalized,
                    reason=ProgramPolicyReason.DENY_AUTOMATION_UNKNOWN,
                    matched_policy_item=f"automation_policy.status={auto_status}",
                    policy_source=policy.source_url,
                    automation=True,
                    explanation=(
                        f"Automation policy is unknown for {intent.target!r} "
                        f"— conservative default is DENY."
                    ),
                )
            # auto_status == "allowed" — continue to test type check

        # --- 7: Check allowed test types (default deny) ---
        if not policy.allowed_test_types:
            # No allowed test types specified → deny unknown
            return self._deny_with_violation(
                target=intent.target,
                test_type=normalized,
                reason=ProgramPolicyReason.DENY_UNKNOWN_TEST_TYPE,
                matched_policy_item="allowed_test_types is empty",
                policy_source=policy.source_url,
                automation=intent.automation,
                explanation=(
                    f"Test type {normalized!r} is not explicitly allowed "
                    f"(policy has no allowed_test_types list)."
                ),
            )

        # Check if normalized test type is in normalized allowed list
        for allowed in policy.allowed_test_types:
            if normalized == self._normalize_test_type(allowed):
                return ProgramPolicyDecision(
                    target=intent.target,
                    status=ProgramPolicyDecisionStatus.ALLOW,
                    reason=ProgramPolicyReason.ALLOW_POLICY_PERMITS_TEST_TYPE,
                    test_type=normalized,
                    explanation=(
                        f"Test type {normalized!r} is explicitly allowed by "
                        f"the policy for {intent.target!r}."
                    ),
                    policy_source=policy.source_url,
                )

        # Not in allowed list → deny
        return self._deny_with_violation(
            target=intent.target,
            test_type=normalized,
            reason=ProgramPolicyReason.DENY_UNKNOWN_TEST_TYPE,
            matched_policy_item="not in allowed_test_types",
            policy_source=policy.source_url,
            automation=intent.automation,
            explanation=(
                f"Test type {normalized!r} is not in the policy's allowed_test_types list."
            ),
        )

    # ------------------------------------------------------------------
    # Test type normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_test_type(test_type: str) -> str:
        """Normalize a test type string for deterministic comparison.

        Performs:
            - Whitespace trimming
            - Lowercase normalization
            - Replace spaces, hyphens, dots with underscores
            - Collapse consecutive underscores
            - Strip leading/trailing underscores

        Examples:
            "brute force" → "brute_force"
            "brute-force" → "brute_force"
            "brute_force"  → "brute_force"
            "CREDENTIAL-STUFFING" → "credential_stuffing"
        """
        normalized = test_type.strip().lower()
        # Replace common delimiters with underscores
        normalized = re.sub(r"[\s\-\.]", "_", normalized)
        # Collapse multiple underscores
        normalized = re.sub(r"_+", "_", normalized)
        # Strip leading/trailing underscores
        normalized = normalized.strip("_")
        return normalized

    # ------------------------------------------------------------------
    # Rule matching
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_matches_test_type(rule_description: str, normalized_test_type: str) -> bool:
        """Check if a policy rule description matches a test type.

        Uses deterministic keyword matching: normalizes the rule description
        and checks if the test type appears as a substring.

        No semantic LLM interpretation. Only structural string matching.

        Examples:
            "Do not perform brute force attacks" + "brute_force" → True
            "No credential stuffing allowed" + "credential_stuffing" → True
            "Report all findings" + "brute_force" → False

        Args:
            rule_description: The rule's description text.
            normalized_test_type: The already-normalized test type.

        Returns:
            True if the test type appears in the normalized description.
        """
        if not rule_description:
            return False
        norm_desc = ProgramPolicyEnforcer._normalize_test_type(rule_description)
        return normalized_test_type in norm_desc

    # ------------------------------------------------------------------
    # Decision helpers
    # ------------------------------------------------------------------

    def _deny(
        self,
        *,
        target: str,
        test_type: str,
        reason: ProgramPolicyReason,
        explanation: str,
        policy_source: str | None = None,
    ) -> ProgramPolicyDecision:
        """Create a DENY decision (no violation evidence)."""
        return ProgramPolicyDecision(
            target=target,
            status=ProgramPolicyDecisionStatus.DENY,
            reason=reason,
            test_type=test_type,
            explanation=explanation,
            policy_source=policy_source,
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def _deny_with_violation(
        self,
        *,
        target: str,
        test_type: str,
        reason: ProgramPolicyReason,
        explanation: str,
        matched_policy_item: str | None = None,
        policy_source: str | None = None,
        automation: bool = False,
    ) -> ProgramPolicyDecision:
        """Create a DENY decision with violation evidence (serializable audit trail)."""
        return ProgramPolicyDecision(
            target=target,
            status=ProgramPolicyDecisionStatus.DENY,
            reason=reason,
            test_type=test_type,
            explanation=explanation,
            policy_source=policy_source,
            violation=ProgramPolicyViolation(
                target=target,
                test_type=test_type,
                automation=automation,
                reason=str(reason),
                matched_policy_item=matched_policy_item,
                policy_source=policy_source,
                explanation=explanation,
            ),
        )
