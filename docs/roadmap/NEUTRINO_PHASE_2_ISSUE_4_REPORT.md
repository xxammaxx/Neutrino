# Neutrino Phase 2 — Issue #4 Human Authorization Workflow Report

## Kurzfazit

**GREEN** — Human Authorization Workflow vollständig implementiert.

- ApprovalRequest enthält Scope-Informationen, geplante Testart und Risk Summary
- HumanDecision mit striktem APPROVE/REJECT (kein Auto-/LLM-/Time-Approval)
- Gate-Check: Default-Deny, nur explizites APPROVE → allow=True
- Statuswechsel werden persistiert und auditiert
- 641 Tests (587 bestehend + 54 neu), alle grün
- Ruff clean, Mypy clean, Compileall clean
- Keine Sicherheitsverstöße

---

## Reality Refresh

| Check | Wert |
|---|---|
| Default Branch | `main` |
| HEAD before | `e598061` |
| Issue #4 | OPEN, GREEN_SAFE |
| Issue #13 | CLOSED |
| Issue #46 | CLOSED |
| Issue #14 | OPEN, blocked on #4 |
| Open PRs | None |
| `.github/workflows/` | None |
| Tests before | 587 passed |
| Tests after | **641 passed** (+54) |

---

## Geänderte Dateien

### Neue Dateien (Approval-Modul)

| Datei | Beschreibung |
|---|---|
| `src/neutrino/approval/__init__.py` | Package-Exports |
| `src/neutrino/approval/models.py` | `ApprovalRequest`, `HumanDecision`, `ApprovalDecision`, Enums |
| `src/neutrino/approval/workflow.py` | `ApprovalWorkflow` Service (create, decide, check) |
| `tests/approval/__init__.py` | Test-Package |
| `tests/approval/test_human_authorization.py` | 54 Tests (Request, Decision, Gate, Bypass, Audit, Safety) |

### Geänderte Dateien

| Datei | Änderung |
|---|---|
| `src/neutrino/storage/schema.py` | Schema v2, human_approvals um 5 Spalten erweitert |
| `src/neutrino/storage/migrations.py` | Migration v2: ALTER TABLE human_approvals ADD COLUMN |
| `src/neutrino/models/entities.py` | HumanApproval/Create/Update um action, target, scope_reference, test_type, risk_summary erweitert |
| `src/neutrino/storage/repositories/human_approvals.py` | INSERT um neue Spalten erweitert |
| `tests/storage/test_schema.py` | Schema-Version von 1 auf 2 aktualisiert |
| `tests/storage/test_migrations.py` | Row-Count von 1 auf 2 aktualisiert (v1 + v2) |

---

## Approval-Modell

### ApprovalRequest (`src/neutrino/approval/models.py`)

```python
@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    actor: str
    action: str
    target: str
    scope_reference: str       # Pflicht — nicht leer
    test_type: str              # Pflicht — nicht leer
    risk_summary: str           # Pflicht — nicht leer
    created_at: str
    status: ApprovalStatus     # Default: PENDING
```

Validierung im `__post_init__`: leere/whitespace-only Werte für scope_reference, test_type, risk_summary werden abgelehnt.

### HumanDecision (`src/neutrino/approval/models.py`)

```python
@dataclass(frozen=True)
class HumanDecision:
    request_id: str
    decider: str
    decision: DecisionType      # APPROVE oder REJECT
    reason: str                 # Pflicht — nicht leer
    decided_at: str
```

Erlaubte DecisionType-Werte: nur `APPROVE` und `REJECT`. AUTO_APPROVE, LLM_APPROVE, TIMEOUT_APPROVE, IMPLICIT_APPROVE existieren nicht.

### ApprovalDecision / GateResult (`src/neutrino/approval/models.py`)

```python
@dataclass(frozen=True)
class ApprovalDecision:
    gate_result: GateResult
    allow: bool                 # True NUR bei ALLOW_APPROVED
    request_id: str | None
    decision_id: str | None
    explanation: str
```

Invariante: allow=True ist nur für ALLOW_APPROVED gültig — andere GateResults mit allow=True werden im `__post_init__` abgelehnt.

---

## Request-Erstellung

Der `ApprovalWorkflow.create_request()` validiert über das `ApprovalRequest`-Modell, dass alle Pflichtfelder gesetzt sind, und persistiert via `HumanApprovalRepository`.

- Neuer Request startet immer als `PENDING`
- Scope-Information, Testart und Risk Summary sind Pflicht
- Request wird im Repository gespeichert
- Ein AuditEvent `approval_request_created` wird erzeugt

---

## Human Decision Workflow

`ApprovalWorkflow.record_decision()`:

1. Validiert DecisionType (nur APPROVE/REJECT)
2. Lädt existierenden Request (fehlt → ValueError + Audit)
3. Prüft Status == PENDING (sonst ValueError)
4. Mapped APPROVE → APPROVED, REJECT → REJECTED
5. Aktualisiert via Repository
6. Erzeugt AuditEvent `approval_decision_recorded`

Kein Override möglich: bereits entschiedene Requests erzeugen ValueError.

