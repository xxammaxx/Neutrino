# Neutrino Phase 1 — Issue #7 Rate-Limit Enforcement Report

## Kurzfazit

**GREEN_SAFE** — Rate-Limit Enforcement ist vollständig implementiert. Der RateLimitEnforcer evaluiert Request-Intents deterministisch, lokal und ohne Netzwerk-I/O. Alle 4 Akzeptanzkriterien sind erfüllt. Keine echten Requests, keine DNS-Auflösung, kein Scheduler, kein Sleep, kein persistenter AuditLog.

## Reality Refresh

- Branch: main
- Pre-Change Commit: `6ca66d7` (docs: #3 Report)
- Post-Change Commit: `a58600b` (feat: #7)
- Pre-existing tests: 168 passing
- Post-implementation tests: 237 passing (69 new)
- Issue #3 (Rate-Limit Extraction): ✅ Closed (Phase A Mini-Sync)
- Issue #6 (Redirect/CNAME): ✅ CLOSED
- Issue #7 (Rate-Limit Enforcement): ✅ Implementiert

## Issue #3 Sync

Issue #3 war auf GitHub OPEN, hatte aber vollständige Completion-Evidence:
- Alle 4 ACs erfüllt (Completion-Comment mit ✅)
- 168 Tests passing, 98% Coverage
- Report `NEUTRINO_PHASE_1_ISSUE_3_REPORT.md` vorhanden
- Gates: ruff ✅, mypy ✅, compileall ✅

→ Mini-Sync: Abschlusskommentar gepostet, Issue #3 geschlossen mit `reason=completed`.

## Geänderte Dateien

| Datei | Zeilen | Beschreibung |
|-------|--------|-------------|
| `src/neutrino/ratelimit/__init__.py` | 27 | Package-Exporte |
| `src/neutrino/ratelimit/models.py` | 217 | Decision-, Violation-, Request-, State-Modelle |
| `src/neutrino/ratelimit/enforcer.py` | 375 | RateLimitEnforcer mit check_request() |
| `tests/ratelimit/__init__.py` | 0 | Package Marker |
| `tests/ratelimit/test_enforcer.py` | 1265 | 69 Unit Tests (alle Bereiche) |

## Rate-Limit-Enforcement-Design

### Architektur

```text
RateLimitRequest + ScopePolicy + RateLimitState
         →  RateLimitEnforcer.check_request()
         →  RateLimitDecision (ALLOW | DENY + optional violation)
```

- **Keine echten Requests** — nur deskriptive Intent-Decisions
- **Kein Sleep** — `retry_after_seconds` wird berechnet, nicht darauf gewartet
- **Kein Scheduler** — keine Hintergrundprozesse
- **Kein persistenter AuditLog** — Violation-Modelle sind serialisierbar, aber schreiben nicht (Issue #12)

### Check-Reihenfolge

1. Policy missing → DENY_MISSING_POLICY
2. RateLimits missing → DENY_MISSING_RATE_LIMIT
3. Target ungültig → DENY_INVALID_TARGET
4. Concurrent limit check
5. Per-second limit check
6. Per-minute limit check
7. Per-hour limit check
8. Per-day limit check
9. Alle bestanden → ALLOW

## Decision-Modell

### RateLimitDecisionStatus
- `ALLOW` / `DENY` (kein UNKNOWN)

### RateLimitReason
- `ALLOW_WITHIN_LIMIT`
- `DENY_MISSING_POLICY`, `DENY_MISSING_RATE_LIMIT`, `DENY_INVALID_TARGET`
- `DENY_REQUESTS_PER_SECOND_EXCEEDED`
- `DENY_REQUESTS_PER_MINUTE_EXCEEDED`
- `DENY_REQUESTS_PER_HOUR_EXCEEDED`
- `DENY_REQUESTS_PER_DAY_EXCEEDED`
- `DENY_CONCURRENT_REQUESTS_EXCEEDED`

### RateLimitDecision
```python
target: str, status: RateLimitDecisionStatus, reason: RateLimitReason,
retry_after_seconds: float | None, explanation: str,
policy_source: str | None, violation: RateLimitViolation | None
```

## State-/History-Modell

### RateLimitState
- `requests: list[RateLimitRequest]` — alle Requests (Zeitfenster-Zählung)
- `_active_ids: set[str]` — nur aktive/in-flight Requests (Concurrency-Zählung)

Methoden:
- `add_request(request)` — fügt Request als aktiv hinzu
- `complete_request(request_id)` — markiert Request als abgeschlossen (freed Concurrent-Slot, zählt weiter für Zeitfenster)
- `active_count(target)` — zählt nur aktive Requests
- `count_in_window(target, window, now)` — zählt alle Requests im Fenster
- `prune_before(cutoff)` — löscht alte abgeschlossene Requests (aktive nie)

## Audit-/Violation-Modell

```python
RateLimitViolation(
    target: str,
    reason: str,
    limit_name: str,          # z.B. "requests_per_second"
    limit_value: int | float, # z.B. 2.0
    observed_value: int | float,  # z.B. 3
    window_seconds: int | float,  # z.B. 1.0 (0 für concurrent)
    timestamp: float,
)
```

Jede DENY-Entscheidung aufgrund eines Limit-Exceed trägt ein Violation-Objekt. Strukturelle Denys (Missing Policy, Missing RateLimits, Invalid Target) haben `violation=None`. Violations sind via Pydantic serialisierbar (JSON), werden aber nicht persistent gespeichert (Issue #12).

## Normalisierung

Ziel-Normalisierung:
- Whitespace-Stripping, Lowercase
- Schema-Entfernung (`https://` → ``)
- Pfad-/Query-/Fragment-Entfernung (Host-only)
- Trailing-Dot-Entfernung (FQDN)

Damit: `HTTPS://API.Example.COM/v1/status` → `api.example.com`

## Tests

| Bereich | Anzahl | Status |
|---------|--------|--------|
| Pre-existing (Issues #1-#6) | 168 | All green |
| Missing Policy | 4 | All green |
| Missing Rate Limits | 2 | All green |
| Invalid Target | 4 | All green |
| Allow Within Limits | 5 | All green |
| Exceed Per Second | 4 | All green |
| Exceed Per Minute | 2 | All green |
| Exceed Per Hour | 2 | All green |
| Exceed Per Day | 2 | All green |
| Exceed Concurrent | 3 | All green |
| Per-Target Isolation | 4 | All green |
| Retry-After | 3 | All green |
| Violation Evidence | 7 | All green |
| Partial / Auto-Throttle / Conservatism | 5 | All green |
| Safety Gates | 5 | All green |
| Determinism | 1 | All green |
| State Management | 6 | All green |
| Request Model | 4 | All green |
| Reason Codes | 3 | All green |
| No Sleep | 2 | All green |
| Policy Source | 2 | All green |
| **Total** | **237** | **All green** |

## Lokale Gates

| Gate | Ergebnis |
|------|----------|
| `pytest tests/ -v` | 237 passed ✅ |
| Coverage | 98% (ratelimit enforcer 100%) ✅ |
| `ruff check .` | All checks passed ✅ |
| `mypy src/neutrino/ --strict` | Success, 14 source files ✅ |
| `compileall src/` | All compiled ✅ |

## Safety Check

- [x] Keine echten Netzwerk-Requests
- [x] Keine DNS-Auflösung
- [x] Kein Sleep / Scheduler
- [x] Kein Override-Pfad (force, admin_override, allow_missing_limits, auto_raise_limit)
- [x] Kein persistenter AuditLog (Issue #12)
- [x] Keine n8n / Paperclip / Dashboard-Integration
- [x] Keine GitHub Actions / Remote-CI
- [x] `auto_throttle=False` umgeht kein DENY
- [x] Determinismus: gleiche Inputs + State → gleiche Decision
- [x] Fehlende Limits → konservativ DENY
- [x] Concurrent nicht durch Zeitfenster-Zählung umgehbar

## Issue #7 Status

Die Akzeptanzkriterien sind erfüllt:

- [x] Request-Limits sind pro Ziel anwendbar
- [x] Überschreitungen werden blockiert
- [x] Verstöße werden auditiert (serialisierbare Violation-Struktur)
- [x] Fehlende Limits werden konservativ behandelt

## Nicht geändert

- ScopeGuard (`src/neutrino/scopeguard/`) — unverändert
- Policy Parser (`src/neutrino/policy/`) — unverändert
- Policy Models (`src/neutrino/models/policy.py`) — unverändert
- Das RateLimit-Modell von Issue #3 wird verwendet, nicht modifiziert
- Kein AuditLog Persistenzsystem (Issue #12)
- Keine Datenbank
- Kein n8n / Paperclip / RAG / Lab / Dashboard
- Kein Scheduler / Worker / Queue
- Kein Scan-Tooling

## Offene Punkte

- None. Alle Akzeptanzkriterien erfüllt.

## Nächster empfohlener Schritt

Issue #15: **Programmspezifische Verbote erzwingen** — Automation-Modelle und Test-Arten-Verbote aus Issue #3 sind jetzt mit Rate-Limit-Daten kombinierbar.

---

## Decision Manifest

### GREEN_SAFE

- RateLimitEnforcer deterministisch, lokal, ohne I/O
- Alle 4 Akzeptanzkriterien erfüllt
- 237 Tests (69 neu), 98% Coverage
- Alle Gates grün (ruff, mypy, compileall, pytest)
- Keine Sicherheitsverletzungen
- Konservative Defaults (missing → DENY)
- Pydantic-Modelle vollständig serialisierbar

### YELLOW_REVIEW

- `complete_request()` muss vom Aufrufer explizit gemanagt werden — bei Integration mit n8n (Phase 3) muss der Workflow dies sicherstellen
- Normalisierung ist Host-only — für zukünftige per-Endpoint-Limits müsste sie angepasst werden
- Keine Quota-Reservierung / Prioritization (nicht im Scope von #7)

### RED_BLOCK

- Keine echten Requests (Policy)
- Keine DNS-Auflösung (Policy)
- Kein Scheduler / Sleep (Policy)
- Kein AuditLog-Persistenz (Issue #12)
- Keine Umgehungslogik (force, bypass, admin_override)
- Keine automatische Limit-Erhöhung

### TOOL_GAP / UNKNOWN

- `nox` nicht im venv ausgeführt (TOOL_GAP, wie in vorherigen Reports dokumentiert)
- Keine Integrationstests mit realen Programmpolicies (nur lokale Fixtures)
