# Neutrino Phase 1 — Issue #6 Redirect/CNAME Report

## Kurzfazit

**GREEN**

Redirect- und CNAME-Evasion-Prävention wurde als lokale, deterministische Schicht
implementiert. Alle 4 Akzeptanzkriterien sind erfullt. 123/123 Tests grun (36 neue),
ruff clean, mypy clean, 97% Coverage. Keine echten DNS- oder HTTP-Requests.
Keine Override-Pfade. Keine Remote-CI aktiviert.

---

## Reality Refresh

| Check | Ergebnis |
|-------|---------|
| Default Branch | `main` |
| HEAD (vorher) | `e4b4048` — docs: add Phase 1 Issue #5 ScopeGuard Report |
| HEAD (nachher) | `4b2cd47` — feat(neutrino): add Redirect- und CNAME-Prüfung (#6) |
| Git Status | Clean |
| Issue #5 Status | CLOSED (GREEN_SAFE) |
| Issue #6 Status | OPEN → wird geschlossen |
| PRs offen | Keine |
| Vorhandene redirect/dns/cname-Module | Keine (alles neu) |
| .github/workflows/ | Existiert nicht |

---

## Geanderte Dateien

| Datei | Aktion | Zeilen |
|-------|--------|--------|
| `src/neutrino/scopeguard/models.py` | erweitert | +71 (ScopeReason + DnsTrace, RedirectTrace, EvasionResult) |
| `src/neutrino/scopeguard/dns.py` | neu | 207 |
| `src/neutrino/scopeguard/redirects.py` | neu | 124 |
| `src/neutrino/scopeguard/evasion.py` | neu | 97 |
| `src/neutrino/scopeguard/__init__.py` | erweitert | +26 |
| `tests/scopeguard/test_redirect_cname.py` | neu | 688 |

**Keine bestehenden Tests oder Produktivmodule modifiziert.**
ScopeGuard (`guard.py`) und `policy.py` blieben unverandert.
Der Parser und alle bestehenden Tests funktionieren unverandert (87/87).

---

## Redirect-Design

### Architektur

```text
RedirectChain (List[RedirectHop]) + ScopePolicy → check_redirect_chain() → (traces, reason|None)
```

### RedirectHop (Datenmodell)

```python
RedirectHop(from_url="https://app.example.com", to_url="https://api.example.com", status_code=302)
```

### Entscheidungsbaum

```text
check_redirect_chain(initial_target, chain, policy)
  │
  ├── chain length > max_hops (5) → DENY_REDIRECT_LIMIT_EXCEEDED
  │
  ├── initial_target check via ScopeGuard
  │     └── DENY? → return reason, no redirect traces
  │
  └── for each hop:
        ├── to_url empty/whitespace → DENY_INVALID_REDIRECT
        ├── ScopeGuard.check_target(to_url)
        │     ├── DENY_OUT_OF_SCOPE → DENY_REDIRECT_OUT_OF_SCOPE
        │     ├── DENY_UNKNOWN_TARGET → DENY_REDIRECT_UNKNOWN
        │     ├── DENY_UNSAFE_SCHEME → DENY_INVALID_REDIRECT
        │     └── ALLOW → continue to next hop
        └── all hops ALLOW → return (traces, None)
```

### Features

- Jeder Redirect-Hop wird eigenstandig gegen ScopePolicy gepruft
- Unsafe Schemes (http, ftp, file, ...) werden bei jedem Hop blockiert
- Hop-Limit (default: 5) mit klarem DENY_REDIRECT_LIMIT_EXCEEDED
- Ungultige/leere Location-Header → DENY_INVALID_REDIRECT
- Kein Override-Pfad (kein force, ignore_scope, etc.)

---

## CNAME-/DNS-Design

### Architektur

```text
CnameResolver (interface) → FakeCnameResolver (test impl)
  │
  └── check_cname_chain(initial_target, policy, resolver=resolver) → (traces, reason|None)
```

### CnameResolver Interface

```python
class CnameResolver(ABC):
    @abstractmethod
    def resolve_cname(self, name: str) -> list[str] | None: ...
```

### FakeCnameResolver

Deterministischer Resolver mit statischem Mapping:

```python
resolver = FakeCnameResolver({"sub.example.com": ["target.example.net"]})
```

### Entscheidungsbaum

```text
check_cname_chain(initial_target, policy, resolver)
  │
  ├── initial_target via ScopeGuard → DENY? → return reason
  │
  └── for hop in range(max_hops=10):
        ├── resolver.resolve_cname(current) → None → chain ends (no CNAME, ok)
        ├── resolver.resolve_cname(current) → [] → DENY_DNS_UNKNOWN
        ├── answer in seen set → DENY_CNAME_LOOP
        ├── ScopeGuard.check_target(answer)
        │     ├── DENY_OUT_OF_SCOPE → DENY_CNAME_OUT_OF_SCOPE
        │     ├── DENY_UNKNOWN → DENY_CNAME_UNKNOWN
        │     └── ALLOW → continue to next hop
        └── all hops ok, no more CNAMEs → return (traces, None)

  └── hop limit exceeded → DENY_CNAME_LIMIT_EXCEEDED
```

### Features

- Jeder CNAME-Hop wird eigenstandig gegen ScopePolicy gepruft
- CNAME-Ziele erben NICHT die Wildcard-Berechtigung des Ursprungs
- Loop-Erkennung (via seen-Set) → DENY_CNAME_LOOP
- Hop-Limit (default: 10) → DENY_CNAME_LIMIT_EXCEEDED
- Leere CNAME-Antwort → DENY_DNS_UNKNOWN
- Keine rekursive DNS-Auflosung ohne Limit

---

## Decision-Modell

### Neue ScopeReason-Werte (Issue #6)

| Code | Bedeutung |
|------|-----------|
| `DENY_REDIRECT_OUT_OF_SCOPE` | Redirect-Ziel ist explizit out-of-scope |
| `DENY_REDIRECT_UNKNOWN` | Redirect-Ziel ist unbekannt (Default Deny) |
| `DENY_REDIRECT_LIMIT_EXCEEDED` | Redirect-Kette uberschreitet Hop-Limit |
| `DENY_INVALID_REDIRECT` | Ungultiger/leerer Redirect-Location-Header |
| `DENY_CNAME_OUT_OF_SCOPE` | CNAME-Ziel ist explizit out-of-scope |
| `DENY_CNAME_UNKNOWN` | CNAME-Ziel ist unbekannt (Default Deny) |
| `DENY_CNAME_LIMIT_EXCEEDED` | CNAME-Kette uberschreitet Hop-Limit |
| `DENY_CNAME_LOOP` | Zirkulare CNAME-Referenz erkannt |
| `DENY_DNS_UNKNOWN` | DNS-Resolver lieferte keine verwertbare Antwort |

### Neue Modelle

| Modell | Zweck |
|--------|-------|
| `DnsTrace` | Serialisierbare DNS/CNAME-Auflosungsaufzeichnung (queried_name, record_type, answers, source, decision) |
| `RedirectTrace` | Serialisierbare Redirect-Hop-Aufzeichnung (from_url, to_url, status_code, decision) |
| `EvasionResult` | Kombiniertes Ergebnis aus ScopeGuard + Redirect + CNAME (initial_decision, redirect_traces, dns_traces, final_decision, final_reason) |

---

## Trace-/Logging-Modell

### DnsTrace

```python
DnsTrace(
    queried_name="app.example.com",
    record_type="CNAME",
    answers=["cdn.trusted.net"],
    source="fake_resolver",
    decision="allow_in_scope",
)
```

- Serialisierbar via `model_dump()` / `model_dump_json()`
- JSON-Roundtrip-fahig
- Kein persistentes AuditLog geschrieben (separates Issue #12)

### RedirectTrace

```python
RedirectTrace(
    from_url="https://app.example.com",
    to_url="https://evil.example.net",
    status_code=302,
    decision="deny_redirect_out_of_scope",
)
```

### EvasionResult

Kombiniert alle Traces in einem serialisierbaren Ergebnis:

```python
EvasionResult(
    initial_target="app.example.com",
    initial_decision=ScopeDecision(...),
    redirect_traces=[...],
    dns_traces=[...],
    final_decision=ALLOW | DENY,
    final_reason=ScopeReason,
    explanation="...",
)
```

---

## Tests

### Testanzahl

| Kategorie | Tests |
|-----------|-------|
| Bestehend (Parser + ScopeGuard) | 87 |
| Neu (Issue #6) | 36 |
| **Gesamt** | **123** |

### Test-Kategorien (Issue #6)

| Kategorie | Anzahl | Beschreibung |
|-----------|--------|-------------|
| Redirect Basic | 10 | In-scope, out-of-scope, unknown, multi-hop, hop-limit, empty location, whitespace-only, unsafe scheme, independent scope, initial deny |
| Redirect Safety | 2 | No override kwargs, evil mid-chain blocks everything |
| CNAME Basic | 7 | In-scope chain, out-of-scope, unknown, hop-limit, loop, empty answer, no CNAME |
| CNAME Wildcard | 3 | Single-level wildcard, deep mismatch, no inheritance |
| CNAME Safety | 2 | No override kwargs, initial deny blocks CNAME |
| DNS Trace | 4 | DnsTrace serialization, JSON roundtrip, RedirectTrace serialization, EvasionResult serialization |
| Evasion Orchestration | 5 | Pure allow, redirect block, CNAME block, combined both, no persistent audit |
| No Real Network | 3 | dns.py no network imports, redirects.py no httpx.get, FakeResolver static dict |

### Safety-Verifikation

- [x] Keine echten DNS-Requests
- [x] Keine echten HTTP-Requests
- [x] Kein `httpx.get()` oder realer Redirect-Follow
- [x] Alle Tests nutzen lokale Fixtures und FakeResolver
- [x] Kein Override-Pfad fur DENY
- [x] Keine persistente AuditLog-Infrastruktur
- [x] Keine GitHub Actions / Remote-CI

---

## Lokale Gates

### Vorher (Pre-Change)

| Gate | Ergebnis |
|------|---------|
| `pytest tests/ -v` | 87/87 passed, 97% Coverage |
| `compileall src/` | OK |
| `ruff check .` | All checks passed (0 warnings) |
| `mypy src/neutrino/ --strict` | Success, 0 errors (8 files) |

### Nachher (Post-Change)

| Gate | Ergebnis |
|------|---------|
| `pytest tests/ -v` | 123/123 passed, 97% Coverage |
| `compileall src/` | OK |
| `ruff check .` | All checks passed (0 warnings) |
| `mypy src/neutrino/ --strict` | Success, 0 errors (11 files) |

---

## Safety Check

| Regel | Status |
|-------|--------|
| Default Deny | Implementiert — UNKNOWN = DENY auf allen Ebenen |
| Redirect-Evasion blockiert | Jeder Hop wird gegen ScopePolicy gepruft |
| CNAME-Evasion blockiert | Jeder CNAME-Hop wird gepruft |
| Wildcards konservativ | Single-level wildcard, keine Vererbung |
| Hop-Limits | Redirect: 5, CNAME: 10 |
| Loop-Erkennung | CNAME-Loops → DENY_CNAME_LOOP |
| DENY nicht uberschreibbar | Keine Override-Flags in check_redirect_chain oder check_cname_chain |
| Deterministisch | FakeResolver statisch, RedirectHop als Datenstruktur |
| Kein Netzwerk | Keine echten DNS/HTTP-Requests |
| Traces serialisierbar | DnsTrace, RedirectTrace, EvasionResult via Pydantic |

---

## Nicht geandert

- `src/neutrino/scopeguard/guard.py` — unverandert
- `src/neutrino/models/policy.py` — unverandert
- `src/neutrino/policy/parser.py` — unverandert
- `tests/policy/test_parser.py` — unverandert
- `tests/scopeguard/test_guard.py` — unverandert
- `pyproject.toml` — unverandert
- Keine neuen Dependencies
- Keine Package-Manager-Migration

---

## Offene Punkte

| Punkt | Issue | Status |
|-------|-------|--------|
| Rate-Limit Enforcement | #7 | Nicht in diesem Lauf |
| AuditLog JSONL-Writer | #12 | Traces sind serialisierbar — AuditLog folgt |
| Human Authorization Workflow | #4 | Separates Issue |
| Redirect/CNAME Regression-Tests | #43 | Separater QA-Lauf |
| ScopeGuard Regression-Tests | #42 | Separater QA-Lauf |
| Coverage-Lucke guard.py:193 | TOOL_GAP | Bestehend aus Issue #5, nicht adressiert |

---

## Nachster empfohlener Schritt

**Issue #7: Rate-Limit Enforcement implementieren**

Nachdem ScopeGuard (#5) und Redirect/CNAME-Evasion-Prevention (#6) jetzt
deterministisch sind, ist der nachste logische Schritt die Implementierung
von Rate-Limit-Enforcement.

---

## Decision Manifest

### GREEN_SAFE

- Redirect-Prufmodul (`src/neutrino/scopeguard/redirects.py`)
- CNAME/DNS-Prufmodul (`src/neutrino/scopeguard/dns.py`)
- Evasion-Orchestrierung (`src/neutrino/scopeguard/evasion.py`)
- Erweiterte Reason-Codes (9 neue ScopeReason-Werte)
- Neue Datenmodelle (DnsTrace, RedirectTrace, EvasionResult)
- FakeCnameResolver-Interface (keine echten DNS-Requests)
- 36 Unit-Tests mit lokalen Fixtures
- Alle Gates grun (pytest, ruff, mypy, compileall)

### YELLOW_REVIEW

- Keine — alle Anderungen sind GREEN_SAFE.

### RED_BLOCK

- Keine — alle harten Verbote wurden eingehalten.

### TOOL_GAP / UNKNOWN

- Coverage-Lucke in `guard.py` Line 193 (aus Issue #5)
- `nox` wurde nicht ausgefuhrt (in venv nicht verfugbar) — aber
  pytest/ruff/mypy/compileall decken die relevanten Checks ab.
- `_REDIRECT_STATUS_CODES` ist definiert aber nicht aktiv genutzt im
  decision-flow (nur Datenstruktur). Kann spater fur HTTP-Client-
  Integration verwendet werden.
