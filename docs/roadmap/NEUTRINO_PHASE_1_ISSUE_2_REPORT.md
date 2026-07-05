# Neutrino Phase 1 — Issue #2 Report

> Erstellt: 2026-07-05
> Orchestrator: Issue Orchestrator (deepseek-v4-pro)
> Commit: `0b6a989` auf `main`

---

## Kurzfazit

**GREEN** — Issue #2 vollständig umgesetzt, 42/42 Tests grün, alle Akzeptanzkriterien erfüllt, alle lokalen Gates grün (ruff 0w, mypy 0e).

---

## Reality Refresh

| Parameter | Wert |
|-----------|------|
| Default Branch | `main` |
| Ausgangs-HEAD | `8554d05` |
| Finaler HEAD | `0b6a989` |
| Git-Status | clean |
| Python-Version | 3.12.3 (venv) |

### Abhängige Issues (Status)

| Issue | Titel | Status |
|-------|-------|--------|
| #1 | Policy-Parser Grundstruktur | CLOSED |
| #2 | In-Scope-/Out-of-Scope-Extraktion | CLOSED (dieser Lauf) |
| #51 | GitHub Issue-/PR-Templates | CLOSED |
| #52 | Code-Konventionen & Build-Standard | CLOSED |

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `docs/roadmap/NEUTRINO_PHASE_0_1_SYNC_REPORT.md` | +2 Zeilen: HEAD-Konsistenz-Hinweis |
| `src/neutrino/models/policy.py` | +2 Felder (`is_wildcard`, `source_section`), Typ-Annotation-Modernisierung |
| `src/neutrino/policy/parser.py` | Umbenennung `_extract_domain_entries` → `_extract_scope_entries`, line-by-line-Parsing, IP-Range/URL/Wildcard-Erkennung |
| `tests/policy/test_parser.py` | +17 neue Tests, 5 neue Policy-Fixtures |

---

## Parser-Änderungen

### Vorher
- `_extract_domain_entries()`: reines Regex-Scanning, nur Domain-Muster
- Kein Unterschied zwischen `domain` und `wildcard_domain`
- Keine IP-Range-Erkennung (`192.0.2.0/24` wurde ignoriert)
- URL-Pfade gingen verloren (`app.example.com/v2/` → `app.example.com`)
- Out-of-Scope-Marker: 5 Keywords

### Nachher
- `_extract_scope_entries()`: Zeilenweises Parsing mit drei Pattern-Ebenen:
  1. **IP-Range** → `type="ip_range"`, `is_wildcard=False`
  2. **URL mit optionalem Pfad** → Klassifikation nach Pfadmerkmalen:
     - `/api/` oder `/v` im Pfad → `type="api"`
     - anderer Pfad → `type="url"`
     - kein Pfad, Wildcard → `type="wildcard_domain"`
     - kein Pfad, kein Wildcard → `type="domain"`
  3. **Domain-Fallback** → `type="domain"` oder `"wildcard_domain"`
- Out-of-Scope-Marker: 8 Keywords (+`ineligible`, `prohibited targets`, `not eligible`)
- `source_section` wird an allen Einträgen gesetzt (`"in_scope"` / `"out_of_scope"`)

---

## Modellentscheidung

### `is_wildcard: bool` (Option B gewählt)

**Begründung:** Minimal-invasiv. Ein bool-Feld erzeugt weniger Breaking Changes als eine Enum-Erweiterung des `type`-Felds. Bestehende Code-Pfade, die `type` vergleichen, bleiben funktional.

### `source_section: str | None`

**Begründung:** Einfaches, nachvollziehbares Tracing für jeden extrahierten Eintrag. Kein komplexes Quellen-Mapping nötig.

### Asset-Typen

| Typ | Trigger |
|-----|---------|
| `domain` | `api.example.com`, `example.com` |
| `wildcard_domain` | `*.example.com`, `*.dev.example.com` |
| `ip_range` | `192.0.2.0/24`, `203.0.113.0/28` |
| `url` | `app.example.com/dashboard`, `portal.example.com/admin` |
| `api` | `api.example.com/v1/`, `rest.example.com/api/` |
| `unknown` | Fallback (nicht automatisch vergeben) |

### Nebenbei gefixt

- **Ruff:** 17 → 0 Warnungen (`Optional[X]` → `X | None`, SIM102/103/110, UP045)
- **Mypy:** 1 → 0 Fehler (`dict` type-arg in `RateLimit`-Extraktion: `**kwargs` → explizite Variablen)

---

## Tests

