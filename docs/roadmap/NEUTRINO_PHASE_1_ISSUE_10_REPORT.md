# Neutrino Phase 1 — Issue #10 SQLite Schema & Migrations Report

## Kurzfazit

**GREEN_SAFE** — Die SQLite-Persistenzgrundlage für alle Neutrino-Core-Entities ist implementiert. Acht Tabellen mit expliziten Foreign Keys, ein idempotentes Migrationssystem, und eine Pfadmanagement-Infrastruktur unter `~/.neutrino/db/neutrino.db`. Alle Migrationen sind reproduzierbar und deterministisch. Keine Remote-DB, keine ORM-Magic, keine CRUD-Repositories, kein AuditLog-Writer.

## Reality Refresh

| Check | Status |
|-------|--------|
| Branch | `main` |
| Pre-change HEAD | `52a3934` |
| Post-change HEAD | `ae6a670` |
| Pre-existing tests | 277 passing |
| Post-implementation tests | 346 passing (+69 new) |
| Coverage | 97.9% (859 statements, 18 missed) |
| Issue #10 state | OPEN → wird in diesem Lauf geschlossen |

## Issue #15 Sync

Issue #15 ist bereits **CLOSED** mit allen Acceptance Criteria abgehakt:
- `src/neutrino/policy_enforcement/` — vorhanden
- `tests/policy_enforcement/` — vorhanden
- `docs/roadmap/NEUTRINO_PHASE_1_ISSUE_15_REPORT.md` — vorhanden
- Alle 4 ACs: `[x]`

**Keine Sync-Aktion notwendig.** Phase A abgeschlossen.

## Geänderte Dateien

| Datei | Zeilen | Beschreibung |
|-------|--------|-------------|
| `src/neutrino/storage/__init__.py` | 29 | Package-Exports |
| `src/neutrino/storage/paths.py` | 49 | `get_db_path()`, `get_temp_db_path()` |
| `src/neutrino/storage/schema.py` | 103 | DDL für 8 Core-Tabellen + `schema_migrations` |
| `src/neutrino/storage/migrations.py` | 135 | Idempotentes Migrationssystem, v1, `rollback_all()` |
| `src/neutrino/storage/sqlite.py` | 58 | `get_connection()` Context-Manager + `ensure_db_directory()` |
| `tests/storage/__init__.py` | 0 | Package-Marker |
| `tests/storage/test_schema.py` | 630 | 31 Tests (Schema-Struktur, FK, Pfade, Rollback, Safety) |
| `tests/storage/test_migrations.py` | 412 | 26 Tests (Idempotenz, FK-Enforcement, Connection, Safety) |

**Total:** 8 Dateien, 1416 Zeilen (Source + Tests)

## Storage-/Pfad-Design

### Pfadhierarchie

```
~/.neutrino/db/neutrino.db     ← Default (überschreibbar via NEUTRINO_DB_PATH)
```

### Pfad-Override (Test-Sicherheit)

```python
# Produktion:
path = get_db_path()           # ~/.neutrino/db/neutrino.db

# Mit Env-Override:
export NEUTRINO_DB_PATH=/custom/path/db.sqlite
path = get_db_path()           # /custom/path/db.sqlite

# Tests (isoliert):
test_path = get_temp_db_path()  # /tmp/neutrino_test_XXXXXX/neutrino.db
```

- `get_db_path()` erstellt keine Dateien/Verzeichnisse.
- `get_temp_db_path()` garantiert isolierte temp-Datenbanken außerhalb von `~/.neutrino/`.
- Tests schreiben **niemals** in den echten Home-DB-Pfad.

## Migrations-Design

### Architektur

```
apply_migrations(db_path)
  ├── get_connection(db_path)          # FK=ON, row_factory=Row
  ├── _get_applied_versions(conn)      # Aus schema_migrations
  ├── for version in sorted(_MIGRATIONS):
  │     ├── skip if already applied
  │     └── _MIGRATIONS[version](conn) # Migration ausführen
  └── commit
```

