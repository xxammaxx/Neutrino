# Neutrino / n8n / Paperclip Target Architecture

> Version: 1.0.0
> Erstellt: 2026-07-04
> Status: ACCEPTED
> Scope: Gesamtarchitektur des Neutrino-Ökosystems

---

## 1. Architekturübersicht

```text
┌──────────────────────────────────────────────────────────────┐
│                      PAPERCLIP                                │
│                 Agent Control Plane                           │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │  Roles   │  │ Tickets  │  │ Heartbeats│  │  Budgets   │  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │  Goals   │  │ Agent    │  │ Tool-Call │  │ Governance │  │
│  │Alignment │  │Instructions│ │  Tracing  │  │            │  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘  │
│                                                               │
│  Paperclip DARF: koordinieren, priorisieren, kommentieren,   │
│                  Reviews vorbereiten, Ziele setzen             │
│  Paperclip DARF NICHT: aktive Security-Tests ausführen        │
└───────────────────────────┬──────────────────────────────────┘
                            │ Aufgaben / Tickets / Heartbeats
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                         n8n                                   │
│              Deterministic Workflow Bridge                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │ Webhooks │  │Human-in- │  │    MCP    │  │ Status    │  │
│  │          │  │the-loop  │  │  Bridge   │  │ Pages     │  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │ Notifica │  │ GitHub   │  │ Dashboard │  │ Android   │  │
│  │ -tions   │  │ Integr.  │  │ Output    │  │ TV Output │  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘  │
│                                                               │
│  n8n DARF: Workflows starten, nur über sichere Neutrino-APIs │
│  n8n DARF NICHT: unkontrollierte aktive Security-Automation  │
└───────────────────────────┬──────────────────────────────────┘
                            │ erlaubte API-/MCP-Aufrufe
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                      NEUTRINO CORE                            │
│                  Safety & Truth Core                           │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │ Policy   │  │ Scope    │  │ Evidence  │  │ Audit     │  │
│  │ Parser   │  │ Guard    │  │ Oracle    │  │ Log       │  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │ Report   │  │ Default  │  │ Human     │  │ Scope     │  │
│  │ Quality  │  │ Deny     │  │ Approval  │  │ Policy    │  │
│  │ Gate     │  │          │  │ Gate      │  │ Model     │  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘  │
│                                                               │
│  Neutrino entscheidet: GREEN_SAFE / YELLOW_REVIEW /          │
│                        RED_BLOCK / UNKNOWN                    │
└───────────────────────────┬──────────────────────────────────┘
                            │ nur nach Freigabe
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                LOKALE LABS / REPORTS / DASHBOARD              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │Juice Shop│  │ WebGoat  │  │ Disclosure│  │  Status-  │  │
│  │ / DVWA   │  │          │  │ Drafts    │  │  Dashboard│  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘  │
│                                                               │
│  NUR lokale oder absichtlich verwundbare Lab-Ziele            │
│  KEINE realen Ziele ohne explizite Scope- und Human-Freigabe  │
│  KEINE automatische Report-Einreichung                        │
└──────────────────────────────────────────────────────────────┘
```

## 2. Schichten im Detail

### 2.1 Neutrino Core — Safety & Truth Core

Neutrino ist der **unbestechliche Sicherheitskern**. Es ist die einzige Instanz, die
Sicherheitsentscheidungen treffen darf.

**Kernmodule:**

| Modul | Funktion | Entscheidung |
|-------|----------|-------------|
| Policy Parser | Extrahiert Scope-Policies aus Bug-Bounty-Programmen | Strukturierte Daten |
| ScopePolicy Model | ScopePolicy-Datenmodell mit In/Out-Scope, Regeln | Datenmodell |
| ScopeGuard | Prüft jeden Netzwerk-Request gegen Scope | ALLOW / DENY |
| Default Deny | Blockiert alles, was nicht explizit erlaubt ist | DENY |
| Human Approval | Erzwingt menschliche Freigabe für aktive Aktionen | BLOCK until approved |
| AuditLog | Append-only Log aller Entscheidungen | Immutable |
| Evidence Oracle | Prüft Evidenz-Qualität und Reproduzierbarkeit | PASS / FAIL |
| Report Quality Gate | Blockiert Reports ohne Evidenz | BLOCK / ALLOW_DRAFT |

**Entscheidungsmodell:**

- `GREEN_SAFE` — sicher, foundational, direkt freigegeben
- `YELLOW_REVIEW` — braucht Owner-Entscheidung
- `RED_BLOCK` — blockiert, gefährlich, unklar
- `UNKNOWN` — nicht genug Informationen, konservativ blockieren

