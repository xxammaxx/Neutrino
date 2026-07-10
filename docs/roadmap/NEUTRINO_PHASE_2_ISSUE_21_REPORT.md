# Neutrino Phase 2 — Issue #21 Evidence-State-Diffing Report

## Metadaten

| Field | Value |
|-------|-------|
| Issue | [#21 [Neutrino] Evidence-State-Diffing implementieren](https://github.com/xxammaxx/Neutrino/issues/21) |
| Branch | `main` |
| Commit | `232d7f1` (base), final commit TBD |
| Date | 2026-07-10 |
| Phase | Phase 2 — Lab Validation |
| Safety Class | GREEN_SAFE |
| Status | IMPLEMENTED |

---

## Kurzfazit

Evidence-State-Diffing (Issue #21) ist vollständig implementiert. Der `EvidenceStateDiffer` vergleicht zwei `EvidenceStateSnapshot`-Instanzen deterministisch und erzeugt ein immutables `EvidenceStateDiff`-Result. Alle Akzeptanzkriterien sind erfüllt, alle 956 Tests bestehen, und alle Safety-Grenzen sind eingehalten.

---

## Implementierte Dateien

### Neue Dateien

| Datei | Zeilen | Beschreibung |
|-------|--------|-------------|
| `src/neutrino/evidence_diff/__init__.py` | 67 | Package-Exports (Differ, Models, Helpers) |
| `src/neutrino/evidence_diff/models.py` | 465 | Domain Models: Snapshot, DiffEntry, DiffResult, RepairContext, redaction helpers, snapshot_from_bundle factory |
| `src/neutrino/evidence_diff/differ.py` | 577 | EvidenceStateDiffer: deterministic diff engine |
| `tests/evidence_diff/__init__.py` | 2 | Test package marker |
| `tests/evidence_diff/test_differ.py` | 1008 | 46 tests covering all requirements |
| `docs/roadmap/NEUTRINO_PHASE_2_ISSUE_21_REPORT.md` | — | This report |

---

## Architektur

### Komponenten

```
EvidenceStateDiffer
├── EvidenceStateSnapshot (Snapshots)
│   └── EvidenceSnapshotItem[] (per-item hashes/summaries)
├── EvidenceStateDiff (Result)
│   ├── EvidenceDiffEntry[] (individual changes)
│   ├── RepairContext (manual review, never auto-fix)
│   └── Summary counts
```

### Datenfluss

```
EvidenceBundle → snapshot_from_bundle() → EvidenceStateSnapshot
                                            │
EvidenceStateDiffer.diff(baseline, current)
                                            │
                                            ▼
                                     EvidenceStateDiff
                                     ├── status: PASS|WARN|FAIL
                                     ├── entries: EvidenceDiffEntry[]
                                     ├── repair_context: RepairContext
                                     ├── summary: {counts}
                                     └── timestamp
```

---

## Akzeptanzkriterien

### 1. Änderungen zwischen Runs werden erkannt

| Change Type | Reason Code | Test |
|------------|-------------|------|
| Item added | ITEM_ADDED | `test_item_added` |
| Item removed | ITEM_REMOVED | `test_item_removed` |
| Content changed | CONTENT_CHANGED | `test_content_changed` |
| Scope changed | SCOPE_CHANGED / SCOPE_MISMATCH | `test_scope_changed`, `test_scope_mismatch_*` |
| Reproducibility marker changed | REPRODUCIBILITY_MARKER_CHANGED | `test_reproducibility_marker_changed` |
| Minimal flag changed | MINIMAL_FLAG_CHANGED | `test_minimal_flag_changed` |
| Data classification changed | DATA_CLASSIFICATION_CHANGED | `test_data_classification_changed` |
| Oracle status changed | ORACLE_STATUS_CHANGED | `test_oracle_status_changed_to_fail` |
| Identical snapshots | UNCHANGED | `test_identical_snapshots_pass` |

### 2. Ergebnisse sind nachvollziehbar

- Jeder `EvidenceDiffEntry` hat: `item_id`, `change_type`, `field`, `before`, `after`, `reason_code`, `severity`
- `EvidenceStateDiff` hat: `status`, `baseline_id`, `current_id`, `summary`, `errors`, `warnings`, `timestamp`
- Reason-Codes sind deterministisch (Enum `EvidenceDiffReasonCode`)
- Summary enthält Zähler nach Change-Type und Severity

### 3. RepairContext nur für erlaubte Runs

- `allowed=True`: kein Scope-Mismatch, Current existiert, kein SENSITIVE_DATA_DETECTED
- `allowed=False`: Scope-Mismatch (`test_scope_mismatch_blocks_repair_context`)
- `allowed=False`: Missing current (`test_missing_current_blocks_repair_context`)
- `allowed=False`: Sensitive data fail (`test_sensitive_data_fail_blocks_repair_context`)
- RepairContext enthält KEINE: Commands, HTTP-Requests, Auto-Fixes (`test_repair_context_contains_no_commands/requests/auto_fixes`)

### 4. Fehlende Vergleichsdaten werden behandelt

- Baseline fehlt → `MISSING_BASELINE` mit WARN (`test_baseline_missing`)
- Current fehlt → `MISSING_CURRENT` mit FAIL (`test_current_missing`)
- Beide fehlen → FAIL mit beiden Einträgen (`test_both_missing`)
- Keine Exceptions bei normalen Missing-Fällen (`test_missing_*_does_not_crash`)

---

## Sensitive Data Handling

- `redact_sensitive_recursive()` redigiert rekursiv alle Werte sensibler Keys
- `SENSITIVE_FIELDS` aus `evidence_oracle.models` (131 Felder inkl. `credentials`, `password`, `token`, etc.)
- Sensitive Werte werden durch `[REDACTED]` ersetzt
- `REDACTED_MARKER` ist als Konstante exportiert
- `snapshot_from_bundle` redigiert sensitive Felder vor Summary-Generierung
- `MAX_CONTENT_SUMMARY_BYTES = 64 KiB` (größere Inhalte nur als Hash)

---

## Determinism

- Gleiche Inputs → gleiche Outputs (`test_same_inputs_same_outputs`)
- Items werden stabil sortiert (nach `item.id`)
- Timestamp ist injizierbar (`test_timestamp_injectable`)
- Summary-Zähler sind deterministisch (`test_summary_counts_deterministic`)

---

## Safety Check

| Check | Status |
|-------|--------|
| Keine Netzwerk-Imports (urllib, requests, httpx, aiohttp, socket) | PASS |
| Keine Shell/subprocess-Imports (subprocess, os.system, shlex, pty) | PASS |
| Keine DNS-Imports (dns, socket.getaddrinfo, gethostbyname) | PASS |
| Keine Scanner-Imports (nmap, scanner, exploit, payload, nuclei) | PASS |
| Keine realen Targets (nur In-Memory-Fixtures) | PASS |
| Keine n8n/Paperclip/API/Dashboard-Integration | PASS |
| Keine automatische Report-Einreichung | PASS |
| Extra-Fields verboten (extra="forbid") | PASS |
| Immutable Models (frozen=True) | PASS |
| RepairContext ohne Commands/Requests/Auto-Fixes | PASS |

---

## Tests

### Testübersicht

```
tests/evidence_diff/test_differ.py:
├── TestSnapshotModel (6 tests)
├── TestMissingData (6 tests)
├── TestDiffDetection (9 tests)
├── TestScopeSafety (7 tests)
├── TestRepairContext (7 tests)
├── TestDeterminism (4 tests)
├── TestAudit (4 tests)
├── TestSafety (9 tests)
├── TestEdgeCases (9 tests)
└── TestModelEdgeCases (5 tests)
─────────────────────────────
Total: 46 tests (+ 910 existing = 956 total)
```

### Coverage

```
src/neutrino/evidence_diff/differ.py   140    3   98%
src/neutrino/evidence_diff/models.py   140   31   78%
```
- Gesamt-Coverage: 95.43% (≥ 80%-Minimum)
- Alle 956 Tests: **PASSED**

---

## Lokale Gates

| Gate | Result |
|------|--------|
| `python3 -m pytest tests/ -v` | 956 passed, 0 failed |
| `python3 -m compileall src/` | All compiled successfully |
| `ruff check .` | 0 findings in evidence_diff (11 pre-existing elsewhere) |
| `mypy src/neutrino/ --strict` | 0 errors in evidence_diff (3 pre-existing in approval/workflow.py) |

---

## Bug Fix

Ein einziger Test-Fehler wurde behoben:

- **`test_nested_sensitive_fields_redacted`**: Der Key `"credentials"` ist in `SENSITIVE_FIELDS` enthalten (siehe `evidence_oracle/models.py` line 109). Daher ersetzt `redact_sensitive_recursive` den gesamten Wert korrekt mit `[REDACTED]`. Die Test-Assertion wurde von:
  ```python
  assert redacted["body"]["credentials"]["password"] == REDACTED_MARKER
  ```
  geändert zu:
  ```python
  assert redacted["body"]["credentials"] == REDACTED_MARKER
  ```

---

## Abhängigkeiten

- [x] **Issue #20** (Evidence Oracle): CLOSED, Code vorhanden in `src/neutrino/evidence_oracle/`
- [x] **Issue #19** (Validation Executor): CLOSED, Code vorhanden in `src/neutrino/validation_executor/`
- [x] **Issue #15** (Program Prohibitions): CLOSED
- [ ] **Issue #9** (Report Quality Gate): NICHT Teil dieses Scopes (explizit ausgeschlossen)

---

## Nicht-Ziele (eingehalten)

- [x] Keine Verbindung zu realen Targets
- [x] Keine aktiven Security-Tests außerhalb lokaler Labs
- [x] Keine Exploit-Ausführung ohne ScopeGuard+Approval
- [x] Keine automatische Report-Einreichung von Lab-Ergebnissen
- [x] Kein #9 Report Quality Gate
- [x] Keine n8n/Paperclip/API/Dashboard-Integration

---

## Nächster sinnvoller Schritt

Phase 2 "Lab Validation" ist mit #21 abgeschlossen. Nächste Phase:
- **Phase 3 — n8n Workflow Bridge**: Integration des Neutrino-Cores mit n8n für workflow-basierte Automatisierung
- Oder: Phase 2 weiter ausbauen mit #9 Report Quality Gate (wenn benötigt)

---

## Decision Manifest

| Decision | Rationale |
|----------|-----------|
| `EvidenceStateSnapshot` speichert nur Hashes + Summaries | Kein Raw-Content im Diff; Sicherheit und Determinismus |
| `RepairContext` nie mit Commands/Requests/Auto-Fixes | Human Approval bleibt verpflichtend |
| `extra="forbid"` auf allen Models | Keine Bypass-Felder |
| `frozen=True` auf allen Models | Immutable Results sind auditierbar |
| `_FIELD_RULES`-Tabelle für Per-Field-Vergleiche | Erweiterbar und deterministisch |
| `MISSING_BASELINE` → WARN, `MISSING_CURRENT` → FAIL | Baseline ist optional, Current ist Pflicht |
| `minimal: True→False` → FAIL-Severity | Degradation der Minimalität ist sicherheitsrelevant |
| Sensitive Keys aus `evidence_oracle.models.SENSITIVE_FIELDS` | Single Source of Truth für sensitive Feldnamen |
| `snapshot_from_bundle()` als Factory | Brücke zwischen EvidenceBundle (#20) und StateSnapshot (#21) |
