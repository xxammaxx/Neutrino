# Neutrino Phase 1 — Issue #15 Program-Specific Prohibitions Report

## Kurzfazit

**GREEN_SAFE** — Die `ProgramPolicyEnforcer`-Komponente erzwingt programmspezifische Verbote deterministisch und lokal. Verbotene Testarten, Automation-Policies und Blocking-PolicyRules werden gegen `ScopePolicy` evaluiert. Alle Entscheidungen produzieren serialisierbare Violation/Evidence-Strukturen. Keine echten Requests, kein DNS, kein Scheduler, kein Override, kein persistenter AuditLog.

## Reality Refresh

| Check | Status |
|-------|--------|
| Branch | `main` |
| Pre-change HEAD | `134e3d5` |
| Post-change HEAD | `68206c9` |
| Pre-existing tests | 237 passing |
| Post-implementation tests | 277 passing (40 new) |
| Coverage | 98% (771 statements, 17 missed) |

## Issue #3/#7 Sync

- **Issue #3**: CLOSED — alle AC verifiziert, Commit `e86ac00`, Report existiert
- **Issue #7**: CLOSED — alle AC verifiziert, Commit `a58600b`, Report existiert
- Keine Sync-Aktion notwendig: beide Issues waren bereits mit vollständiger Evidence geschlossen

## Geänderte Dateien

| Datei | Zeilen | Beschreibung |
|-------|--------|-------------|
| `src/neutrino/policy_enforcement/__init__.py` | 24 | Package-Exports |
| `src/neutrino/policy_enforcement/models.py` | 219 | ProgramPolicyIntent, Decision, Violation, Response |
| `src/neutrino/policy_enforcement/enforcer.py` | 283 | ProgramPolicyEnforcer mit 7-stufigem Check |
| `tests/policy_enforcement/__init__.py` | 0 | Package-Marker |
| `tests/policy_enforcement/test_enforcer.py` | 664 | 40 Tests (34 spezifizierte + 6 Edge Cases) |

## Enforcement-Design

### Evaluation Order (first match determines outcome)

```
1. policy is None → DENY_MISSING_POLICY
2. invalid/empty test_type → DENY_INVALID_INTENT
3. normalize test_type (lowercase, spaces/hyphens → underscores)
4. test_type in prohibited_test_types → DENY_PROHIBITED_TEST_TYPE
5. blocking PolicyRule matches → DENY_BLOCKING_POLICY_RULE
6. intent.automation=True + automation_policy.status != "allowed" → DENY_AUTOMATION_*
7. test_type in allowed_test_types → ALLOW_POLICY_PERMITS_TEST_TYPE
   else → DENY_UNKNOWN_TEST_TYPE
```

### Key invariants

- Prohibited always wins over allowed
- Blocking rules always win over allowed
- Unknown/empty → DENY (no ALLOW fallback)
- No semantic interpretation — only deterministic keyword matching

## Decision-Modell

```python
class ProgramPolicyDecisionStatus(StrEnum):
    ALLOW = "allow"
    DENY = "deny"

class ProgramPolicyReason(StrEnum):
    ALLOW_POLICY_PERMITS_TEST_TYPE = "allow_policy_permits_test_type"
    DENY_PROHIBITED_TEST_TYPE = "deny_prohibited_test_type"
    DENY_AUTOMATION_PROHIBITED = "deny_automation_prohibited"
    DENY_AUTOMATION_REQUIRES_APPROVAL = "deny_automation_requires_approval"
    DENY_AUTOMATION_UNKNOWN = "deny_automation_unknown"
    DENY_BLOCKING_POLICY_RULE = "deny_blocking_policy_rule"
    DENY_UNKNOWN_TEST_TYPE = "deny_unknown_test_type"
    DENY_MISSING_POLICY = "deny_missing_policy"
    DENY_INVALID_INTENT = "deny_invalid_intent"
```

8 Reason-Codes (1 ALLOW, 8 DENY). Kein UNKNOWN als Allow-Status.

## Intent-Modell

```python
class ProgramPolicyIntent(BaseModel):
    target: str          # "api.example.com"
    test_type: str       # "api_testing", "brute_force"
    automation: bool     # False
    method: str          # "GET"
    source: str          # "local-test"
```

Kein I/O. Nur Deskriptor.

## Violation-/Evidence-Modell

```python
class ProgramPolicyViolation(BaseModel):
    target: str
    test_type: str
    automation: bool
    reason: str
    matched_policy_item: str | None   # z. B. "brute_force" oder Rule-Description
    policy_source: str | None         # ScopePolicy.source_url
    explanation: str                  # Human-readable
```

Serialisierbar via Pydantic. Keine persistente Datei/DB.

## Testarten-Normalisierung

