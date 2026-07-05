# Neutrino Issue Alignment Report

> Reality Refresh & Issue-Neuausrichtung
> Datum: 2026-07-04
> Repository: github.com/xxammaxx/Neutrino

---

## 1. Reality-Refresh-Ergebnis

### Repository-Status

| Metadatum | Wert |
|-----------|------|
| Repository | github.com/xxammaxx/Neutrino |
| Default Branch | `main` |
| Sichtbarkeit | public |
| Erstellt | 2026-05-08 |
| Letzter Push | 2026-05-08 (Initialer Commit) |
| Architektur | leer (0 Commits, 0 Dateien) |
| GitHub Actions | keine |
| Releases | keine |
| Pull Requests | keine |
| Issues (offen) | 49 |
| Issues (geschlossen) | 0 |
| Labels | 29 |
| Milestones | 7 |

### Label-Bestand (vorhanden)

| Kategorie | Labels |
|-----------|--------|
| GitHub Default | bug, documentation, duplicate, enhancement, good first issue, help wanted, invalid, question, wontfix |
| Custom Workflow | vibe-coding |
| Module | module:compliance, module:security, module:core, module:db, module:infra, module:agent, module:api, module:ui, module:testing |
| Priority | priority:critical, priority:high, priority:medium, priority:low |
| Size | size:s, size:m, size:l |
| Mode | mode:passive, mode:active-validation, mode:lab-only |
| Approval | requires-human-approval |

### Milestone-Bestand (vorhanden)