| # | Test | Fixture | Ergebnis |
|---|------|---------|----------|
| 1 | `test_extract_wildcard_domains_with_is_wildcard` | COMPREHENSIVE_POLICY | ✅ |
| 2 | `test_extract_ip_ranges` | COMPREHENSIVE_POLICY | ✅ |
| 3 | `test_extract_url_with_path` | COMPREHENSIVE_POLICY | ✅ |
| 4 | `test_extract_domain_type_unchanged` | COMPREHENSIVE_POLICY | ✅ |
| 5 | `test_source_section_tracking_in_scope` | COMPREHENSIVE_POLICY | ✅ |
| 6 | `test_source_section_tracking_out_of_scope` | COMPREHENSIVE_POLICY | ✅ |
| 7 | `test_out_of_scope_wildcard` | COMPREHENSIVE_POLICY | ✅ |
| 8 | `test_out_of_scope_overrides_in_scope_extraction` | COMPREHENSIVE_POLICY | ✅ |
| 9 | `test_ineligible_marker_extraction` | POLICY_INELIGIBLE | ✅ |
| 10 | `test_prohibited_targets_marker_extraction` | POLICY_PROHIBITED | ✅ |
| 11 | `test_api_type_detection` | POLICY_API_TARGETS | ✅ |
| 12 | `test_url_type_vs_domain_type` | POLICY_URL_WITH_PATH | ✅ |
| 13 | `test_deterministic_enhanced_parsing` | COMPREHENSIVE_POLICY | ✅ |
| 14 | `test_no_network_in_parse_from_text` | COMPREHENSIVE_POLICY | ✅ |
| 15 | `test_scope_entry_with_source_section_serialization` | (direkt) | ✅ |
| 16 | `test_minimal_policy_with_only_one_target` | (inline) | ✅ |
| 17 | `test_empty_scope_sections` | (inline) | ✅ |

Gesamt: **42/42 Tests** (25 Bestand + 17 Neu)

---

## Lokale Gates

| Check | Ergebnis |
|-------|----------|
| `pytest tests/ -v` (venv) | 42/42 passed ✅ |
| `python3 -m compileall src/` | OK ✅ |
| `ruff check .` | 0 warnings ✅ |
| `mypy src/neutrino/ --strict` | 0 errors ✅ |
| Coverage | 96% ✅ |

---

## Safety Check

| Prüfung | Status |
|---------|--------|
| Keine realen Targets kontaktiert | ✅ |
| Keine DNS-Auflösung | ✅ |
| Keine HTTP-Requests gegen reale Domains | ✅ |
| Alle Tests mit lokalen Fixtures | ✅ |
| Default-Deny erhalten | ✅ |
| Out-of-Scope schlägt In-Scope | ✅ |
| Keine GitHub Actions aktiviert | ✅ |
| Keine Remote-CI konfiguriert | ✅ |
| Keine Package-Manager-Migration | ✅ |

---

## Nicht geändert

- `parse_from_url()` — unverändert, verwendet weiterhin `parse_from_text()` intern
- `_extract_rules()`, `_extract_program_name()`, `_strip_html()` — keine Änderungen
- `ScopePolicy.is_in_scope()` — Logik unverändert (nur SIM110-Refactoring)
- Keine ScopeGuard-, Human-Approval-, RAG-, n8n-, Paperclip-, Lab- oder Dashboard-Funktionen

---

## Offene Punkte

Keine. Issue #2 vollständig abgeschlossen.

---

## Nächster empfohlener Schritt

**Issue #5: ScopeGuard Request-Gating implementieren**

Issue #2 war als direkter Vorgänger für #5 spezifiziert. Der ScopePolicy-Datensatz mit `is_in_scope()`, `source_section` und `is_wildcard` ist jetzt bereit für den ScopeGuard.

---

## Decision Manifest

### GREEN_SAFE

- `ScopeEntry.is_wildcard` (bool) als minimal-invasive Wildcard-Markierung
- `ScopeEntry.source_section` (str | None) für Quellen-Nachvollziehbarkeit
- Zeilenweises Parsing in `_extract_scope_entries` für robustere Extraktion
- IP-Range-Erkennung mit dediziertem Regex
- URL-Pfad-Erhalt durch erweiterten URL-Regex
- Alle Ruff-Warnungen gefixt (0 warnings)
- Alle Mypy-Fehler gefixt (0 errors)
- 17 neue Tests, 42/42 passing, 96% Coverage
- Sync-Report HEAD-Konsistenz dokumentiert

### YELLOW_REVIEW

- Asset-Typ-Klassifikation (`api` vs `url`) basiert auf Pfad-Heuristiken (`/api/`, `/v`). Diese sind deterministisch, aber könnten bei sehr ungewöhnlichen Policy-Formaten falsch positiv sein. Owner kann später feinere Regeln definieren.

### RED_BLOCK

- Nichts — keine gefährlichen Aktionen ausgeführt

### TOOL_GAP / UNKNOWN

- Nichts — alle Gates lokal verifiziert

---

## Abschluss-Fußzeile

```text
Phase 1 — Issue #2: 2026-07-05
Commit: 0b6a989 → main
Tests: 42/42 ✓, Coverage: 96% ✓
Ruff: 0w ✓, Mypy: 0e ✓
Status: CLOSED — GREEN_SAFE
```
