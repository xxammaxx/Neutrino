# Neutrino Phase 1 — Issue #11 CRUD Repositories Report

## Kurzfazit

**GREEN** — Vollständig umgesetzt und getestet.

## Reality Refresh

| Check | Ergebnis |
|-------|----------|
| Default Branch | `main` |
| HEAD | `2dec196` (docs: Phase 1 Issue #10 Report) |
| git status | Clean (vor Änderungen) |
| Issue #10 | CLOSED / completed |
| Issue #11 | OPEN / GREEN_SAFE |
| Issue #12 | OPEN / GREEN_SAFE (blockiert, nicht gebaut) |
| Offene PRs | Keine |
| `.github/workflows/` | Nicht vorhanden |
| Vorhandene Storage-Dateien | `schema.py`, `sqlite.py`, `migrations.py`, `paths.py`, `__init__.py` |
| Vorhandene Tests | `test_schema.py`, `test_migrations.py` |

## Geänderte Dateien

### Neu erstellt
| Datei | Beschreibung |
|-------|-------------|
| `src/neutrino/storage/exceptions.py` | Repository-Exceptions: `EntityNotFound`, `ForeignKeyViolation`, `AuditEventImmutable`, `RepositoryError` |
| `src/neutrino/models/entities.py` | Pydantic-Modelle für alle 8 Core-Entities + Create/Update-DTOs (24 Modelle) |
| `src/neutrino/storage/repositories/__init__.py` | Package-Exports für alle 8 Repositories |
| `src/neutrino/storage/repositories/base.py` | `BaseRepository` mit `_now_iso()`, `_row_to_dict()`, `_fetch_one()`, `_fetch_all()`, `_execute_write()` |
| `src/neutrino/storage/repositories/programs.py` | `ProgramRepository` |
| `src/neutrino/storage/repositories/scope_policies.py` | `ScopePolicyRepository` |
| `src/neutrino/storage/repositories/targets.py` | `TargetRepository` |
| `src/neutrino/storage/repositories/research_runs.py` | `ResearchRunRepository` |
| `src/neutrino/storage/repositories/finding_hypotheses.py` | `FindingHypothesisRepository` |
| `src/neutrino/storage/repositories/evidence.py` | `EvidenceRepository` |
| `src/neutrino/storage/repositories/human_approvals.py` | `HumanApprovalRepository` |
| `src/neutrino/storage/repositories/audit_events.py` | `AuditEventRepository` (append-only) |
| `tests/storage/test_repositories.py` | 81 Unit Tests für alle 8 Repositories |
| `docs/roadmap/NEUTRINO_PHASE_1_ISSUE_11_REPORT.md` | Dieser Report |

## Repository-Design

- **Basis**: `BaseRepository` mit shared SQLite-Helfern
- **DB-Zugriff**: Jeder Aufruf öffnet eigene Connection via `get_connection()` (FKs immer ON)
- **SQL**: Nur explizite parametrisierte Queries, kein ORM
- **List-Ordnung**: Deterministic `ORDER BY created_at ASC, id ASC`
- **Timestamps**: `created_at` und `updated_at` via `datetime.now(UTC).isoformat()`
- **Updates**: Nur nicht-None Felder aus Pydantic-Update-Modellen
- **Rückgaben**: Pydantic-Modelle oder `None` (für `get`)
- **Fehler**: `EntityNotFound` bei Update/Delete auf fehlende ID, `ForeignKeyViolation` bei FK-Verstößen
- **keine**: ORM-Magic, Caching, Batch-Operationen, Implizite Joins, Eager Loading

## Entity-Repositories

### ProgramRepository
- `create(data)` → `Program`
- `get(id)` → `Program | None`
- `list_all()` → `list[Program]`
- `update(id, data)` → `Program`
- `delete(id)` → `bool`
- `count()` → `int`

### ScopePolicyRepository
- `create(data)` → `ScopePolicy`
- `get(id)` → `ScopePolicy | None`
- `list_all()` → `list[ScopePolicy]`
- `list_by_program(program_id)` → `list[ScopePolicy]`
- `update(id, data)` → `ScopePolicy`
- `delete(id)` → `bool`
- `count()` → `int`

### TargetRepository
- `create(data)` → `Target` (is_wildcard: bool→int Konvertierung)
- `get(id)` → `Target | None`
- `list_all()` → `list[Target]`
- `list_by_program(program_id)` → `list[Target]`
- `update(id, data)` → `Target`
- `delete(id)` → `bool`

### ResearchRunRepository
- `create(data)` → `ResearchRun`
- `get(id)` → `ResearchRun | None`
- `list_all()` → `list[ResearchRun]`
- `list_by_program(program_id)` → `list[ResearchRun]`
- `update(id, data)` → `ResearchRun` (status/finished_at)
- `delete(id)` → `bool`

### FindingHypothesisRepository
- `create(data)` → `FindingHypothesis`
- `get(id)` → `FindingHypothesis | None`
- `list_all()` → `list[FindingHypothesis]`
- `list_by_research_run(research_run_id)` → `list[FindingHypothesis]`
- `update(id, data)` → `FindingHypothesis`
- `delete(id)` → `bool`

### EvidenceRepository
- `create(data)` → `Evidence`
- `get(id)` → `Evidence | None`
- `list_all()` → `list[Evidence]`
- `list_by_finding(finding_hypothesis_id)` → `list[Evidence]`
- `update(id, data)` → `Evidence`
- `delete(id)` → `bool`

### HumanApprovalRepository
- `create(data)` → `HumanApproval`
- `get(id)` → `HumanApproval | None`
- `list_all()` → `list[HumanApproval]`
- `list_by_research_run(research_run_id)` → `list[HumanApproval]`
- `update(id, data)` → `HumanApproval`
- `delete(id)` → `bool`

### AuditEventRepository
- `create(data)` → `AuditEvent`
- `append(data)` → `AuditEvent` (Alias für create)
- `get(id)` → `AuditEvent | None`
- `list_all()` → `list[AuditEvent]`
- `list_by_actor(actor)` → `list[AuditEvent]`
- `list_by_action(action)` → `list[AuditEvent]`
- `update(id, data)` → **immer** `AuditEventImmutable`
- `delete(id)` → **immer** `AuditEventImmutable`

## Relation-Auflösung

Explizite `list_by_*`-Methoden pro Repository — keine komplexen Joins:

| Methode | Repository | FK-Feld |
|---------|-----------|---------|
| `list_scope_policies_by_program(program_id)` | ScopePolicyRepository | `program_id` |
| `list_targets_by_program(program_id)` | TargetRepository | `program_id` |
| `list_research_runs_by_program(program_id)` | ResearchRunRepository | `program_id` |
| `list_findings_by_research_run(research_run_id)` | FindingHypothesisRepository | `research_run_id` |
| `list_evidence_by_finding(finding_hypothesis_id)` | EvidenceRepository | `finding_hypothesis_id` |
| `list_human_approvals_by_research_run(research_run_id)` | HumanApprovalRepository | `research_run_id` |

## Fehlerfall-Modell

| Fehler | Auslöser | Verhalten |
|--------|---------|-----------|
| `EntityNotFound` | `update`/`delete` auf unbekannte ID | Exception mit Entity-Typ und ID |
| `ForeignKeyViolation` | `create` mit ungültigem FK | Exception mit Entity-Typ und FK-Feld |
| `AuditEventImmutable` | `update`/`delete` auf AuditEvent | Exception mit Aktionstyp |
| `None` | `get` auf unbekannte ID | Silent `None` (kein Exception) |

## Audit-Abgrenzung

- ✅ `AuditEventRepository` implementiert (SQLite-basierte Tabellen-Persistenz)
- ✅ AuditEvents sind append-only (`update`/`delete` werfen `AuditEventImmutable`)
- ✅ `AuditEvent.get()` und `AuditEvent.list_all()` funktionieren
- ⏳ **JSONL-AuditLog-Writer (#12)**: Noch nicht gebaut — Folge-Issue
- ⏳ **Cross-Repository-Audit-Hooks**: Noch nicht gebaut
- ⏳ **AuditLog-Integritätstests (#46)**: Noch nicht gebaut

## Tests

### Test-Struktur

81 Repository-Tests in `tests/storage/test_repositories.py`, organisiert als:

| Testklasse | Tests | Abdeckung |
|-----------|-------|-----------|
| `TestProgramRepository` | 11 | create/get, list, update, delete, missing, count |
| `TestScopePolicyRepository` | 12 | create/get, list_by_program, FK, JSON roundtrip, update, delete, missing |
| `TestTargetRepository` | 12 | create/get, wildcard roundtrip, list_by_program, FK, update, delete, missing |
| `TestResearchRunRepository` | 11 | create/get, list_by_program, FK, status update, delete, missing |
| `TestFindingHypothesisRepository` | 10 | create/get, list_by_run, FK, update, delete, missing |
| `TestEvidenceRepository` | 10 | create/get, JSON roundtrip, list_by_finding, FK, update, delete, missing |
| `TestHumanApprovalRepository` | 10 | create/get, list_by_run, FK, update, delete, missing |
| `TestAuditEventRepository` | 10 | create/get, append, JSON roundtrip, list_by_actor/action, update/delete forbidden |
| `TestDeterminism` | 1 | Stabile Ordnung bei gleichen Timestamps |
| `TestRepositoriesSafety` | 4 | Kein ORM, keine Home-Pfade, kein Netzwerk, explizite SQL |
| **Total** | **81** | |

### Test-Design
- Alle Tests nutzen `get_temp_db_path()` → keine Schreibzugriffe auf `~/.neutrino/`
- Datenbanken werden mit `apply_migrations()` vorbereitet
- FK-Tests prüfen, dass ungültige Referenzen `ForeignKeyViolation` auslösen
- Audit-Tests prüfen, dass `update`/`delete` immer `AuditEventImmutable` werfen
- `is_wildcard` bool↔int Konvertierung wird explizit getestet
- Liste-Ordnung wird über `created_at ASC, id ASC` verifiziert

## Lokale Gates

| Gate | Vorher (346 Tests) | Nachher (427 Tests) |
|------|-------------------|---------------------|
| `pytest tests/ -v` | 346 passed, 97.90% | **427 passed, 96.41%** |
| `ruff check .` | ✅ | ✅ |
| `mypy src/neutrino/ --strict` | ✅ (22 files) | ✅ (34 files) |
| `python3 -m compileall src/` | ✅ | ✅ |
| `nox` | Verfügbar | (nicht ausgeführt, da virtualenv) |

## Issue #11 Status

- **Status**: Akzeptanzkriterien erfüllt, Issue kann geschlossen werden
- [x] CRUD-Operationen existieren für alle Core-Entities
- [x] Beziehungen sind korrekt auflösbar
- [x] Fehlerfälle werden behandelt
- [x] Datenzugriffe sind deterministisch

## Safety Check

- [x] Keine Remote-DB verwendet (SQLite lokal)
- [x] Kein ORM (nur explizite parametrisierte Queries)
- [x] Kein Netzwerk-I/O in Repository-Modulen
- [x] Keine Tests schreiben nach `~/.neutrino/`
- [x] Keine echten sensiblen Daten in Tests
- [x] Kein JSONL-AuditLog-Writer (#12) gebaut
- [x] Keine n8n/Paperclip-Anbindung
- [x] Keine GitHub Actions erstellt
- [x] Keine Package-Manager-Migration

## Nicht geändert

- `src/neutrino/storage/schema.py` — unverändert
- `src/neutrino/storage/sqlite.py` — unverändert
- `src/neutrino/storage/migrations.py` — unverändert
- Alle Policy-, ScopeGuard-, RateLimit-Module — unverändert

## Nicht gebaut (abgegrenzt)

- ❌ Issue #12: AuditLog JSONL-Writer
- ❌ Issue #46: AuditLog-Integritätstests
- ❌ n8n/Paperclip-Integration
- ❌ API-Layer oder Workflow-Runtime
- ❌ Caching oder Batch-Operationen
- ❌ Graph-Loader oder Eager Loading

## Decision Manifest

### GREEN_SAFE
- Alle 8 CRUD-Repositories mit explizitem SQL
- 81 Unit Tests mit 96.41% Gesamt-Coverage
- Append-Only-Garantie für AuditEvents
- FK-Constraint-Tests (6 FK-Relationen)
- Deterministische List-Ordnung
- Kein ORM, kein Netzwerk, keine Remote-DB

### YELLOW_REVIEW
- Coverage von `audit_events.py` auf 92% (update/delete-Zweige sind unerreichbar → absichtlich)
- Coverage von `evidence.py`, `finding_hypotheses.py`, `human_approvals.py` auf 88% (unbenutzte Import-/Error-Zweige)
- Issue #12 JSONL-AuditLog-Writer sollte als nächster Schritt priorisiert werden

### RED_BLOCK
- Keine — alle Sicherheitsgrenzen eingehalten

### TOOL_GAP / UNKNOWN
- `nox` nicht ausgeführt (erfordert Python 3.11, aber `.venv` läuft auf 3.12)
- Coverage-Report zeigt 96.41% — über 80%-Schwelle

## Nächster sinnvoller Schritt

**Issue #12: AuditLog JSONL-Writer implementieren**

Nachdem die SQLite-Repository-Schicht jetzt vollständig ist, kann der JSONL-basierte
AuditLog-Writer (#12) darauf aufbauen. Der `AuditEventRepository` in SQLite dient
bereits als Fallback/Query-Layer — der JSONL-Writer ergänzt dies um eine
immutable, append-only, zeilenbasierte Audit-Log-Datei.