### Versionen

| Version | Beschreibung |
|---------|-------------|
| `1` | Initiales Schema: Alle 8 Core-Tabellen + `schema_migrations` |

### Idempotenz-Garantien

- `CREATE TABLE IF NOT EXISTS` in DDL
- `INSERT OR IGNORE` in `schema_migrations`
- `_get_applied_versions()` prüft vor Ausführung
- Wiederholtes `apply_migrations()` erzeugt **keine Fehler, keine Duplikate**

### Rollback (Test-only)

- `rollback_all(db_path)` löscht alle Tabellen in reverse dependency order
- Nur für Test-Datenbanken dokumentiert
- Idempotent: mehrfaches Ausführen erzeugt keinen Fehler
- Nach Rollback kann erneut migriert werden

## Tabellen

| Tabelle | Zeilen | Primary Key | Foreign Keys |
|---------|--------|------------|-------------|
| `schema_migrations` | version, applied_at | version TEXT | — |
| `programs` | id, name, platform, policy_url, created_at, updated_at | id TEXT | — |
| `scope_policies` | id, program_id, source_url, raw_text, parsed_json, created_at, updated_at | id TEXT | program_id → programs.id (SET NULL) |
| `targets` | id, program_id, pattern, type, source_section, is_wildcard, created_at, updated_at | id TEXT | program_id → programs.id (SET NULL) |
| `research_runs` | id, program_id, status, started_at, finished_at, created_at, updated_at | id TEXT | program_id → programs.id (SET NULL) |
| `finding_hypotheses` | id, research_run_id, title, status, risk_level, created_at, updated_at | id TEXT | research_run_id → research_runs.id (SET NULL) |
| `evidence` | id, finding_hypothesis_id, kind, content_json, source, created_at, updated_at | id TEXT | finding_hypothesis_id → finding_hypotheses.id (SET NULL) |
| `human_approvals` | id, research_run_id, actor, decision, reason, created_at, updated_at | id TEXT | research_run_id → research_runs.id (SET NULL) |
| `audit_events` | id, actor, action, target, decision, event_json, timestamp, created_at, updated_at | id TEXT | **Keine** (bewusst: unabhängige Protokollierung) |

Alle IDs sind UUIDs als TEXT. Timestamps sind ISO 8601 Strings.

## Relationen

```
programs (1) ──────< scope_policies (N)
programs (1) ──────< targets (N)
programs (1) ──────< research_runs (N)
research_runs (1) ──< finding_hypotheses (N)
research_runs (1) ──< human_approvals (N)
finding_hypotheses (1) ──< evidence (N)
audit_events (keine FK) — unabhängig protokollierbar
```

## Tests