**Harte Regeln:**

1. Keine automatische aktive Security-Validierung gegen reale Ziele
2. Keine Credential-Angriffe
3. Keine Datenexfiltration
4. Keine freien Shell-Kommandos
5. Keine Exploit-Ausführung außerhalb Labs
6. Keine automatische Report-Einreichung
7. LLM-Ausgaben ersetzen niemals Scope/Evidence-Entscheidungen
8. UNKNOWN = Blockieren oder Review

### 2.2 n8n — Deterministic Workflow Bridge

n8n ist die **Prozess- und Integrationsschicht**. Es orchestriert Workflows deterministisch,
aber trifft keine Sicherheitsentscheidungen.

**Einsatzbereiche:**

| Bereich | Beschreibung |
|---------|-------------|
| Webhooks | Empfängt externe Trigger (GitHub, Paperclip, Dashboard) |
| Human-in-the-loop | Approval-Workflows mit menschlicher Bestätigung |
| MCP Bridge | Verbindet MCP-Clients/-Server sicher mit Neutrino |
| Status Pages | Zeigt System- und Workflow-Status |
| GitHub Integration | Synchronisiert Issues, Comments, Status |
| Dashboard Output | Bereitet Daten für Dashboard/Android-TV auf |
| Notifications | Benachrichtigungen bei Approval-Anfragen |

**Regeln für n8n:**

- Darf Workflows starten, aber NUR über sichere Neutrino-APIs
- Darf KEINE unkontrollierte aktive Security-Automation ausführen
- Jeder Workflow-Schritt, der Neutrino-APIs aufruft, muss durch Neutrino authorisiert werden
- MCP-Tools dürfen nur sichere, klar begrenzte Funktionen exportieren

### 2.3 Paperclip — Agent Control Plane

Paperclip ist der **Agenten-Leitstand**. Es koordiniert Agenten, verwaltet Tickets,
Ziele, Budgets und Governance.

**Einsatzbereiche:**

| Bereich | Beschreibung |
|---------|-------------|
| Agent Roles | Rollenbasierte Zugriffskontrolle für Agenten |
| Tickets | Issue-Tracking für Agenten-Aufgaben |
| Heartbeats | Liveness- und Status-Checks für Agenten |
| Budgets | Kostenkontrolle für Agenten-Aktionen |
| Goal Alignment | Ausrichtung der Agenten-Arbeit an Projektzielen |
| Agent Instructions | Verwaltung von Agent-Prompts und Anweisungen |
| Tool-Call Tracing | Nachverfolgung aller Agent-Tool-Aufrufe |
| Governance | Regeln, Richtlinien, Compliance |

**Regeln für Paperclip:**

- Agenten dürfen koordinieren, analysieren und Vorschläge machen
- Agenten dürfen KEINE direkten aktiven Tests gegen Ziele starten
- Keine freien Shell-Kommandos für Agenten
- Keine Credential-Angriffe durch Agenten
- Jede aktive Aktion eines Agenten muss durch Neutrino authorisiert werden

### 2.4 Lokale Labs / Reports / Dashboard

Die **Ausführungsschicht** für sichere, lokale Validierung und Reporting.

| Bereich | Beschreibung |
|---------|-------------|
| Juice Shop / WebGoat / DVWA | Lokale, absichtlich verwundbare Lab-Ziele |
| Validation Recipe Executor | Führt definierte Validierungsschritte aus |
| Disclosure Draft Generator | Erzeugt Report-Drafts (keine Submits) |
| Evidence Bundle Export | Exportiert Evidenz für manuelle Review |
| Status Dashboard | Zeigt Project- und Workflow-Status |

## 3. Kommunikationsflüsse

### 3.1 Erlaubte Kommunikation

```text
Paperclip → n8n:          Aufgaben, Tickets, Heartbeats
n8n → Neutrino:           API-Aufrufe über sichere Endpunkte
Neutrino → n8n:           Safety-Entscheidungen, Logs
n8n → Dashboard:          Status-Daten
Neutrino → Labs:          Freigegebene Validierungsschritte
Labs → Neutrino:          Evidence, Logs, Ergebnisse
```

### 3.2 Verbotene Kommunikation

```text
Paperclip → Labs:         DIREKTE Test-Ausführung (muss über n8n+Neutrino)
n8n → Externe Ziele:      OHNE Neutrino-ScopeGuard
Agent → Internet:         OHNE Scope-Prüfung
n8n → Bug-Bounty-Plattform: DIREKTE Report-Einreichung
```

### 3.3 MCP-Grenzen

