# Neutrino Phase 2 — Issue #13 BudgetPolicy Status Logic Report

## Kurzfazit

**GREEN** — Vollständig umgesetzt. Alle Akzeptanzkriterien erfüllt, alle lokalen Gates grün, 47 neue Budget-Tests (587 gesamt), keine Sicherheitsverletzung.

## Reality Refresh

| Item | Status |
|------|--------|
| Default Branch | `main` |
| HEAD Commit (vorher) | `bfdfdf9` |
| Working Tree | Clean |
| Issue #46 (AuditLog Integrity Tests) | CLOSED (in diesem Lauf synchronisiert) |
| Issue #11 (CRUD Repositories) | CLOSED |
| Issue #13 (BudgetPolicy Statuslogik) | OPEN → jetzt IMPLEMENTIERT |
| Open PRs | Keine |
| `.github/workflows/` | Nicht vorhanden (by design) |
| Budget-Code vorher | Keiner |

## Issue #46 Sync

- Issue #46 war OPEN mit allen Akzeptanzkriterien `[x]`
- `tests/audit/test_integrity.py` vorhanden (48 Tests)
- Report `NEUTRINO_PHASE_1_ISSUE_46_REPORT.md` vorhanden
- 540 Tests vorher alle grün
- → Mit `reason=completed` geschlossen, Sync-Kommentar gepostet

## Geänderte Dateien

| Datei | Typ | Änderung |
|-------|-----|----------|
| `src/neutrino/budget/__init__.py` | Neu — Modul | Public API exports |
| `src/neutrino/budget/models.py` | Neu — Modelle | BudgetStatus, BudgetPolicy, BudgetUsage, BudgetDecision |
| `src/neutrino/budget/policy.py` | Neu — Kernlogik | `evaluate_budget()` pure function |
| `src/neutrino/budget/status.py` | Neu — Persistenz | `apply_budget_decision()` Repository-Integration |
| `tests/budget/__init__.py` | Neu — Test Package | Leer |
| `tests/budget/test_budget_policy.py` | Neu — Tests | 47 Tests in 6 Testklassen |
| `docs/roadmap/NEUTRINO_PHASE_2_ISSUE_13_REPORT.md` | Neu — Report | Dieser Report |

**Keine Änderungen an bestehenden Produktdateien.** Das Budget-Modul ist ein neues, isoliertes Package.

## Budget-Modell

### BudgetStatus (StrEnum)
- `OK` — innerhalb aller Limits
- `WARNING` — reserviert für zukünftige Schwellwert-Warnungen
- `EXHAUSTED` — mindestens ein Limit erreicht oder überschritten
- `ERROR` — ungültige Eingabe oder fehlende Konfiguration

### BudgetPolicy
- `max_requests: int | None`
- `max_cost_cents: int | None`
- `max_runtime_seconds: int | None`
- `has_any_limit() -> bool`

### BudgetUsage
- `requests_used: int = 0`
- `cost_cents_used: int = 0`
- `runtime_seconds_used: int = 0`
- `is_valid() -> bool`

### BudgetDecision
- `status: BudgetStatus`
- `reason: str`
- `limit_name: str | None`
- `limit_value: int | None`
- `observed_value: int | None`
- `timestamp: str` (ISO 8601, injizierbar)

## EXHAUSTED-Logik

Prüfreihenfolge (deterministisch):
1. Negative Usage-Werte → `ERROR`
2. Negative Limits → `ERROR`
3. Keine Limits gesetzt → `ERROR` (`missing_budget_limits`)
4. `requests_used >= max_requests` → `EXHAUSTED`
5. `cost_cents_used >= max_cost_cents` → `EXHAUSTED`
6. `runtime_seconds_used >= max_runtime_seconds` → `EXHAUSTED`
7. Alles OK → `OK`

Erstes erschöpftes Limit gewinnt. `None`-Limits werden übersprungen.

## Statuswechsel-Speicherung

### `apply_budget_decision()`
- `EXHAUSTED` oder `ERROR` → ResearchRun-Status wird via `ResearchRunRepository.update()` auf `"exhausted"`/`"error"` gesetzt
- `OK` → kein Status-Update (Run läuft weiter)
- Jeder Decision wird via `AuditEventRepository.append()` als AuditEvent protokolliert
- Beide Repositories optional: funktioniert auch ohne eine oder beide
- Fehler bei nicht-existentem Run werden still behandelt (kein Crash)

### Immutability
- `EXHAUSTED` ist endgültig — kein automatisches Reset
- OK-Decision nach EXHAUSTED-Decision überschreibt den Run-Status NICHT

## Reproduzierbarkeit

- `evaluate_budget(policy, usage, timestamp)` — pure function
- Timestamp injizierbar → Tests mit fixem Timestamp
- Gleiche Inputs + gleicher Timestamp → identische Decision (assert d1 == d2)
- Keine `datetime.now()` im Kern der Evaluation

## Fehlerzustände

