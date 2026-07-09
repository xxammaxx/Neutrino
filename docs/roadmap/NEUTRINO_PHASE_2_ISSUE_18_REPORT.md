# Neutrino Phase 2 — Issue #18 Validation Recipe Schema Report

## Kurzfazit

**GREEN** — Validation-Recipe-Schema, Modelle, Validator und JSON-Schema-Helfer sind implementiert; die Schema-Ebene ist fail-closed und bereit als Blocker-Freigabe für Issue #19.

## Reality Refresh

- Issue #14: CLOSED
- Issue #18: OPEN → implemented
- Issue #19: OPEN, blocked by #18
- Baseline: 690 tests, 96.89% coverage
- No prior validation_recipe module

## Agentenlauf

- Architecture-Agent: bestätigte das Schema als rein deklarative Schicht; Executor bleibt Issue #19.
- Security-Agent: prüfte Default-Deny, Target-Safety, Import-Verbote, rekursive Forbidden-Field-Scans.
- Compliance-Agent: markierte JSON-Schema als Hilfsartefakt, nicht als Source of Truth.
- Review-Agent: prüfte Scope-Regeln, Step-Semantik und Fail-Closed-Verhalten; Target-Striktheit ist by design.

## Geänderte Dateien

| Datei | Zeilen | Größe |
|---|---:|---:|
| `src/neutrino/validation_recipe/__init__.py` | 53 | n/v |
| `src/neutrino/validation_recipe/models.py` | 294 | n/v |
| `src/neutrino/validation_recipe/validators.py` | 494 | n/v |
| `src/neutrino/validation_recipe/schema.py` | 69 | n/v |
| `tests/validation_recipe/__init__.py` | 0 | n/v |
| `tests/validation_recipe/test_schema.py` | 950 | n/v |
| `docs/roadmap/NEUTRINO_PHASE_2_ISSUE_18_REPORT.md` | 186 | n/v |

Hinweis: Byte-Größen waren mit den verfügbaren Dokumentations-Tools nicht verifizierbar; die Zeilenangaben stammen aus der Quelltextlektüre.

## Schema-Design

- Pydantic-Modelle mit `extra="forbid"` auf allen Schichten, inklusive `ValidationResult`.
- Source of Truth bleibt `validate_recipe()`; JSON Schema ist nur ein Export-Helfer.
- Default-Deny für unbekannte Felder, unbekannte Step-Typen, ungültige Targets und ungültige Scope-Referenzen.
- Keine Ausführungsschicht im Schema; Issue #19 konsumiert nur diese Modelle.

## Recipe-Modell

`ValidationRecipe` verlangt:

- `id`, `name`, `version`, `description`, `scope_references`, `steps`, `created_at`
- `safety_class` nur `non_destructive`
- `destructive` muss `False` bleiben
- `scope_references` non-empty und ohne Whitespace-Only-Einträge
- `steps` non-empty
- Bounds: max. 20 Steps, max. 64 KB Rohinput, max. 8 Verschachtelungsebenen

## Step-Modell

`ValidationStep` verlangt:

- `id`, `name`, `step_type`, `target`, `scope_reference`, `expected_evidence`
- `step_type` allowlisted: `http_check`, `tcp_check`, `evidence_check`, `manual_observation`, `local_fixture_check`
- `target` konservativ: Loopback/localhost, Lab-Platzhalter, `fixture:` / `lab:`-Referenzen
- `requires_approval` für `http_check` und `tcp_check` zwingend `True`
- `timeout_seconds` nur 1–300
- `destructive` muss `False` bleiben
- `safety_class` nur `non_destructive`

## Verbotsregeln

`FORBIDDEN_FIELD_NAMES`: 22 Einträge, rekursiv und case-insensitive gescannt.

Enthalten sind u. a. `command`, `shell`, `exec`, `subprocess`, `script`, `payload`, `exploit`, `scanner`, `raw_request`, `pickle`, `eval`, `os_system`.

## Scope-Referenzen

Format: `scope:namespace/id`, `program:id#target:id`.

- Keine Wildcards
- Keine Platzhalter wie `*`, `all`, `default`, `any`
- Step-Scope muss exakt in `recipe.scope_references` enthalten sein

## Target-Safety

- Erlaubt: `localhost`, `127.0.0.1`, `::1`
- Erlaubt: `fixture:`-, `lab:`-Referenzen, `{scope:...#target:...}`-Platzhalter
- Erlaubt: Lab-Hostnamen (`lab-*`, `*.lab.local`, `*.test`)
- Verworfen: öffentliche IPs, private IPs, Wildcards, fremde Domains, unsichere Schemes

## Validator

`validate_recipe()` ist deterministisch und fail-closed. Prüfpfad:

1. Rekursiver Forbidden-Field-Scan
2. Bounds-Checks
3. Pydantic-Parsing mit `extra="forbid"`
4. Scope-Formatprüfung
5. Step-Scope-Match gegen Rezept-Scope
6. Konservative Target-Prüfung
7. Step-Typ-Semantik
8. Safety-/Destructive-Checks

## Tests

- 103 Testfunktionen / 113 effektive Testfälle
- Abdeckung nach Kategorie:

| Kategorie | Fälle |
|---|---:|
| Valid recipes | 12 |
| Required fields | 17 |
| Forbidden fields | 20 |
| Target safety | 18 |
| Scope rules | 9 |
| Non-destructive | 6 |
| Fail-closed | 7 |
| Step-type semantics | 16 |
| Safety imports | 4 |
| Bounds / limits | 4 |

## Lokale Gates

- pytest: 803 passed (was 690), 96.17% coverage
- ruff: style-only warnings (pre-existing pattern)
- mypy: 3 pre-existing errors in `approval/workflow.py`; new module clean
- compileall: clean

## Safety Check

- No executor code
- No HTTP client/socket/subprocess imports
- No real targets
- No shell/command execution
- Recursive forbidden-field scanning
- `extra="forbid"` on all models (including `ValidationResult`)

## Nicht geändert

- No Issue #19 executor
- No n8n/Paperclip
- No API layer
- No dashboard
- No GitHub Actions
- No active validation

## Offene Punkte

- Compliance-Agent: PASS_WITH_NOTES
- Review-Agent: 2 findings addressed, 1 (target strictness) is by-design per ADR

## Nächster sinnvoller Schritt

Issue #19: Validation-Recipe-Executor implementieren.

- Consumer of this schema
- Must integrate with ActiveValidationGate (#14)
- Must use ScopeGuard for target authorization
- Must require Human Approval

## Decision Manifest

### GREEN_SAFE

- Schema models with fail-closed validation
- Recursive forbidden-field detection
- Conservative target classification
- 113 deterministic tests

### YELLOW_REVIEW

- `fixture:` / `lab:` placeholders are valid per ADR but extend beyond pure loopback (by design)
- Pydantic parse errors collapse to `INVALID_MODEL_PARSE` while preserving the specific message

### RED_BLOCK

- No executor, no execution, no real targets — intentionally not built

### TOOL_GAP / UNKNOWN

- None

## Acceptance Criteria

- [x] Report file created at `docs/roadmap/NEUTRINO_PHASE_2_ISSUE_18_REPORT.md`
- [x] Issue #18 implementation summarized from verified source files
- [x] Key ADR / safety decisions documented
- [x] Security findings and mitigations documented
- [x] Test coverage breakdown included
- [x] Handoff to Issue #19 documented
