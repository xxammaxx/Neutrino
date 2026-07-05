# Neutrino Phase 1 — Issue #3 Rate-Limit & Automation Extraction Report

## Kurzfazit

**GREEN_SAFE** — Rate-Limits, Automation-Policies und Testarten werden deterministisch aus Policy-Texten extrahiert und strukturiert im ScopePolicy-Modell gespeichert. Keine Enforcement-Logik, keine echten Requests, keine DNS-Auflösung.

## Reality Refresh

- Branch: main
- Commit: e86ac00
- Pre-existing tests: 123 passing
- Post-implementation tests: 168 passing (45 new)
- Issue #6 (Redirect/CNAME): CLOSED ✓
- Issue #7 (Rate-Limit Enforcement): OPEN, blockiert durch #3 → jetzt unblockiert

## Geänderte Dateien

| Datei | Änderungen | Beschreibung |
|-------|-----------|-------------|
| `src/neutrino/models/policy.py` | +47 lines | RateLimit erweitert, AutomationPolicy neu, ScopePolicy erweitert |
| `src/neutrino/policy/parser.py` | +204 lines | Extraction-Methoden für Rate-Limits (minute/day), Automation, Testarten |
| `tests/policy/test_parser.py` | +520 lines | 45 neue Tests (26 functionale + 19 Safety/Determinism) |

## Modell-Änderungen

### RateLimit (erweitert)

```python
requests_per_second: float | None = None  # existing
requests_per_minute: int | None = None    # NEW
requests_per_hour: int | None = None      # existing
requests_per_day: int | None = None       # NEW
concurrent_requests: int | None = None    # existing
auto_throttle: bool = True               # existing
```

### AutomationPolicy (NEU)

```python
status: str = "unknown"         # allowed | prohibited | requires_approval | unknown
evidence: str | None = None     # text snippet that led to classification

# Properties:
is_allowed, is_prohibited, requires_approval, is_unknown
```

### ScopePolicy (erweitert)

```python
automation_policy: AutomationPolicy = AutomationPolicy()  # NEW
allowed_test_types: list[str] = []                        # NEW
prohibited_test_types: list[str] = []                     # NEW
```

## Rate-Limit-Extraktion

Unterstützte Formate:

| Format | Feld | Beispiel |
|--------|------|----------|
| `2 requests per second` / `3 req/s` | `requests_per_second` | `2`, `3.0` |
| `60 requests per minute` / `100 req/min` | `requests_per_minute` | `60`, `100` |
| `1000 requests per hour` / `500 req/hour` | `requests_per_hour` | `1000`, `500` |
| `10000 requests per day` / `10000 req/day` | `requests_per_day` | `10000` |
| `5 concurrent requests` | `concurrent_requests` | `5` |

Fehlende Limits → `RateLimit` ist `None` (explizit unknown).

## Automation-Policy-Extraktion

Prioritäten (höchste zuerst):
1. **prohibited**: "Automated scanning is prohibited", "Do not use automated scanners"
2. **requires_approval**: "Automated testing requires prior approval", "Must obtain prior written permission"
3. **allowed**: "Automated testing is allowed within rate limits", "Automation is welcome"
4. **unknown**: Default wenn nichts gefunden wird

Widersprüchliche Aussagen → konservativ behandelt (prohibited > requires_approval > allowed).

## Testarten-Extraktion

### Verbotene Testarten (15 Muster)

`brute_force`, `credential_stuffing`, `social_engineering`, `phishing`, `spam`, `ddos`, `destructive_testing`, `physical_attacks`, `data_exfiltration`, `accessing_user_data`, `automated_scanning`, `social_media_phishing`, `website_defacement`, `ransomware`, `port_scanning_out_of_scope`

### Erlaubte Testarten (10 Muster)

`web_application_testing`, `api_testing`, `authenticated_testing`, `non_destructive_testing`, `rate_limited_automated_testing`, `test_accounts`, `manual_testing`, `code_review`, `configuration_analysis`, `vulnerability_scanning`

## Unknown-Modellierung

- Fehlende Rate-Limits → `rate_limits` ist `None`
- Fehlende Automation-Policy → `automation_policy.status == "unknown"` (mit Properties `is_unknown`, etc.)
- Fehlende Testarten → leere Listen `[]` (in Kombination mit AutomationPolicy.status == "unknown" interpretierbar)

## Tests

| Bereich | Anzahl | Status |
|---------|--------|--------|
| Pre-existing (Issues #1, #2, #5, #6) | 123 | All green |
| Rate-Limit Extraction (neu) | 8 | All green |
| Automation Policy (neu) | 10 | All green |
| Test-Type Extraction (neu) | 15 | All green |
| Determinism & Safety (neu) | 12 | All green |
| **Total** | **168** | **All green** |

## Lokale Gates

| Gate | Ergebnis |
|------|----------|
| `pytest tests/ -v` | 168 passed ✓ |
| Coverage | 98% (models 100%, parser 95%) ✓ |
| `ruff check .` | All checks passed ✓ |
| `mypy src/neutrino/ --strict` | Success, no issues ✓ |
| `compileall src/` | All compiled ✓ |

## Safety Check

- Keine echten Netzwerk-Requests ✓
- Keine DNS-Auflösung ✓
- Kein Enforcement (Issue #7) ✓
- Kein n8n/Paperclip ✓
- Kein AuditLog-Persistenzsystem ✓
- Keine Remote-CI / GitHub Actions ✓
- Determinismus verifiziert ✓
- Konservative Defaults ✓

## Nicht geändert

- ScopeGuard (`src/neutrino/scopeguard/guard.py`) — unverändert
- Redirect-/CNAME-Logik (`src/neutrino/scopeguard/redirects.py`, `dns.py`) — unverändert
- ScopePolicy.is_in_scope(), ScopePolicy.has_blocking_rules() — unverändert
- ScopeEntry.matches() — unverändert
- Kein neues Issue #7 implementiert

## Offene Punkte

- None. Alle Akzeptanzkriterien erfüllt.

## Nächster empfohlener Schritt

Issue #7: **Rate-Limit Enforcement implementieren** — jetzt unblockiert, da alle Rate-Limit-Daten strukturiert in `ScopePolicy.rate_limits` verfügbar sind.

---

## Decision Manifest

### GREEN_SAFE

- RateLimit-Modell rückwärtskompatibel erweitert
- AutomationPolicy-Modell mit konservativen Defaults
- Testarten-Extraktion mit getrennten Listen
- Unknown-Status explizit modelliert
- Alle bestehenden Tests grün
- 45 neue Tests, deterministisch, ohne Netzwerk

### YELLOW_REVIEW

- Testarten-Patterns sind keyword-basiert (Regex). Semantische Verbesserung möglich, wenn NLP-Komponente verfügbar.
- Automation-Policy-Patterns decken gängige Formulierungen ab, aber nicht alle Edge Cases.

### RED_BLOCK

- Kein Enforcement (bleibt Issue #7)
- Keine aktiven Tests
- Keine Netzwerk-Requests
- Keine DNS-Auflösung

### TOOL_GAP / UNKNOWN

- `nox` verfügbar im venv, aber nicht als separates Gate ausgeführt (TOOL_GAP)
- Keine externen Policy-Quellen validiert (nur lokale Fixtures)