```text
MCP-Server (n8n-hosted) exportiert NUR:
  - neutrino.scope_check(target)
  - neutrino.policy_parse(url)
  - neutrino.audit_query(filter)
  - neutrino.evidence_export(bundle_id)

MCP-Server exportiert NIEMALS:
  - neutrino.bypass_scope(*)
  - neutrino.execute_exploit(*)
  - neutrino.submit_report(*)
  - Shell/Bash-Kommandos
```

## 4. Ziel-Roadmap

Die Entwicklung folgt dieser strikten Reihenfolge:

### Phase 0 — Repository Foundation & Governance
- README, SECURITY.md, CONTRIBUTING.md
- Architekturübersicht (dieses Dokument)
- Safety Policy / Decision Manifest
- Issue-/PR-Templates
- Labels und Milestones
- Klare Aussage: Keine aktiven Security-Aktionen ohne Gates
- Lokale Entwicklungsanleitung

### Phase 1 — Neutrino Safety Core
- Policy Parser Grundstruktur
- ScopePolicy-Modell, In/Out-Scope-Extraktion
- Rate-Limit-/Automation-Regeln
- ScopeGuard mit Default-Deny
- Human Authorization Workflow
- AuditLog (JSONL, Append-only)
- Evidence Oracle Mindestprüfungen
- Report Quality Gate

### Phase 2 — Deterministic Storage & Evidence
- SQLite-Schema und Migrationen
- CRUD-Repositories für alle Core-Entities
- Evidence Bundles
- Audit-Auszüge
- Redigierte Logs
- Reproduzierbare Evidence-Prüfungen

### Phase 3 — n8n Workflow Bridge
- n8n Webhooks
- Human-in-the-loop Approval-Workflows
- Sichere Workflow-Gates
- Neutrino API-Aufrufe
- MCP Client/Server Bridge
- Statusseiten
- GitHub-Issue-Integration
- Android-TV-/Dashboard-Output

### Phase 4 — Paperclip Control Plane
- Agentenrollen und Berechtigungen
- Tickets und Heartbeats
- Budgetkontrolle
- Goal Alignment
- Agent Instructions Management
- Tool-Call-Tracing
- Governance-Richtlinien
- Paperclip ↔ n8n Integration

### Phase 5 — Passive Research & Opportunity Scoring
- Öffentliche Programmquellen (passiv)
- Program Discovery
- Passive Recon Planner
- Opportunity Scoring
- Quellenreferenzen
- KEINE aggressiven Requests
- KEINE Authentifizierungsversuche
- KEINE Exploit-Ausführung

### Phase 6 — Local Lab Validation Only
- Juice Shop / WebGoat / DVWA Setup
- Validation Recipe JSON-Schema
- Validation Recipe Executor
- Lab-only Approval
- ScopeGuard-Prüfung jedes Requests
- Audit jedes Schritts
- KEINE realen Targets ohne explizite Freigabe

### Phase 7 — Reporting, Review & Dashboard
- Disclosure Draft Generator
- Triage Bundle Assembler
- Evidence Bundle Export
- Report Quality Gate Integration
- Reviewer-Workflow
- Dashboard/Statusseite
- GitHub-/Android-TV-Status

## 5. Abgrenzung zu früheren Konzepten

### Was sich geändert hat:

| Früher | Jetzt |
|--------|-------|
| Monolithische "NEUTRINO AI" App | Dreischicht: Neutrino Core + n8n Bridge + Paperclip CP |
| Agentenlogik direkt in Neutrino | Paperclip als separate Control Plane |
| Agent orchestriert Workflows | n8n als deterministische Workflow-Schicht |
| CLI als primäre UI | n8n als Integrations-Hub, CLI als eine Option |
| Alle Phasen in einem Repo | Neutrino = Safety Core, n8n/Paperclip = eigene Projekte |

### Was gleich bleibt:
- Safety-First, Default-Deny
- Human Approval für aktive Aktionen
- Evidence vor Claims
- Lab-only für aktive Validierung
- Keine automatische Report-Einreichung
- Append-only AuditLog

## 6. Offene Entscheidungen (YELLOW_REVIEW)

1. Ob n8n und Paperclip als separate Repos oder Submodule geführt werden
2. Ob ein Monorepo mit Workspaces oder getrennte Projekte
3. Konkrete n8n-Version und Deployment-Strategie
4. Paperclip-Hosting (lokal vs. Cloud)
5. MCP-Protokollversion und Transport (stdio vs. HTTP)

## 7. Änderungshistorie

| Datum | Version | Autor | Änderung |
|-------|---------|-------|----------|
| 2026-07-04 | 1.0.0 | Issue Orchestrator | Initiale Zielarchitektur nach Reality Refresh |
