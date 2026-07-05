# Neutrino Phase 1 — Issue #5 ScopeGuard Report

## Kurzfazit

**GREEN**

ScopeGuard wurde als lokale, deterministische Request-Gating-Komponente
implementiert. Alle 4 Akzeptanzkriterien sind erfullt. 87/87 Tests grun,
0 ruff warnings, 0 mypy errors, 97% Coverage. Keine Netzwerkrequests,
keine DNS-Auflosung, keine Overrides.

---

## Reality Refresh

| Check | Ergebnis |
|-------|---------|
| Default Branch | `main` |
| HEAD (vorher) | `709043e` — docs: add Phase 1 Issue #2 Report |
| HEAD (nachher) | `cc2408b` — feat(neutrino): add ScopeGuard deterministic request-gating (#5) |
| Git Status | Clean |
| Issue #2 Status | CLOSED (GREEN_SAFE) |
| Issue #5 Status | OPEN → wird geschlossen |
| PRs offen | Keine |
| Vorhandene scopeguard-Module | Keine (alles neu) |

---

## Geanderte Dateien

| Datei | Aktion | Zeilen |
|-------|--------|--------|
| `src/neutrino/scopeguard/__init__.py` | neu | 17 |
| `src/neutrino/scopeguard/models.py` | neu | 81 |
| `src/neutrino/scopeguard/guard.py` | neu | 289 |
| `tests/scopeguard/__init__.py` | neu | 0 |
| `tests/scopeguard/test_guard.py` | neu | 489 |

**Keine bestehenden Dateien modifiziert.** Der Parser, das ScopePolicy-Modell
und alle bestehenden Tests blieben unverandert.

---

## ScopeGuard-Design

### Architektur

```text
Request Intent / Target + ScopePolicy → ScopeGuard.check_target() → ScopeDecision
```

ScopeGuard ist die letzte Instanz vor jeder potenziellen Netzwerkaktion.
Er fuhrt die Aktion nicht aus — er entscheidet nur.

### Entscheidungsbaum

```text
check_target(target, policy)
  │
  ├── policy is None? → DENY_MISSING_POLICY
  │
  ├── target valid & normalized?
  │     ├── Empty/whitespace → DENY_INVALID_TARGET
  │     ├── Too long (>2048 chars) → DENY_INVALID_TARGET
  │     ├── Null bytes → DENY_INVALID_TARGET
  │     ├── Unsafe scheme (ftp, file, http, ...) → DENY_UNSAFE_SCHEME
  │     └── OK → scheme extracted, target normalized
  │
  ├── Out-of-Scope match? → DENY_OUT_OF_SCOPE
  │     (checked FIRST — explicit exclusion always wins)
  │
  ├── In-Scope match? → ALLOW_IN_SCOPE
  │     (only reached if no out-of-scope match)
  │
  └── No match → DENY_UNKNOWN_TARGET (Default Deny)
```

### Normalisierung (lokal, deterministisch)

```
https://Example.COM/v1/status/ → example.com/v1/status
```

Schritte:
1. Whitespace stripping
2. Lowercase
3. Scheme-Extraktion (https, http, ftp, ...)
4. Trailing slash entfernen
5. Host-Extraktion fur Domain-Matching
6. Path-Erhaltung fur API/URL-Matching

**Nicht durchgefuhrt:**
- DNS-Auflosung
- Redirect-Verfolgung
- CNAME-Prufung
- IR-/WHOIS-Lookups
- Jegliche Netzwerk-I/O

### Matching

| Entry-Typ | Matching-Methode |
|-----------|-----------------|
| `domain` | `ScopeEntry.matches(host)` — exakt, subdomain, wildcard |
| `wildcard_domain` | `ScopeEntry.matches(host)` — single-level wildcard |
| `ip_range` | `ipaddress.ip_network(cidr)` — CIDR-Bereich |
| `url` | `ScopeEntry.matches(normalized)` — mit Path |
| `api` | `ScopeEntry.matches(normalized)` — mit Path |

---

## Decision-Modell

### ScopeDecisionStatus (StrEnum)

| Wert | Bedeutung |
|------|-----------|
| `ALLOW` | Target darf kontaktiert werden. |
| `DENY` | Target ist blockiert. Nicht uberschreibbar. |

Nur zwei Zustande. Kein UNKNOWN — wenn keine Bestimmung moglich: DENY.

### ScopeReason (StrEnum)

| Code | Bedeutung |
|------|-----------|
| `ALLOW_IN_SCOPE` | Target matcht einen in-scope Eintrag und ist nicht out-of-scope. |
| `DENY_OUT_OF_SCOPE` | Target matcht einen out-of-scope Eintrag. |
| `DENY_UNKNOWN_TARGET` | Target matcht keinen in-scope Eintrag (Default Deny). |
| `DENY_INVALID_TARGET` | Target ist leer, zu lang oder enthalt Null-Bytes. |
| `DENY_UNSAFE_SCHEME` | Target verwendet ein blockiertes URL-Schema. |
| `DENY_MISSING_POLICY` | Es wurde keine ScopePolicy ubergeben. |

### ScopeDecision (BaseModel)

Serialisierbares Pydantic-Modell mit:
- `target` — originaler Target-String
- `status` — ALLOW oder DENY
- `reason` — deterministischer Reason-Code
- `matched_entry` — Pattern des gematchten ScopeEntry (oder None)
- `policy_source` — Quell-URL der Policy
- `explanation` — menschenlesbare Erklarung

Properties:
- `is_allowed` → True wenn ALLOW
- `is_denied` → True wenn DENY

---

## Tests

### Testanzahl

| Kategorie | Tests |
|-----------|-------|
| Bestehend (Parser) | 42 |
| Neu (ScopeGuard) | 45 |
| **Gesamt** | **87** |

### Test-Kategorien (ScopeGuard)

| Kategorie | Anzahl | Beispiele |
|-----------|--------|-----------|
| ALLOW — in-scope | 8 | Exact domain, wildcard, HTTPS URL, IP range, API path, subdomain |
| DENY — out-of-scope | 3 | Exact, wildcard override, wildcard subdomain |
| DENY — unknown | 3 | Unknown domain, deep wildcard, similar-but-different |
| DENY — invalid target | 4 | Empty, whitespace, too long, null byte |
| DENY — unsafe scheme | 5 | FTP, HTTP, file, javascript, data |
| DENY — missing policy | 2 | None policy with domain, None policy with URL |
| Normalisierung | 4 | Trailing slash, mixed case, whitespace, path |
| IP range edge cases | 4 | Outside range, network addr, broadcast, invalid IP |
| Serialisierung | 3 | model_dump, deny dump, JSON roundtrip |
| Immutability | 2 | No override, no kwargs |
| Explanations | 2 | Content check, scheme mention |
| Integration | 3 | OOS-before-IS order, complex policy, policy_source |

### Safety-Verifikation

- [x] Keine echten Targets kontaktiert
- [x] Keine DNS-Auflosung
- [x] Keine HTTP-Requests
- [x] Alle Tests nutzen lokale Fixtures
- [x] Keine Redirect-/CNAME-Prufung
- [x] Kein Scanner oder aktive Validierung

---

## Lokale Gates

### Vorher (Pre-Change)

| Gate | Ergebnis |
|------|---------|
| `pytest tests/ -v` | 42/42 passed, 96% Coverage |
| `python3 -m compileall src/` | OK |
| `ruff check .` | All checks passed (0 warnings) |
| `mypy src/neutrino/ --strict` | Success, 0 errors (5 files) |

### Nachher (Post-Change)

| Gate | Ergebnis |
|------|---------|
| `pytest tests/ -v` | 87/87 passed, 97% Coverage |
| `python3 -m compileall src/` | OK |
| `ruff check .` | All checks passed (0 warnings) |
| `mypy src/neutrino/ --strict` | Success, 0 errors (8 files) |

---

## Safety Check

| Regel | Status |
|-------|--------|
| Default Deny | Implementiert — UNKNOWN = DENY |
| Out-of-Scope schlagt In-Scope | Implementiert — OOS wird zuerst gepruft |
| DENY nicht uberschreibbar | Implementiert — keine Override-Flags, keine force-Parameter |
| Deterministisch | Implementiert — kein LLM, kein Netzwerk, reine Regex/CIDR-Logik |
| AuditLog vorbereitet | ScopeDecision ist serialisierbar fur zukunftigen AuditLog (#12) |
| Kein Netzwerk | scopeGuard macht keine Netzwerkrequests |
| Keine DNS-Auflosung | Nicht implementiert |
| Keine Redirect/CNAME | Nicht implementiert → Issue #6 |

---

## Nicht geandert

- `src/neutrino/models/policy.py` — unverandert
- `src/neutrino/policy/parser.py` — unverandert
- `tests/policy/test_parser.py` — unverandert
- `pyproject.toml` — unverandert
- Keine neuen Dependencies
- Keine Package-Manager-Migration

---

## Offene Punkte

| Punkt | Issue | Status |
|-------|-------|--------|
| Redirect- und CNAME-Prufung | #6 | Nicht in diesem Lauf — separates Issue |
| AuditLog JSONL-Writer | #12 | ScopeDecision ist serialisierbar — AuditLog folgt |
| Out-of-Scope Regression-Tests | #42 | Separater QA-Lauf |
| Redirect/CNAME Regression-Tests | #43 | Separater QA-Lauf |
| Human Authorization Workflow | #4 | Separates Issue |
| Code Coverage: Line 193 (guard.py) | TOOL_GAP | `return None, None` in `_validate_and_normalize`: Pfad "strip scheme+slash → empty" wird von `test_whitespace_only_target_denies` nicht erreicht — whitespace-only führt zu fruherem `return None` |

---

## Nachster empfohlener Schritt

**Issue #6: Redirect- und CNAME-Prufung implementieren**

Nachdem ScopeGuard jetzt deterministisch uber In-Scope/Out-of-Scope/Unknown
entscheidet, ist der nachste logische Schritt die Erweiterung um
Redirect- und CNAME-Prufung (separates Issue, da es Netzwerk-I/O involviert).

---

## Decision Manifest

### GREEN_SAFE

- ScopeGuard-Modul (`src/neutrino/scopeguard/`)
- Decision-Modell (`ScopeDecision`, `ScopeDecisionStatus`, `ScopeReason`)
- `ScopeGuard.check_target()` mit vollstandigem Entscheidungsbaum
- Lokale URL-/Target-Normalisierung
- IP-Range-Matching via `ipaddress`
- 45 Unit-Tests mit lokalen Fixtures
- Alle Gates grun (pytest, ruff, mypy, compileall)

### YELLOW_REVIEW

- HTTP wird als UNSAFE_SCHEME geblockt (nur HTTPS erlaubt). Sollte in Zukunft
  ggf. als konfigurierbar oder mit expliziter Warning behandelt werden.

### RED_BLOCK

- Keine — alle harten Verbote wurden eingehalten.

### TOOL_GAP / UNKNOWN

- Eine Coverage-Lucke in `_validate_and_normalize` (Line 193): Pfad
  "strip scheme + trailing slash → empty string" wird nicht direkt getestet.
  Nicht kritisch — der leere String wird bereits fruher abgefangen.
- `nox` wurde nicht ausgefuhrt (in venv nicht verfugbar) — aber
  pytest/ruff/mypy/compileall decken die relevanten Checks ab.