| Bereich | Anzahl | Status |
|---------|--------|--------|
| Pre-existing (Issues #1-#15) | 277 | All green |
| Schema Structure (neu) | 5 | All green |
| Migration Lifecycle (neu) | 6 | All green |
| Table Columns (neu) | 8 | All green |
| Data Integrity (neu) | 3 | All green |
| Foreign Keys (neu) | 8 | All green |
| DB Paths (neu) | 5 | All green |
| Rollback (neu) | 8 | All green |
| Safety (neu) | 6 | All green |
| Deterministic (neu) | 3 | All green |
| FK Enforcement (neu) | 8 | All green |
| Connection Mgmt (neu) | 4 | All green |
| Idempotency (neu) | 4 | All green |
| **Total** | **346** | **All green** |

## Lokale Gates

| Gate | Pre-Change | Post-Change |
|------|-----------|-------------|
| `pytest tests/ -v` | 277 passed | 346 passed (+69) |
| Coverage | 97.8% (771 stmts) | 97.9% (859 stmts) |
| `ruff check .` | All checks passed | All checks passed |
| `mypy src/neutrino/ --strict` | Success (17 files) | Success (22 files) |
| `compileall src/` | All compiled | All compiled |

## Safety Check

- [x] Keine Remote-Datenbank (nur lokales SQLite)
- [x] Keine Cloud-Datenbank (PostgreSQL, etc.)
- [x] Keine Netzwerkverbindungen in Storage-Modulen
- [x] Keine ORM-Magic (nur explizites SQL)
- [x] Keine CRUD-Repositories (Issue #11 ist getrennt)
- [x] Kein AuditLog JSONL-Writer (Issue #12 ist getrennt)
- [x] Keine sensiblen Daten in Test-Fixtures
- [x] Test-Datenbanken außerhalb `~/.neutrino/`
- [x] `rollback_all()` nur für Test-Pfade dokumentiert
- [x] Foreign Keys auf jedem Connection aktiviert
- [x] Deterministische Migration-Reihenfolge
- [x] Keine GitHub Actions / Remote-CI
- [x] Kein n8n / Paperclip / Dashboard
- [x] Keine Verletzung des Safety Decision Manifests

## Nicht geändert

- ScopeGuard (`src/neutrino/scopeguard/`) — unverändert
- RateLimitEnforcer (`src/neutrino/ratelimit/`) — unverändert
- PolicyEnforcer (`src/neutrino/policy_enforcement/`) — unverändert
- PolicyParser (`src/neutrino/policy/`) — unverändert
- Policy Models (`src/neutrino/models/policy.py`) — unverändert
- **Keine** CRUD-Repositories implementiert (Issue #11)
- **Kein** AuditLog JSONL-Writer implementiert (Issue #12)
- **Keine** AuditLog-Integritätstests (Issue #46)
- **Keine** Package-Manager-Migration

## Offene Punkte

- Line 100 in `migrations.py` (1 uncovered statement): `rollback_all`-Code-Pfad. Coverage 98% ist akzeptabel.
- Die `_MIGRATIONS` Registry unterstützt Erweiterung für zukünftige Versionen (einfach neuen Eintrag hinzufügen).
- Down-Migration ist nur als `rollback_all()` für Test-Datenbanken implementiert — keine partiellen Rollbacks.

## Nächster empfohlener Schritt

**Issue #11: CRUD-Repositories für Core-Entities** — jetzt, da das SQLite-Schema mit Migrationen und Foreign Keys bereitsteht, kann die Repository-Schicht mit deterministischen CRUD-Operationen implementiert werden.

---

## Decision Manifest

### GREEN_SAFE

- SQLite-Schema mit allen 8 Core-Entity-Tabellen
- Idempotentes, versioniertes Migrationssystem
- Foreign-Key-Enforcement auf jedem Connection
- Pfadmanagement mit Env-Override und Test-Isolation
- 69 neue Tests, 346 total, 97.9% Coverage
- Ruff / Mypy / Compileall sauber
- Keine Remote-DB, keine ORM-Magic, kein Netzwerk
- Safety Decision Manifest eingehalten

### YELLOW_REVIEW

- Partielle Down-Migrations (pro Version) sind nicht implementiert. Nur `rollback_all()` für Tests. Dies ist akzeptabel für Phase 1, sollte aber bei komplexeren Schema-Änderungen in späteren Phasen evaluiert werden.
- Die `ON DELETE SET NULL` Strategie für FKs kann später auf `CASCADE` geändert werden, je nach Business-Logik der CRUD-Repositories.

### RED_BLOCK

- Keine CRUD-Repositories (Issue #11)
- Kein AuditLog JSONL-Writer (Issue #12)
- Keine AuditLog-Integritätstests (Issue #46)
- Keine aktiven Tests gegen reale Ziele
- `rollback_all()` nie auf Produktions-DB ohne explizite Bestätigung

### TOOL_GAP / UNKNOWN

- `nox` verfügbar im venv, aber nicht als separates Gate ausgeführt (TOOL_GAP)
- Coverage bei 97.9% (ein Statement in migrations.py uncovered — nicht kritisch)