| # | Titel | Issues |
|---|-------|--------|
| 1 | Phase 0 - Legal, Scope & Safety Foundation | 9 Issues (#1-#9) |
| 2 | Phase 1 - Foundation & Deterministic Core | 6 Issues (#10-#15) |
| 3 | Phase 2 - Safe Execution & Lab Sandbox | 6 Issues (#16-#21) |
| 4 | Phase 3 - Intelligence & RAG | 6 Issues (#22-#27) |
| 5 | Phase 4 - Agents & Orchestration | 7 Issues (#28-#34) |
| 6 | Phase 5 - CLI & Reporting | 7 Issues (#35-#41) |
| 7 | Phase 6 - QA & Compliance | 8 Issues (#42-#49) |

### Bewertung des Ist-Zustands

- **Repository ist vollständig leer** — kein Code, kein README, keine CI
- **49 Issues existieren** — alle vom 8. Mai 2026, alle offen
- **Issues sind gut strukturiert** — Akzeptanzkriterien, Abhängigkeiten dokumentiert
- **Issues folgen einem alten Konzept** — "NEUTRINO AI" als monolithische App
- **Zielarchitektur ist neu** — Neutrino Core + n8n Bridge + Paperclip Control Plane
- **Keine Breaking Changes** — da noch kein Code existiert, ist Neuausrichtung risikofrei

---

## 2. Issue-Mapping-Tabelle

### Legende

- 🟢 `GREEN_SAFE` — direkt umsetzbar
- 🟡 `YELLOW_REVIEW` — braucht Owner-Entscheidung
- 🔴 `RED_BLOCK` — blockiert / zu weitgehend
- ⚪ `UNKNOWN` — zu wenig Informationen
- 📦 `MERGE_CANDIDATE` — mit anderem Issue zusammenführen
- ✂️ `SPLIT_CANDIDATE` — aufteilen in mehrere Issues
- ✏️ `RENAME_ONLY` — Inhalt passt, Titel/Labels anpassen
- 🔄 `UPDATE_BODY` — Body an neues Format anpassen

---

### Phase 0 → Target: Repository Foundation & Governance

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| — | *Keine Issues vorhanden* | Phase 0 | Foundation | — | Neue Issues für README, SECURITY.md, Templates etc. müssen erstellt werden |

---

### Phase 1 → Target: Neutrino Safety Core

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| 1 | [Compliance] Policy-Parser Grundstruktur anlegen | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | Kern des Policy-Systems. Titel auf `[Neutrino] Policy-Parser Grundstruktur anlegen` |
| 2 | [Compliance] In-Scope- und Out-of-Scope-Extraktion | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | ScopePolicy-Modell. Teil der Policy-Pipeline |
| 3 | [Compliance] Rate-Limit- und Automation-Regeln extrahieren | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | Teil der Policy-Extraktion |
| 4 | [Security] Human Authorization Workflow | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | Human Approval ist Core-Safety-Feature. n8n-Integration später |
| 5 | [Security] ScopeGuard Request-Gating | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | Fundamentaler Safety-Mechanismus |
| 6 | [Security] Redirect- und CNAME-Prüfung | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | Scope-Evasion-Prävention |
| 7 | [Security] Rate-Limit Enforcement | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | Safety-Enforcement |
| 9 | [Compliance] Report-Quality-Gate | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | Quality Gate ist Safety-Core |

---

### Storage & Evidence (alt: Phase 1 → Target: Phase 2)

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| 10 | [DB] SQLite-Schema und Migrationen | Phase 2 | Neutrino Core (Storage) | ✏️ RENAME + 🔄 UPDATE_BODY | Persistenz-Schicht |
| 11 | [DB] CRUD-Repositories für Core-Entities | Phase 2 | Neutrino Core (Storage) | ✏️ RENAME + 🔄 UPDATE_BODY | Datenzugriff |
| 12 | [Core] AuditLog JSONL-Writer | Phase 2 | Neutrino Core (Storage) | ✏️ RENAME + 🔄 UPDATE_BODY | Audit-Persistenz |
| 13 | [Core] BudgetPolicy Statuslogik | Phase 2 | Neutrino Core (Storage) | ✏️ RENAME + 🔄 UPDATE_BODY | Budget-Status |

---

### Safety Enforcement (alt: Phase 1 → Target: Phase 1)

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| 14 | [Security] Active-Validation-Gate | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | Mit #4 (Human Approval) und #5 (ScopeGuard) eng verknüpft. 🟡 MERGE_CANDIDATE mit #4 |
| 15 | [Security] Programmspezifische Verbote | Phase 1 | Neutrino Core | ✏️ RENAME + 🔄 UPDATE_BODY | ScopePolicy-Enforcement |

---

### Lab & Validation (alt: Phase 2 → Target: Phase 6)

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| 16 | [Infra] Lokale Lab-Sandbox automatisieren | Phase 6 | Lokale Labs | ✏️ RENAME + 🔄 UPDATE_BODY | Lab-Setup. Titel: `[Lab] Lokale Lab-Sandbox automatisieren` |
| 17 | [Infra] Firecracker-gVisor-Isolation vorbereiten | Phase 6 | Lokale Labs | 🟡 YELLOW_REVIEW | Optional. Firecracker/gVisor sind komplex. Erst Docker-Compose-basierte Labs evaluieren |
| 18 | [Core] Validation-Recipe JSON-Schema | Phase 6 | Neutrino Core (Lab) | ✏️ RENAME + 🔄 UPDATE_BODY | Schema-Definition |
| 19 | [Core] Validation-Recipe-Executor | Phase 6 | Neutrino Core (Lab) | ✏️ RENAME + 🔄 UPDATE_BODY | Ausführung |
| 20 | [Core] Evidence-Oracle Mindestprüfungen | Phase 6 | Neutrino Core (Evidence) | ✏️ RENAME + 🔄 UPDATE_BODY | Evidence-Validierung |
| 21 | [Core] Evidence-State-Diffing | Phase 6 | Neutrino Core (Evidence) | ✏️ RENAME + 🔄 UPDATE_BODY | State-Diffing |

---

### RAG/Intelligence (alt: Phase 3 → Target: Umstritten)

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| 22 | [Core] RAG-Ingestion Pipeline | — | — | 🟡 YELLOW_REVIEW | RAG-Pipeline sprengt aktuellen Scope. Ist nicht Teil der Zielarchitektur (Neutrino Core + n8n + Paperclip). Owner-Entscheidung nötig |
| 23 | [Core] SHA-256 Integritätsprüfung | — | — | 🟡 YELLOW_REVIEW | Hängt von #22 ab. Owner-Entscheidung nötig |
| 24 | [Core] Vector-Store-Grundlagen | — | — | 🟡 YELLOW_REVIEW | Hängt von #22 ab. Owner-Entscheidung nötig |
| 25 | [Core] Hybrid-Retrieval | — | — | 🟡 YELLOW_REVIEW | Hängt von #22 ab. Owner-Entscheidung nötig |
| 26 | [Agent] ModelSelector Routinglogik | — | — | 🟡 YELLOW_REVIEW | LLM-Model-Selection. Passt nicht in Zielarchitektur ohne RAG. Owner-Entscheidung |
| 27 | [Agent] Hallucination-Guard | — | — | 🟡 YELLOW_REVIEW | Wichtiges Konzept (Hypothesen-Markierung), aber aktuell zu weit. Als Safety-Feature in Phase 1 erwägen |

---

### Agenten/Orchestration (alt: Phase 4 → Target: Phase 4/5)

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| 28 | [Agent] Program-Discovery-Ingestion | Phase 5 | Paperclip CP (Research Support) | ✏️ RENAME + 🔄 UPDATE_BODY | Passive Program Discovery. Gehört zu Research, nicht Agent Execution |
| 29 | [Agent] Opportunity-Scoring | Phase 5 | Paperclip CP (Research Support) | ✏️ RENAME + 🔄 UPDATE_BODY | Scoring passt zu Paperclip-Analyse |
| 30 | [Agent] Passive-Recon-Planer | Phase 5 | Paperclip CP (Research Support) | ✏️ RENAME + 🔄 UPDATE_BODY | Planer ist Analyse, nicht Execution |
| 31 | [Agent] Finding-Hypothesis-Engine | Phase 5 | Paperclip CP (Research Support) | ✏️ RENAME + 🔄 UPDATE_BODY | Hypothesen sind Analyse |
| 32 | [Agent] Finding-Triage-Pipeline | Phase 5 | Paperclip CP (Research Support) | ✏️ RENAME + 🔄 UPDATE_BODY | Triage ist Analyse/Koordination |
| 33 | [Agent] Safe-Validation-Plan-Builder | Phase 4/6 | Paperclip CP + Neutrino Core | ✂️ SPLIT_CANDIDATE | Plan-Generierung (Paperclip) + Plan-Ausführung (Neutrino) sollten getrennt werden |
| 34 | [Agent] Supervisor-State-Machine | Phase 4 | Paperclip CP | ✏️ RENAME + 🔄 UPDATE_BODY | Workflow-Orchestrierung gehört jetzt zu Paperclip (Koordination) + n8n (Ausführung) |

---

### CLI & Reporting (alt: Phase 5 → Target: Phase 7)

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| 35 | [API] Disclosure-Draft-Generator | Phase 7 | Reporting | ✏️ RENAME + 🔄 UPDATE_BODY | Draft-Generator ist Reporting |
| 36 | [API] Evidence-Bundle-Export | Phase 7 | Reporting | ✏️ RENAME + 🔄 UPDATE_BODY | Evidence-Export |
| 37 | [API] Triage-Bundle-Assembler | Phase 7 | Reporting | ✏️ RENAME + 🔄 UPDATE_BODY | Bundle-Assembly |
| 38 | [UI] CLI-Command program-discover | Phase 7 | n8n Bridge / CLI | 🟡 YELLOW_REVIEW | CLI-Commands könnten über n8n-Webhooks ersetzt werden. Owner-Entscheidung |
| 39 | [UI] CLI-Command parse-policy | Phase 7 | n8n Bridge / CLI | 🟡 YELLOW_REVIEW | Siehe #38 |
| 40 | [UI] CLI-Commands Scope und Research | Phase 7 | n8n Bridge / CLI | 🟡 YELLOW_REVIEW | Siehe #38 |
| 41 | [UI] CLI-Commands Approval und Reporting | Phase 7 | n8n Bridge / CLI | 🟡 YELLOW_REVIEW | Siehe #38 |

---

### Testing/Regression (alt: Phase 6 → Target: Zugeordnet zu jeweiligen Phasen)

| # | Aktueller Titel | Zielphase | Neue Rolle | Entscheidung | Begründung |
|---|---|---|---|---|---|
| 42 | [Testing] ScopeGuard Out-of-Scope Regression | Phase 1 | Neutrino Core (Test) | ✏️ RENAME + 🔄 UPDATE_BODY | Testet ScopeGuard → Phase 1 |
| 43 | [Testing] Redirect-Policy-Regression | Phase 1 | Neutrino Core (Test) | ✏️ RENAME + 🔄 UPDATE_BODY | Testet Redirect → Phase 1 |
| 44 | [Testing] Rate-Limit-Regression | Phase 1 | Neutrino Core (Test) | ✏️ RENAME + 🔄 UPDATE_BODY | Testet Rate-Limit → Phase 1 |
| 45 | [Testing] Verbotene-Testart-Regression | Phase 1 | Neutrino Core (Test) | ✏️ RENAME + 🔄 UPDATE_BODY | Testet Verbote → Phase 1 |
| 46 | [Testing] AuditLog-Integritätstests | Phase 2 | Neutrino Core (Test) | ✏️ RENAME + 🔄 UPDATE_BODY | Testet AuditLog → Phase 2 |
| 47 | [Testing] Human-Approval-Gate E2E | Phase 1 | Neutrino Core (Test) | ✏️ RENAME + 🔄 UPDATE_BODY | Testet Human Approval → Phase 1 |
| 48 | [Testing] Report-Quality-Gate Negativtests | Phase 1 | Neutrino Core (Test) | ✏️ RENAME + 🔄 UPDATE_BODY | Testet Quality Gate → Phase 1 |
| 49 | [Testing] E2E-Compliance gegen lokale Lab-Targets | Phase 6 | Lokale Labs (Test) | ✏️ RENAME + 🔄 UPDATE_BODY | E2E-Tests → Phase 6 |

---

## 3. Issue-Klassifikation Zusammenfassung

### GREEN_SAFE (direkt umsetzbar): 36 Issues
Issues #1-#7, #9-#16, #18-#21, #28-#32, #34-#37, #42-#49

Diese Issues sind inhaltlich korrekt, müssen nur umbenannt, umgelabelt und ins neue Body-Format gebracht werden.

### YELLOW_REVIEW (braucht Owner-Entscheidung): 13 Issues

| Issue | Grund |
|-------|-------|
| #8 | Passive-Recon-Workflow: Gehört nach Phase 5 (Research), aber Inhalt passt. Sollte verschoben werden. |
| #17 | Firecracker/gVisor: Zu komplex für initiale Phase. Docker-Compose evaluieren. |
| #22-#27 | RAG/Intelligence-Pipeline: Sprengt Zielarchitektur. Owner muss entscheiden, ob RAG Teil des Scopes ist. |
| #33 | Safe-Validation-Plan-Builder: Sollte in Plan-Generierung (Paperclip) und Ausführung (Neutrino) geteilt werden. |
| #38-#41 | CLI-Commands: Könnten durch n8n-Webhooks ersetzt werden. Owner muss UI-Strategie festlegen. |

### RED_BLOCK: 0 Issues
Kein Issue ist grundsätzlich gefährlich oder verboten. Alle Issues respektieren Safety-Regeln.

### MERGE_CANDIDATE: 1 Issue
- #14 (Active-Validation-Gate) → könnte mit #4 (Human Authorization) oder #5 (ScopeGuard) zusammengeführt werden

### SPLIT_CANDIDATE: 1 Issue
- #33 (Safe-Validation-Plan-Builder) → Plan-Generierung (Paperclip) vs. Plan-Ausführung (Neutrino)

---

## 4. Empfohlene neue Issues

### Phase 0 — Repository Foundation (Brandneue Issues)

| Titel | Labels | Beschreibung |
|-------|--------|-------------|
| [Foundation] README.md mit Projektvision und Quickstart | layer:neutrino-core, type:documentation, safety:default-deny | Projektbeschreibung, Architektur-Diagramm, lokaler Setup-Guide |
| [Foundation] SECURITY.md mit Safety Policy | layer:neutrino-core, type:documentation, safety:default-deny | Referenziert SAFETY_DECISION_MANIFEST.md |
| [Foundation] CONTRIBUTING.md mit Developer Guide | layer:neutrino-core, type:documentation | Wie beitragen, Branch-Strategie, Commit-Konventionen |
| [Foundation] Issue- und PR-Templates anlegen | layer:neutrino-core, type:foundation | Bug Report, Feature Request, Security Report Templates |
| [Foundation] Label-System für Neutrino/n8n/Paperclip normalisieren | layer:neutrino-core, type:foundation | Neue Labels: layer:*, safety:*, status:*, type:* |
| [Foundation] Milestones für Phasen 0-7 anlegen | layer:neutrino-core, type:foundation | Zielphasen-Milestones |
| [Foundation] Lokale Entwicklungsanleitung | layer:neutrino-core, type:documentation | Dev-Setup, Tests, Linting, Pre-commit Hooks |

### Phase 3 — n8n Workflow Bridge (Brandneue Issues)

| Titel | Labels | Beschreibung |
|-------|--------|-------------|
| [n8n] Webhook-Endpunkt für GitHub-Issue-Events | layer:n8n-bridge, type:integration | Empfängt Issue-Events von GitHub |
| [n8n] Human-in-the-loop Approval Workflow | layer:n8n-bridge, safety:human-approval | n8n-Workflow für Approval-Anfragen |
| [n8n] Sichere Neutrino API Bridge | layer:n8n-bridge, type:integration | n8n ruft Neutrino APIs nur mit ScopeGuard |
| [n8n] MCP Server Bridge konfigurieren | layer:n8n-bridge, type:mcp | n8n als MCP-Host für sichere Neutrino-Tools |
| [n8n] Statusseite für Workflow-Zustände | layer:n8n-bridge, type:workflow | Dashboard-Daten für n8n-Workflows |
| [n8n] Android-TV Dashboard Output | layer:dashboard, type:integration | Status-Daten für Android-TV |

### Phase 4 — Paperclip Control Plane (Brandneue Issues)

| Titel | Labels | Beschreibung |
|-------|--------|-------------|
| [Paperclip] Agenten-Rollen und Berechtigungen definieren | layer:paperclip-control-plane, type:agent-governance | Role-based Access für Agenten |
| [Paperclip] Ticket-System für Agenten-Aufgaben | layer:paperclip-control-plane, type:agent-governance | Issue-Tracking via Paperclip |
| [Paperclip] Heartbeat- und Liveness-Checks | layer:paperclip-control-plane, type:agent-governance | Agent-Health-Monitoring |
| [Paperclip] Budget-System für Agenten-Aktionen | layer:paperclip-control-plane, type:agent-governance | Cost-Control |
| [Paperclip] Goal Alignment und Priorisierung | layer:paperclip-control-plane, type:agent-governance | Agent-Ziele an Projekt-Roadmap |
| [Paperclip] Tool-Call-Tracing und Audit | layer:paperclip-control-plane, type:agent-governance | Alle Agent-Tool-Calls nachverfolgen |
| [Paperclip] Paperclip ↔ n8n Integration | layer:paperclip-control-plane, type:integration | Tickets → n8n Workflows |

---

## 5. Milestone-Neuausrichtung

### Alte Milestones → Neue Milestones

| Alt | Issues | Neu | Issues |
|-----|--------|-----|--------|
| Phase 0 (Legal, Scope & Safety) | #1-#9 | Phase 0 (Foundation) | Neue Issues |
| | | Phase 1 (Neutrino Core) | #1-#7, #9, #14, #15, #42-#45, #47-#48 |
| Phase 1 (Foundation & Core) | #10-#15 | Phase 2 (Storage & Evidence) | #10-#13, #46 |
| Phase 2 (Safe Execution & Labs) | #16-#21 | Phase 6 (Lab Validation) | #16, #18-#21, #49 |
| Phase 3 (Intelligence & RAG) | #22-#27 | 🟡 YELLOW_REVIEW | #22-#27 |
| Phase 4 (Agents & Orchestration) | #28-#34 | Phase 4 (Paperclip CP) | #34, neue Issues |
| | | Phase 5 (Passive Research) | #28-#32 |
| Phase 5 (CLI & Reporting) | #35-#41 | Phase 7 (Reporting) | #35-#37 |
| Phase 6 (QA & Compliance) | #42-#49 | Zugeordnet zu Phasen 1,2,6 | #42-#49 |

### Empfohlene neue Milestone-Struktur

| # | Milestone | Beschreibung | Issues |
|---|-----------|-------------|--------|
| 0 | Phase 0 — Repository Foundation & Governance | Repo aufsetzen, Docs, Labels, Templates | Neue Issues |
| 1 | Phase 1 — Neutrino Safety Core | Policy Parser, ScopeGuard, Human Approval, AuditLog | #1-#7, #9, #14, #15, #42-#45, #47-#48 |
| 2 | Phase 2 — Deterministic Storage & Evidence | SQLite, CRUD, Evidence, Audit-Persistenz | #10-#13, #46 |
| 3 | Phase 3 — n8n Workflow Bridge | Webhooks, Human-in-loop, MCP, Status | Neue Issues + #38-#41 (wenn CLI behalten) |
| 4 | Phase 4 — Paperclip Control Plane | Rollen, Tickets, Budget, Governance | #34, neue Paperclip-Issues |
| 5 | Phase 5 — Passive Research & Scoring | Program Discovery, Recon, Scoring | #8, #28-#32 |
| 6 | Phase 6 — Local Lab Validation | Lab-Setup, Recipe Schema, Executor | #16, #18-#21, #49 |
| 7 | Phase 7 — Reporting & Dashboard | Drafts, Bundles, Export, Dashboard | #35-#37 |

---

## 6. YELLOW_REVIEW — Offene Owner-Entscheidungen

| # | Entscheidung | Optionen | Empfehlung |
|---|-------------|----------|-----------|
| 1 | RAG/Intelligence-Pipeline (#22-#27): Teil des Scopes? | A: Später wiedereinführen, B: Auslagern in eigenes Projekt, C: Jetzt vereinfacht implementieren | A — erst Safety Core stabilisieren |
| 2 | CLI vs. n8n-Webhooks (#38-#41): UI-Strategie? | A: CLI beibehalten, B: Nur n8n-Webhooks, C: Beides parallel | C — CLI für Dev/Debug, n8n für Produktion |
| 3 | Firecracker/gVisor (#17): Jetzt oder später? | A: Jetzt vorbereiten, B: Docker-Compose-first, später evaluieren | B — Docker-Compose ist ausreichend für Phase 6 |
| 4 | Monorepo vs. separate Repos: n8n und Paperclip? | A: Monorepo mit Workspaces, B: Separate Repos, C: Submodule | A — einfacher für initiale Entwicklung |
| 5 | #33 (Validation-Plan-Builder): Splitten? | A: Ja, Plan-Gen und Ausführung trennen, B: Zusammenhalten | A — klare Trennung von Planung und Ausführung |
| 6 | #14 (Active-Validation-Gate): Mit #4 mergen? | A: Mergen, B: Getrennt lassen | B — getrennt, aber Abhängigkeit dokumentieren |

---

## 7. Empfohlene Build-Reihenfolge

```text
Priorität 1 (Foundation):
  → Phase 0: Neue Issues (README, SECURITY.md, CONTRIBUTING.md, Templates, Labels, Milestones)
  → Phase 0: Dieses Alignment-Report-Dokument commiten
  → Phase 0: Zielarchitektur-Dokument commiten
  → Phase 0: Safety Decision Manifest commiten

Priorität 2 (Safety Core):
  → #1: Policy-Parser Grundstruktur
  → #2: In-Scope/Out-of-Scope-Extraktion
  → #3: Rate-Limit-/Automation-Regeln
  → #5: ScopeGuard Request-Gating
  → #4: Human Authorization Workflow
  → #15: Programmspezifische Verbote
  → #6: Redirect- und CNAME-Prüfung
  → #7: Rate-Limit Enforcement
  → #9: Report-Quality-Gate

Priorität 3 (Storage & Evidence):
  → #10: SQLite-Schema und Migrationen
  → #11: CRUD-Repositories
  → #12: AuditLog JSONL-Writer
  → #13: BudgetPolicy Statuslogik

Priorität 4 (Tests für Priorität 2 & 3):
  → #42-#48: Regressionstests

Priorität 5 (n8n Bridge):
  → Neue n8n-Issues
  → Owner-Entscheidung zu CLI (#38-#41)

Priorität 6 (Paperclip Control Plane):
  → Neue Paperclip-Issues
  → #34: Supervisor-State-Machine

Priorität 7 (Passive Research):
  → #28-#32, #8

Priorität 8 (Lab Validation):
  → #18, #16, #19, #20, #21, #49

Priorität 9 (Reporting):
  → #35, #36, #37
```

---

## 8. Was wurde bewusst nicht geändert?

1. **Keine Issues gelöscht** — Issues werden nicht gelöscht, nur neu klassifiziert
2. **Keine Issues geschlossen** — Alle Issues sind inhaltlich relevant, nur umzuordnen
3. **Keine Issue-Historie verändert** — Änderungen sind additiv
4. **RAG/Intelligence (#22-#27)** — Nicht gelöscht, sondern als YELLOW_REVIEW markiert. Owner muss entscheiden
5. **Alte Labels nicht gelöscht** — Neue Labels werden ergänzt, alte bleiben (für historische Issues)

---

## 9. Nächste Schritte nach diesem Lauf

1. **Owner muss YELLOW_REVIEW-Entscheidungen treffen** (siehe Abschnitt 6)
2. **GREEN_SAFE-Issues umbenennen und neu labeln** (36 Issues)
3. **Neue Foundation-Issues erstellen** (Phase 0)
4. **Neue n8n-Issues erstellen** (Phase 3)
5. **Neue Paperclip-Issues erstellen** (Phase 4)
6. **Milestones neu erstellen** (Phasen 0-7)
7. **Labels ergänzen** (layer:*, safety:*, status:*, type:*)
8. **Dokumente committen** (Alignment Report, Target Architecture, Safety Manifest)
9. **Build gemäß Prioritätsliste starten**

---

## 10. Kurzfazit

**GESAMTSTATUS: GREEN**

- Das Repository ist in einem idealen Zustand für eine Neuausrichtung: leer, aber gut dokumentiert
- Alle 49 Issues sind inhaltlich wertvoll und sicherheitsbewusst formuliert
- Keine RED_BLOCK-Issues — die ursprünglichen Autoren haben Safety-Regeln respektiert
- 36 Issues sind GREEN_SAFE und können direkt neu zugeordnet werden
- 13 Issues benötigen Owner-Entscheidungen (meist Scope-Entscheidungen)
- Die neue Zielarchitektur (Neutrino Core + n8n + Paperclip) ist mit minimalen Änderungen aus den bestehenden Issues ableitbar
- Die größte konzeptionelle Verschiebung betrifft RAG/Intelligence (#22-#27) und CLI-UI (#38-#41)

---

---

## 11. Governance Polish 2026-07-05

Am 2026-07-05 wurde ein Governance-Polish-Lauf durchgeführt:

- **49 Issue-Bodies** auf das neue Ziel-Template normalisiert (Ziel, Rolle, Sicherheitsklasse, Nicht-Ziele, Verification Contract, Safety Notes, Next-Step-Handoff)
- **Alte Architekturbegriffe** („NEUTRINO AI") bereinigt
- **Abhängigkeiten** auf neue Komponentennamen aktualisiert
- **6 neue Issues** erstellt:
  - #51: GitHub Issue- und PR-Templates
  - #52: Code-Konventionen und Build-Standard
  - #53: n8n Workflow-Bridge Grunddesign
  - #54: n8n Human-in-the-loop Approval Workflow
  - #55: Paperclip Control-Plane Rollenmodell
  - #56: Dashboard Projektstatusseite

Details siehe: [Governance Polish Report](./NEUTRINO_GOVERNANCE_POLISH_REPORT.md)

---

*Report erstellt am 2026-07-04 durch Issue Orchestrator im Rahmen des Reality Refresh*
*Governance Polish Update 2026-07-05*
