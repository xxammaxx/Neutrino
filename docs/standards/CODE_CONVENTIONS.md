# Code Conventions — Neutrino

> Version: 1.0.0
> Erstellt: 2026-07-05
> Status: ACCEPTED — bindend fuer alle Neutrino-Core-Commits
> Scope: Neutrino Core (Phase 1+). n8n Bridge und Paperclip folgen spaeter eigenen Konventionen.

---

## 1. Sprache

| Entscheidung | Wert |
|-------------|------|
| Sprache | Python 3.11+ |
| Begruendung | Breite n8n-Kompatibilitaet, native `Self`-Type, `StrEnum`, `ExceptionGroup`, verbesserte Error-Messages |
| Minimum | `>=3.11` |
| Ziel | `~3.12` (sobald Dependencies es erlauben) |
| Verboten | Python 3.10 und aelter |

---

## 2. Package-Manager

| Entscheidung | Wert |
|-------------|------|
| Primary | `uv` (astral-sh/uv) |
| Alternative | `poetry` |
| Status | **YELLOW_REVIEW** — Owner-Entscheidung ausstehend zwischen `uv` und `poetry` |
| Praeferenz | `uv` (schneller Resolver, kompatibel mit pip-Workflow, kein Lockfile-Zwang) |

### `uv`-Setup (empfohlen)
```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,test]"
```

### `poetry`-Setup (Alternative)
```bash
poetry install --with dev,test
poetry shell
```

---

## 3. Linting & Formatting

| Tool | Zweck | Config |
|------|-------|--------|
| `ruff` | Linting (ersetzt flake8, isort, pyflakes, pylint) | `[tool.ruff]` in `pyproject.toml` |
| `ruff format` | Formatting (ersetzt black) | `[tool.ruff.format]` in `pyproject.toml` |
| `mypy` | Static Type Checking (strict mode) | `[tool.mypy]` in `pyproject.toml` |

### Ruff-Regeln (GREEN_SAFE)

- `E` / `W` — pycodestyle errors/warnings
- `F` — pyflakes
- `I` — isort (import sorting)
- `N` — pep8-naming
- `UP` — pyupgrade (modern Python syntax)
- `B` — flake8-bugbear
- `SIM` — flake8-simplify
- `TCH` — flake8-type-checking (TYPE_CHECKING imports)

### Ruff-Regeln (spaeter)
- `S` — flake8-bandit (Security-Linting, manuelle Pruefung noetig)
- `ANN` — flake8-annotations (zu strikt fuer fruehe Phase)

---

## 4. Type Hints

| Regel | Wert |
|-------|------|
| Modus | `mypy --strict` |
| Pflicht | Jede oeffentliche Funktion/Methode muss type hints haben |
| Optional | Private Hilfsfunktionen (duerfen, muessen aber nicht) |
| `Any` | verboten ausser bei expliziter Begruendung mit `# type: ignore[no-any-explicit]` |

### Beispiel
```python
from typing import Optional

def parse_policy(url: str, timeout: int = 30) -> Optional["ScopePolicy"]:
    """Parses a bug bounty policy page.

    Args:
        url: The URL of the policy page.
        timeout: Request timeout in seconds.

    Returns:
        Parsed ScopePolicy or None if unreachable.
    """
    ...
```

---

## 5. Testing

| Tool | Zweck |
|------|-------|
| `pytest` | Test-Framework |
| `pytest-cov` | Coverage-Reporting |
| `pytest-mock` | Mocking (fuer HTTP, Dateisystem) |
| `nox` | Multi-Python Test Runner |

### Regeln
- Test-Dateien in `tests/`, spiegeln `src/neutrino/`-Struktur
- Naming: `test_<modulename>.py`
- Jedes neue Modul braucht **mindestens eine Test-Datei**
- Coverage-Schwellwert: **80%** (GREEN_SAFE Minimum) — wird spaeter auf 90% erhoeht
- Tests duerfen **niemals** reale externe Ziele kontaktieren
- HTTP-Tests verwenden `pytest-mock` oder `responses`
- Keine `sleep()`-basierten Tests — Timeouts mocken

### Ausfuehrung
```bash
nox           # Alle unterstuetzten Python-Versionen
nox -s test   # Nur Tests
nox -s lint   # Nur Linting
```

---

## 6. Projektstruktur

```text
Neutrino/
  src/
    neutrino/
      __init__.py
      models/           # Datenmodelle (ScopePolicy, AuditEvent, etc.)
        __init__.py
      policy/           # Policy-Parser-Logik
        __init__.py
      scope/            # ScopeGuard
        __init__.py
      approval/         # Human Approval Workflow
        __init__.py
      audit/            # Audit Trail
        __init__.py
      evidence/         # Evidence Collection
        __init__.py
  tests/
    __init__.py
    policy/
      __init__.py
    scope/
      __init__.py
    ...
  docs/
    architecture/
    governance/
    roadmap/
    specs/
    standards/
  .github/
    ISSUE_TEMPLATE/
    PULL_REQUEST_TEMPLATE.md
  .gitignore
  .pre-commit-config.yaml
  CONTRIBUTING.md
  LICENSE (tbd)
  noxfile.py
  pyproject.toml
  README.md
  SECURITY.md
```