---

## Gate-Check-Logik

`ApprovalWorkflow.check_approval()`:

| Status | GateResult | allow |
|---|---|---|
| APPROVED | ALLOW_APPROVED | True |
| PENDING | BLOCK_PENDING_APPROVAL | False |
| REJECTED | BLOCK_REJECTED | False |
| EXPIRED | BLOCK_EXPIRED_APPROVAL | False |
| Missing | BLOCK_MISSING_APPROVAL | False |
| Unknown | BLOCK_INVALID_REQUEST | False |

Jeder Check wird auditiert (allow oder block).

---

## Persistenz

- Nutzt die erweiterte `human_approvals`-Tabelle (Schema v2)
- Neue Spalten: `action`, `target`, `scope_reference`, `test_type`, `risk_summary`
- Migration v2: `ALTER TABLE human_approvals ADD COLUMN ...` (idempotent)
- Schema-Version auf 2 erhöht
- Existierende v1-Datenbanken erhalten die neuen Spalten mit `DEFAULT ''`

---

## Audit

- **SQLite**: `AuditEventRepository.append()` für strukturierte Audit-Events
- **JSONL**: `AuditLogWriter.append()` für Datei-basierte Audit-Events
- Beide optional — Workflow funktioniert auch ohne Audit-Backends
- Auditierte Aktionen: `approval_request_created`, `approval_decision_recorded`, `approval_decision_blocked`, `approval_gate_check`
- Testverzeichnisse: temporäre DB + temporäres Audit-Dir

---

## Tests

### Neue Tests: 54 (in `tests/approval/test_human_authorization.py`)

| Kategorie | Tests | Beschreibung |
|---|---|---|
| Request Creation | 9 | Scope, TestType, Risk, Default PENDING, Missing Fields, Persistenz |
| Decision Recording | 9 | APPROVE/REJECT, Reason, Decider, Missing Request, Already Decided |
| Gate Check | 10 | Ohne Approval, PENDING, REJECTED, APPROVED, Missing, Deterministic |
| No Bypass | 10 | Kein force/override, ScopeGuard ersetzt nicht, keine Zeit/LLM/Lab-Auto-Approval |
| Persistence/Audit | 7 | Repository-Read, Status-Change, Audit SQLite, Audit JSONL, Temp-Dir |
| Safety | 6 | Keine Netzwerk-Imports, DNS, Shell, n8n/Paperclip, Determinismus |
| Integration | 3 | Full Flow APPROVE, Full Flow REJECT, Multiple Independent Requests |

### Bestehende Tests aktualisiert

- `test_schema_version_is_v2` (vorher v1)
- `test_migrations_are_idempotent` (Row-Count 2 statt 1)
- `test_schema_migrations_rows_after_all` (vorher only_one_row)

---

## Lokale Gates

### Vorher

| Gate | Ergebnis |
|---|---|
| `pytest tests/ -v` | 587 passed |
| `ruff check .` | All checks passed |
| `mypy src/neutrino/ --strict` | Success (41 files) |
| `python3 -m compileall src/` | Success |

### Nachher

| Gate | Ergebnis |
|---|---|
| `pytest tests/ -v` | **641 passed** |
| `ruff check .` | All checks passed |
| `mypy src/neutrino/ --strict` | Success (44 files) |
| `python3 -m compileall src/` | Success |
| Coverage | 96.80% |

---

## Safety Check

- [x] Keine aktive Validierung implementiert
- [x] Keine Auto-Approval-Mechanismen
- [x] Keine LLM-Entscheidung als Approval
- [x] Keine CLI/API-Bypass-Flags
- [x] Keine Lab-Auto-Freigabe
- [x] Keine Zeit-basierte Auto-Approval
- [x] Keine n8n-Integration
- [x] Keine Paperclip-Integration
- [x] Keine echten Requests
- [x] Keine DNS-Auflösung
- [x] Keine Shell-Ausführung
- [x] Keine GitHub Actions
- [x] Keine Remote-CI
- [x] Nur lokale, deterministische Tests
- [x] Temporäre SQLite-DBs und Audit-Verzeichnisse

---

## Nicht geändert

- Issue #14 bleibt offen (Active-Validation-Gate blockiert auf #4)
- Keine API-Endpunkte
- Kein Dashboard
- Keine n8n/Paperclip Webhooks
- Keine Package-Manager-Migration
- Kein Poetry

---

## Offene Punkte

- `AuditLogEvent.from_approval_decision()` Adapter könnte in Zukunft ergänzt werden (niedrige Priorität)
- EXPIRED-Status ist im Modell definiert aber kein automatischer Expiry-Mechanismus (korrekt — kein Auto-Approval)
- ERROR-Status ist definiert aber derzeit nicht vom Workflow gesetzt (für zukünftige Fehlerbehandlung)

---

## Nächster empfohlener Schritt

**Issue #14: Active-Validation-Gate** — Jetzt, da der Human Authorization Workflow (#4) vollständig implementiert ist, kann das Active-Validation-Gate (#14) darauf aufbauen und vor jeder aktiven Validierung den Approval-Status prüfen.
