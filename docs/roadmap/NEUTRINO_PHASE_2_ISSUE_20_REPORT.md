---
title: "Phase 2 Issue #20 Report"
issue: 20
commit: 232d7f1
branch: main
---

# Phase 2 — Issue #20 Report

## 1. Kurzfassung

Implementiert wurde das eigenständige **Evidence Oracle** als deterministischer, fail-closed Qualitätsprüfer für lokale Evidence-Bundles.

Warum: Evidence muss vor Speicherung, Weitergabe oder Reporting auf Mindestqualität geprüft werden.

Ergebnis: Das Oracle bewertet Bundles und Items reproduzierbar, blockiert unsichere Inhalte und bleibt strikt offline.

## 2. Architektur-Design

### Kernmodelle

- **EvidenceItem** — atomare Evidence-Einheit mit `id`, `kind`, `scope_reference`, `source`, `content`, `collected_at`, `minimal`, `reproducibility_marker`, `metadata`
- **EvidenceBundle** — Sammlung von Items für ein Finding oder einen Run
- **EvidenceCheckResult** — Ergebnis einer einzelnen Prüfung mit Status, Reason Code und Detail
- **EvidenceOracleResult** — aggregiertes Ergebnis mit Status, Checks, Errors, Warnings, Timestamp
- **ReasonCode** — deterministische, maschinenlesbare Codes für alle Prüfpfade

### Design-Eigenschaften

- `extra="forbid"` für alle Modelle
- `frozen=True` für alle Modelle
- deterministische Aggregation: **FAIL > WARN > PASS**
- keine Netzwerkzugriffe, keine Shell, keine Subprocesses
- keine aktiven Tests gegen reale Targets
- kein Evidence-State-Diffing (#21)

## 3. Implementierte Prüfungen

| Prüfung | Status | Reason Code |
|---|---|---|
| Bundle fehlt | FAIL | `MISSING_BUNDLE` |
| Bundle hat keine Items | FAIL | `MISSING_ITEMS` |
| Bundle- oder Item-Scope fehlt | FAIL | `MISSING_SCOPE_REFERENCE` |
| Scope ist `UNKNOWN` | FAIL | `UNKNOWN_SCOPE` |
| Item-Scope weicht vom Bundle-Scope ab | FAIL | `SCOPE_MISMATCH` |
| Reproducibility-Marker fehlt | FAIL | `NO_REPRODUCIBILITY_MARKER` |
| Reproducibility-Marker ist leer | FAIL | `EMPTY_REPRODUCIBILITY_MARKER` |
| `minimal=False` | FAIL | `MINIMAL_DATA_VIOLATION` |
| Sensible Felder in `content` | FAIL | `SENSITIVE_DATA_DETECTED` |
| Sensible Felder in `metadata` | FAIL | `SENSITIVE_DATA_DETECTED` |
| Content ist leer | FAIL | `MISSING_CONTENT` |
| Payload über Soft-Limit | WARN | `PAYLOAD_WARN` |
| Payload über Hard-Limit | FAIL | `EXCESSIVE_PAYLOAD` |
| Unbekannter `kind` | FAIL | `UNKNOWN_DATA_CLASSIFICATION` |
| Alle Checks bestanden | PASS | `OK` |

## 4. Dateien

### Issue #20 Implementation

- `src/neutrino/evidence_oracle/__init__.py`
- `src/neutrino/evidence_oracle/models.py`
- `src/neutrino/evidence_oracle/oracle.py`
- `tests/evidence_oracle/test_oracle.py`

### Dokumentation

- `docs/roadmap/NEUTRINO_PHASE_2_ISSUE_20_REPORT.md`

## 5. Tests

- **Gesamt:** 56 Tests
- **Kategorien:**
  - Missing Evidence
  - Reproducibility Checks
  - Scope Checks
  - Minimal Data / Sensitive Fields
  - Payload Size Checks
  - Unknown Data Classification
  - Result Model Serialization
  - Determinism
  - Bundle Scope Edge Cases
  - Safety Checks
  - Auditability
  - Edge Cases
  - Review-Agent Hardening Tests
- **Abdeckung:** `evidence_oracle` 97%

## 6. Gates

- `ruff` — bestanden
- `compileall` — bestanden
- `pytest` — 56/56 bestanden
- `coverage` — `evidence_oracle: 97%`

## 7. Safety-Ergebnisse

Review-Agent Findings wurden adressiert:

- **Recursion-Limit** — rekursive Sensitive-Field-Prüfung ist auf maximale Tiefe begrenzt
- **Timestamp-Validierung** — leere/Whitespace-Timestamps führen fail-closed zu FAIL
- **Warnings-Population** — WARN-Checks werden in `warnings` übernommen
- **MAX_ITEMS** — Bundle-Größenlimit erzwingt FAIL bei Überschreitung

## 8. Nicht gebaut

Abgrenzung zu Issue #21:

- kein State-Diffing
- keine aktiven Tests
- keine echten Targets
- keine Netzwerk-, Shell- oder Remote-Operationen

## 9. Commit-Referenz

- `232d7f1` auf `main`

## 10. Issue-Status

- **#20:** geschlossen
- **#21:** nächster Schritt

## 11. Decision Manifest

### ADR: Evidence Oracle als eigenständiges Modul

Entscheidung: Das Evidence Oracle bleibt als eigenes Modul `neutrino.evidence_oracle` mit klarer API und separaten Domain-Modellen.

Begründung:

- klare Trennung von Evidenzprüfung und Folgeprozessen
- deterministische, auditierbare Minimum-Checks
- unabhängige Testbarkeit ohne aktive Ziele
- saubere Abgrenzung zu #21 (State-Diffing)