### Package-Regeln
- `src/`-Layout (kein Flat-Layout) — verhindert Import-Confusion
- Keine zirkulaeren Imports
- `__init__.py` exportiert nur oeffentliche API-Symbole
- Interne Module mit `_` prefix (z.B. `_internal.py`)

---

## 7. Commit-Konventionen

Format: [Conventional Commits](https://www.conventionalcommits.org/) mit Scope-Praefix.

### Erlaubte Typen
| Typ | Beschreibung |
|-----|-------------|
| `feat(scope):` | Neues Feature |
| `fix(scope):` | Bugfix |
| `docs(scope):` | Nur Dokumentation |
| `test(scope):` | Nur Tests |
| `chore(scope):` | Build, CI, Tooling |
| `refactor(scope):` | Refactoring (kein Verhalten geaendert) |

### Erlaubte Scopes
| Scope | Komponente |
|-------|-----------|
| `neutrino` | Neutrino Core |
| `policy` | Policy-Parser |
| `scope-guard` | ScopeGuard |
| `approval` | Human Approval |
| `audit` | Audit Trail |
| `evidence` | Evidence Collection |
| `templates` | GitHub Templates |
| `standards` | Code-Konventionen, Docs |
| `build` | Build-System, Dependencies |

### Beispiele
```
feat(neutrino): add policy parser foundation (#1)
fix(scope-guard): resolve false-positive redirect detection (#42)
docs(standards): update testing conventions
chore(build): pin ruff to 0.5.x
```

### Safety Rule
- Jeder Commit MUSS auf ein GitHub Issue verweisen (`#<number>`)

---

## 8. Pre-commit Hooks

Definiert in `.pre-commit-config.yaml`:

| Hook | Stage | Beschreibung |
|------|-------|-------------|
| `ruff` | pre-commit | Linting |
| `ruff format` | pre-commit | Formatting |
| `mypy` | pre-commit | Type Checking (nur geaenderte Files) |
| `check-yaml` | pre-commit | YAML-Validierung |
| `check-toml` | pre-commit | TOML-Validierung |
| `check-json` | pre-commit | JSON-Validierung |
| `check-added-large-files` | pre-commit | Blockiert grosse Commits |
| `detect-private-key` | pre-commit | Blockiert Secrets |
| `no-commit-to-branch` | pre-commit | Blockiert Commits auf `main` |

Installation:
```bash
pre-commit install
pre-commit run --all-files  # Erstmalig
```

---

## 9. Lokaler Build-Standard

### Quickstart
```bash
# 1. Clone & venv
git clone git@github.com:xxammaxx/Neutrino.git
cd Neutrino
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Dependencies
pip install -e ".[dev,test]"

# 3. Pre-commit
pre-commit install

# 4. Verify
nox
```

### Nox Sessions
| Session | Befehl | Beschreibung |
|---------|--------|-------------|
| `test` | `nox -s test` | pytest mit Coverage |
| `lint` | `nox -s lint` | ruff check + ruff format --check + mypy |
| `typecheck` | `nox -s typecheck` | Nur mypy |
| `format` | `nox -s format` | ruff format (auto-fix) |

### Manuelle Befehle (ohne nox)
```bash
ruff check src/ tests/          # Linting
ruff format src/ tests/          # Formatting
mypy src/                        # Type Check
pytest tests/ -v --cov=src --cov-report=term  # Tests
```

---

## 10. Sicherheitsrelevante Konventionen

- **Keine Secrets in Code oder Config:** API-Keys, Tokens, Passwoerter nur ueber Umgebungsvariablen oder `.env` (nicht committet)
- **Keine Shell-Ausfuehrung in Produktionscode:** `subprocess.run()` nur in Lab-Kontext
- **Netzwerk-Requests nur ueber `neutrino.scope.guard`:** Kein direkter `requests.get()` ohne Scope-Pruefung
- **Keine `eval()` oder `exec()`** in Produktionscode
- **Dependencies pinnen:** `pyproject.toml` mit Pin-Constraints, `uv.lock` oder `poetry.lock` im Repo
- **Supply-Chain:** Keine Dependencies von nicht-verifizierten Quellen

---

## 11. Version-Historie

| Datum | Version | Autor | Aenderung |
|-------|---------|-------|-----------|
| 2026-07-05 | 1.0.0 | Issue Orchestrator | Initiale Konventionen |