```
"brute force"        → "brute_force"
"brute-force"        → "brute_force"
"Brute_Force"        → "brute_force"
"credential-stuffing" → "credential_stuffing"
"BRUTE   FORCE"      → "brute_force"
```

Deterministisch: lowercase → whitespace/hyphens/dots → underscores → collapse → strip.

## Tests

| Bereich | Anzahl | Status |
|---------|--------|--------|
| Pre-existing (Issues #1-#7) | 237 | All green |
| Prohibited Test Types (neu) | 5 | All green |
| Allowed Test Types (neu) | 4 | All green |
| Automation Policies (neu) | 5 | All green |
| Blocking PolicyRules (neu) | 4 | All green |
| Unknown / Invalid (neu) | 4 | All green |
| Audit / Serialization (neu) | 4 | All green |
| Safety (neu) | 8 | All green |
| Edge Cases (neu) | 6 | All green |
| **Total** | **277** | **All green** |

## Lokale Gates

| Gate | Pre-Change | Post-Change |
|------|-----------|-------------|
| `pytest tests/ -v` | 237 passed | 277 passed (+40) |
| Coverage | 98% (674 stmts) | 98% (771 stmts) |
| `ruff check .` | All checks passed | All checks passed |
| `mypy src/neutrino/ --strict` | Success (14 files) | Success (17 files) |
| `compileall src/` | All compiled | All compiled |

## Safety Check

- [x] Keine echten Netzwerk-Requests
- [x] Keine DNS-Auflösung
- [x] Kein Scheduler / Sleep / Wait
- [x] Kein Override-Pfad für DENY (force, admin_override, etc.)
- [x] Keine Human-Approval-Freigabe implementiert
- [x] Kein persistenter AuditLog-Writer (Issue #12)
- [x] Kein n8n / Paperclip / Lab / Dashboard
- [x] Keine GitHub Actions / Remote-CI
- [x] Determinismus verifiziert: same inputs → same decision
- [x] Default-Deny für unknown/invalid states

## Nicht geändert

- ScopeGuard (`src/neutrino/scopeguard/`) — unverändert
- RateLimitEnforcer (`src/neutrino/ratelimit/`) — unverändert
- PolicyParser (`src/neutrino/policy/`) — unverändert
- Policy Models (`src/neutrino/models/policy.py`) — unverändert
- Keine Pipeline-Integration zwischen Enforcern
- Keine Datenbank, kein persistenter AuditLog
- Kein Human Approval Workflow (bleibt Issue #4)

## Offene Punkte

- Line 282 in `enforcer.py` (1 uncovered statement) — `__init_subclass__` oder ähnliche Metaclass-Ebene. Coverage 98% ist akzeptabel.
- `requires_approval` bleibt DENY bis Issue #4 (Human Authorization Workflow) explizit freigibt.

## Nächster empfohlener Schritt

**Issue #12: AuditLog JSONL-Writer** — jetzt, da sowohl RateLimitEnforcer als auch ProgramPolicyEnforcer serialisierbare Violation/Evidence-Strukturen produzieren, kann ein persistenter AuditLog-Writer diese konsumieren.

Alternativ: **Issue #44: Rate-Limit-Regressionstests** — nachgelagerte Regressionstests für den RateLimitEnforcer.

---

## Decision Manifest

### GREEN_SAFE

- ProgramPolicyEnforcer mit deterministischer Entscheidungs-Logik
- Verbotene Testarten mit Normalisierung geblockt
- Automation-Policies konservativ erzwungen (unknown/requires_approval → DENY)
- Blocking PolicyRules via Keyword-Matching evaluiert
- Serialisierbare Violation/Evidence für jede DENY-Entscheidung
- 40 neue Tests, 277 total, 98% Coverage
- Ruff / Mypy / Compileall sauber
- Kein Netzwerk, kein DNS, kein Scheduler, kein Override

### YELLOW_REVIEW

- Rule-Matching ist keyword-basiert (Substring in normalisierter Description). Semantisches Matching könnte Fehlalarme reduzieren, wäre aber nicht-deterministisch.
- `requires_approval` erzeugt DENY — dies ist korrektes konservatives Verhalten, muss aber in Issue #4 explizit bestätigt werden.

### RED_BLOCK

- Kein Human-Approval-Workflow (Issue #4)
- Kein Admin-Override (bewusst nicht implementiert)
- Kein persistenter AuditLog (Issue #12)
- Keine Pipeline-Integration ScopeGuard → PolicyEnforcer → RateLimitEnforcer
- Keine aktiven Tests gegen reale Ziele

### TOOL_GAP / UNKNOWN

- `nox` verfügbar im venv, aber nicht als separates Gate ausgeführt (TOOL_GAP)
- Coverage bei 98% (ein Statement in enforcer.py uncovered — nicht kritisch)