| Fehler | Status | Reason |
|--------|--------|--------|
| policy is None | ValueError | "policy must not be None" |
| Negative Usage | ERROR | "Negative usage values are not allowed" |
| Negative Limits | ERROR | "Negative budget limits are not allowed" |
| No limits configured | ERROR | "No budget limits configured (missing_budget_limits)" |

Alle ERROR-Entscheidungen werden als AuditEvent protokolliert.

## Tests

### Teststruktur (6 Klassen, 47 Tests)

| # | Klasse | Tests | Fokus |
|---|--------|-------|-------|
| 1 | `TestExhaustedDetection` | 13 | OK/EXHAUSTED für Requests, Cost, Runtime, Priority |
| 2 | `TestErrorHandling` | 10 | None policy, missing limits, negative values |
| 3 | `TestReproducibility` | 4 | Gleiche Inputs, Timestamp-Injection, Priority-Order |
| 4 | `TestStatusChangePersistence` | 9 | Run-Status-Update, Audit-Event, No-Auto-Recovery, Optional-Repos |
| 5 | `TestSafetyChecks` | 7 | Keine Netzwerk-Imports, kein Auto-Recovery, keine Cloud-Billing, keine DNS |
| 6 | `TestBudgetModels` | 6 | has_any_limit, is_valid, JSON-Serialisierbarkeit, Enum-Values |

### Abgedeckte Acceptance Criteria

- [x] BudgetStatus erkennt EXHAUSTED korrekt (Tests 1–13)
- [x] Statuswechsel werden gespeichert (Tests 4.1–4.9)
- [x] Budgetprüfungen sind reproduzierbar (Tests 3.1–3.4)
- [x] Fehlerzustände werden protokolliert (Tests 2.1–2.10, 4.3–4.4)

## Lokale Gates

| Gate | Vorher | Nachher |
|------|--------|---------|
| `pytest tests/ -v` | 540 passed | **587 passed** (+47) |
| Coverage | 96.63% | **96.89%** (+0.26%) |
| `compileall src/` | OK | OK |
| `ruff check .` | All checks passed | All checks passed |
| `mypy src/neutrino/ --strict` | Success: 37 files | Success: **41 files** |

## Safety Check

- [x] Keine Echtgeld-Integration
- [x] Kein Cloud-Kosten-Tracking
- [x] Keine automatische Budget-Verlängerung
- [x] Kein implizites Auto-Recovery
- [x] EXHAUSTED wird nicht automatisch zurückgesetzt
- [x] Keine n8n-Integration
- [x] Keine Paperclip-Integration
- [x] Kein API-Layer
- [x] Kein Dashboard
- [x] Keine echten Requests
- [x] Keine DNS-Auflösung
- [x] Keine Scanner
- [x] Keine GitHub Actions erstellt
- [x] Keine Remote-CI konfiguriert
- [x] Keine Package-Manager-Migration
- [x] Alle Tests lokal und deterministisch (temp SQLite)
- [x] `evaluate_budget()` ist pure function — keine Side Effects

## Nicht geändert

- Keine bestehenden Modelle geändert (`entities.py` unverändert)
- Keine bestehenden Repositories geändert
- Keine bestehenden Tests geändert
- Keine neuen Dependencies
- Keine n8n/Paperclip/API/Dashboard-Integration

## Offene Punkte

| # | Punkt | Status |
|---|-------|--------|
| — | Keine offenen Punkte für Issue #13 | — |

## Decision Manifest

### GREEN_SAFE

- Alle 47 neuen Budget-Tests bestanden
- EXHAUSTED-Erkennung deterministisch und mit fixer Priority-Order
- Statuswechsel via ResearchRunRepository + AuditEventRepository persistiert
- EXHAUSTED bleibt endgültig, kein Auto-Recovery
- Budget-Modell ist minimal, serialisierbar, ohne Echtgeld-Integration
- Alle lokalen Gates grün

### YELLOW_REVIEW

- Keine.

### RED_BLOCK

- Keine — alle bewussten Nicht-Ziele respektiert:
  - Kein Auto-Recovery, kein Reset
  - Keine Echtgeld-/Cloud-Integration
  - Keine n8n/Paperclip/API/Dashboard

### TOOL_GAP / UNKNOWN

- `nox` ist verfügbar (`2026.4.10`), wurde aber nicht als separater Lauf ausgeführt, da `pytest`, `ruff`, und `mypy` direkt die gleichen Checks abdecken.

## Nächster empfohlener Schritt

Issue #13 (BudgetPolicy Statuslogik) ist abgeschlossen. Empfohlene nächste Schritte in Phase 2:

1. **Issue #14** oder nächstes Storage-Issue — Evidenz-Tracking oder ResearchRun-Workflow
2. **Human/Admin Reset-Workflow** — separates Folgeissue für kontrollierte Budget-Reset-Funktion
3. **WARNING-Status** — Schwellwert-basierte Warnungen, wenn Limits zu >80% erreicht sind
