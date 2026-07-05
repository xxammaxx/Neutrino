# Neutrino Owner Decisions Report

> Datum: 2026-07-05
> Lauf-Typ: Owner Decision / Governance
> Scope: YELLOW_REVIEW-Entscheidungen
> Kein Code-Implementierungs-Lauf

---

## Kurzfazit

**GREEN** — Die offenen YELLOW_REVIEW-Entscheidungen wurden getroffen und dokumentiert.

- 12 YELLOW_REVIEW-Issues wurden mit Owner-Entscheidungen versehen
- 6 Entscheidungen dokumentiert
- 1 Label-Inkonsistenz (#8) korrigiert
- 2 neue reine Spezifikations-Issues für #33 Split erstellt (#57, #58)
- Keine Code-Implementierung, keine Security-Scans, keine aktiven Tests
- Keine Issues gelöscht, geschlossen oder gemerged

---

## Reality Refresh

| Metadatum | Wert |
|-----------|------|
| Repository | github.com/xxammaxx/Neutrino |
| Default Branch | `main` |
| Letzter Commit | `db1ae65` — docs: add Governance Polish Report and update Alignment Report |
| Vorhandene Dateien | README.md, SECURITY.md, CONTRIBUTING.md, docs/architecture/NEUTRINO_N8N_PAPERCLIP_TARGET_ARCHITECTURE.md, docs/governance/SAFETY_DECISION_MANIFEST.md, docs/roadmap/NEUTRINO_ISSUE_ALIGNMENT_REPORT.md, docs/roadmap/NEUTRINO_GOVERNANCE_POLISH_REPORT.md |
| GitHub Actions | Keine |
| Pull Requests | Keine |
| Issues (offen) | 58 (#1-#56 Original + #57, #58 neu) |
| Issues (geschlossen) | 0 |
| Labels | 56 |
| Milestones | 8 (Phasen 0-7) |

---

## Getroffene Entscheidungen

| Entscheidung | Issues | Decision | Ergebnis | Risiko |
|---|---|---|---|---|
| RAG/Intelligence | #22-#27 | `DEFER_RAG_UNTIL_SAFETY_CORE_GREEN` | DEFERRED — blockiert bis Phase 1/2 grün | GREEN_SAFE |
| CLI vs. n8n | #38-#41 | `KEEP_CLI_FOR_DEV_AND_N8N_FOR_WORKFLOWS` | DECIDED — CLI als Dev/Debug, n8n als Produktion | GREEN_SAFE |
| Firecracker/gVisor | #17 | `DOCKER_COMPOSE_FIRST_FIRECRACKER_LATER` | DEFERRED — Docker-Compose zuerst | GREEN_SAFE |
| Passive Recon | #8 | `MOVE_PASSIVE_RECON_TO_PHASE_5_AFTER_SAFETY_CORE` | DECIDED — Phase 5, nach Safety Core | GREEN_SAFE |
| Split #33 | #33, #57, #58 | `SPLIT_VALIDATION_PLAN_BUILDER` | DECIDED — Plan-Generator (#57) + Plan-Executor (#58) | GREEN_SAFE |
| Merge #14/#4 | #14, #4 | `KEEP_14_SEPARATE_DEPENDS_ON_4` | DECIDED — getrennt, Abhängigkeit dokumentiert | GREEN_SAFE |

---

## RAG / Intelligence (#22-#27)

**Decision:** `DEFER_RAG_UNTIL_SAFETY_CORE_GREEN`

**Begründung:**
Neutrino braucht zuerst einen stabilen Safety Core: Policy Parser, ScopeGuard, Human Approval, AuditLog, Evidence Oracle und Report Quality Gate. RAG kann später sinnvoll sein, darf aber niemals Evidence ersetzen. LLM-Ausgaben bleiben Hypothesen, keine Fakten.

**Betroffene Issues:**
- #22 RAG-Ingestion Pipeline — DEFERRED
- #23 SHA-256 Integritätsprüfung — DEFERRED (hängt von #22 ab)
- #24 Vector-Store-Grundlagen — DEFERRED (hängt von #22 ab)
- #25 Hybrid-Retrieval — DEFERRED (hängt von #22 ab)
- #26 ModelSelector Routinglogik — DEFERRED
- #27 Hallucination-Guard — DEFERRED

**Folgeaktion:** Issues bleiben offen mit `status:yellow-review`, Owner Decision in Body dokumentiert. Nach grünem Safety Core (Phase 1/2) erneut prüfen.

---

## CLI vs. n8n (#38-#41)

**Decision:** `KEEP_CLI_FOR_DEV_AND_N8N_FOR_WORKFLOWS`

**Begründung:**
Beide UI-Strategien sind wertvoll, aber mit klarer Rollenverteilung:
- **CLI** = lokales Dev-, Debug- und Fallback-Werkzeug
- **n8n** = deterministische Produktions-Workflow-Schicht
- CLI darf niemals ScopeGuard, Human Approval, AuditLog oder Report Quality Gate umgehen

**Betroffene Issues:**
- #38 CLI program-discover — KEEP als Dev-CLI
- #39 CLI parse-policy — KEEP als Dev-CLI
- #40 CLI Scope und Research — KEEP als Dev-CLI
- #41 CLI Approval und Reporting — KEEP als Dev-CLI

**Folgeaktion:** Issues bleiben offen mit `status:yellow-review`. Umsetzung nach Phase 1/2 Safety Core. n8n-Issues #53 und #54 bleiben die Grundlage für produktive Workflow-Automation.

---

## Firecracker / gVisor (#17)

**Decision:** `DOCKER_COMPOSE_FIRST_FIRECRACKER_LATER`

**Begründung:**
Firecracker/gVisor ist für einen frühen Foundation-/Safety-Core-Stand zu komplex. Für Phase 6 reicht zunächst Docker Compose mit lokalen, absichtlich verwundbaren Labs (Juice Shop, WebGoat, DVWA). Isolation kann später gehärtet werden.

**Betroffenes Issue:**
- #17 Firecracker-gVisor-Isolation vorbereiten — DEFERRED

**Folgeaktion:** #17 bleibt offen mit `status:yellow-review`. Keine Umsetzung vor lokalem Lab-Basisdesign (#16) und Validation-Recipe-Executor (#19).

---

## Passive Recon (#8)

**Decision:** `MOVE_PASSIVE_RECON_TO_PHASE_5_AFTER_SAFETY_CORE`

**Begründung:**
Phase 1 soll den Neutrino Safety Core stabilisieren. Passive Recon braucht später Paperclip Research Support und n8n-Workflow-Gates. Ohne Policy Parser, ScopeGuard, AuditLog und Evidence-Regeln ist selbst passive Recherche zu unscharf.

**Betroffenes Issue:**
- #8 Passive-Recon-Workflow — DECIDED, Phase 5

**Label-Korrektur:** #8 hatte fälschlicherweise das Label `status:green-safe` bei einem YELLOW_REVIEW-Body. Das Label wurde auf `status:yellow-review` korrigiert.

**Folgeaktion:** #8 bleibt offen mit `status:yellow-review`. Safety Notes verlangen: passive only, keine aggressiven Requests, keine Login-Versuche, keine Exploit-Ausführung.

---

## Split #33 — Validation-Plan-Builder

**Decision:** `SPLIT_VALIDATION_PLAN_BUILDER`

**Begründung:**
Plan-Generierung und Plan-Ausführung müssen getrennt werden:
1. **Paperclip Plan Generator** — Agenten erstellen Validierungspläne als Analyse, keine Ausführung, keine Shell, keine echten Targets
2. **Neutrino Plan Executor** — führt validierte Pläne aus, nur lokal / Lab-only, nur mit ScopeGuard, Human Approval, AuditLog und Evidence Gate

**Neue Issues:**
- **#57** `[Paperclip] Validation-Plan-Generator spezifizieren` — Phase 4, GREEN_SAFE (reine Spezifikation)
- **#58** `[Neutrino] Validation-Plan-Executor spezifizieren` — Phase 6, GREEN_SAFE (reine Spezifikation)

**Folgeaktion:** #33 bleibt als Parent/Tracking-Issue offen. #57 und #58 sind reine Spezifikations-Dokumente (kein Code).

---

## Merge #14 / #4 — Active-Validation-Gate

**Decision:** `KEEP_14_SEPARATE_DEPENDS_ON_4`

**Begründung:**
Human Authorization (#4) und Active Validation Gate (#14) sind eng gekoppelt, aber nicht identisch:
- #4 entscheidet: Wer darf aktive Schritte freigeben?
- #14 entscheidet: Wann wird aktive Validierung technisch blockiert oder erlaubt?
Beide haben unterschiedliche Akzeptanzkriterien und Testfälle.

**Betroffene Issues:**
- #14 Active-Validation-Gate — KEEP SEPARATE, Abhängigkeit zu #4 dokumentiert
- #4 Human Authorization Workflow — nicht geändert

**Folgeaktion:** #14 bleibt offen. Das `status:merge-candidate`-Label bleibt als historische Markierung. Implementierung von #14 kann nach Fertigstellung von #4 erfolgen.

---

## Geänderte Issues

### Body-Updates (Owner Decision Section appended)

| # | Titel | Decision |
|---|-------|----------|
| #8 | Passive-Recon-Workflow | MOVE_PASSIVE_RECON_TO_PHASE_5_AFTER_SAFETY_CORE |
| #14 | Active-Validation-Gate | KEEP_14_SEPARATE_DEPENDS_ON_4 |
| #17 | Firecracker-gVisor-Isolation | DOCKER_COMPOSE_FIRST_FIRECRACKER_LATER |
| #22 | RAG-Ingestion Pipeline | DEFER_RAG_UNTIL_SAFETY_CORE_GREEN |
| #23 | SHA-256 Integritätsprüfung | DEFER_RAG_UNTIL_SAFETY_CORE_GREEN |
| #24 | Vector-Store-Grundlagen | DEFER_RAG_UNTIL_SAFETY_CORE_GREEN |
| #25 | Hybrid-Retrieval | DEFER_RAG_UNTIL_SAFETY_CORE_GREEN |
| #26 | ModelSelector Routinglogik | DEFER_RAG_UNTIL_SAFETY_CORE_GREEN |
| #27 | Hallucination-Guard | DEFER_RAG_UNTIL_SAFETY_CORE_GREEN |
| #33 | Safe-Validation-Plan-Builder | SPLIT_VALIDATION_PLAN_BUILDER |
| #38 | CLI program-discover | KEEP_CLI_FOR_DEV_AND_N8N_FOR_WORKFLOWS |
| #39 | CLI parse-policy | KEEP_CLI_FOR_DEV_AND_N8N_FOR_WORKFLOWS |
| #40 | CLI Scope und Research | KEEP_CLI_FOR_DEV_AND_N8N_FOR_WORKFLOWS |
| #41 | CLI Approval und Reporting | KEEP_CLI_FOR_DEV_AND_N8N_FOR_WORKFLOWS |
| #50 | Meta-Issue | Owner Decisions 2026-07-05 Abschnitt + neue Issues referenziert |

### Label-Änderungen

| # | Vorher | Nachher |
|---|--------|---------|
| #8 | `status:green-safe` | `status:yellow-review` |

---

## Neue Issues

| # | Titel | Phase | Typ | Labels |
|---|-------|-------|-----|--------|
| #57 | [Paperclip] Validation-Plan-Generator spezifizieren | Phase 4 | Spezifikation | layer:paperclip-control-plane, type:agent-governance, status:green-safe |
| #58 | [Neutrino] Validation-Plan-Executor spezifizieren | Phase 6 | Spezifikation | layer:neutrino-core, type:security, status:green-safe, safety:lab-only |

Beide Issues sind **reine Spezifikationen** (kein Code) und GREEN_SAFE. Sie definieren die Schnittstelle und Sicherheitsgates, bevor Code implementiert wird.

---

## Nicht geändert

1. **Keine Issues gelöscht** — alle 56 Original-Issues + 2 neue sind offen
2. **Keine Issues geschlossen** — Entscheidungen sind dokumentiert, Issues bleiben zur Nachverfolgung offen
3. **Keine Issue-Historie verändert** — alle Änderungen sind additiv
4. **Keine Labels gelöscht** — `status:merge-candidate` auf #14 bleibt als historische Markierung
5. **Keine Milestones gelöscht** — Milestones unverändert
6. **Kein Code implementiert** — dieser Lauf war rein dokumentarisch
7. **Keine GitHub Actions aktiviert** — kein `.github/workflows/` angelegt
8. **Keine Security-Scans durchgeführt** — keine Targets kontaktiert

---

## RED_BLOCK

**Keine RED_BLOCK-Issues.** Alle 14 betroffenen Issues sind sicher und respektieren das Safety Decision Manifest.

---

## Nächste empfohlene Läufe

1. **Phase 0 Abschluss** — #51 (Templates) und #52 (Code-Konventionen) umsetzen
2. **Phase 1 Start** — Policy Parser #1 implementieren (erster Code-Commit)
3. **Phase 3/4 Spezifikation** — #53-#56 (n8n-Bridge, Paperclip-Rollen, Dashboard) + #57-#58 (neue Split-Issues) umsetzen
4. **Safety Core Tests** — #42-#48 Regressionstests nach Build definieren
5. **CI/CD-Planung** — GitHub Actions erst nach lokaler Build-Stabilität aktivieren (Safety-Regel #9)

---

## Verification Contract

- [x] Alle `status:yellow-review`-Issues geprüft
- [x] 6 Owner-Entscheidungen dokumentiert
- [x] Issue #50 aktualisiert
- [x] 14 Issue-Bodies mit Owner-Decision-Sektion ergänzt
- [x] Issue #8 Label-Inkonsistenz korrigiert
- [x] 2 neue Split-Issues (#57, #58) erstellt
- [x] Keine Issues gelöscht, geschlossen oder gemerged
- [x] Kein Produktcode, keine Security-Scans, keine aktiven Tests
- [x] Keine GitHub Actions oder Remote-CI aktiviert
- [x] Alle Änderungen respektieren das Safety Decision Manifest

---

*Report erstellt am 2026-07-05 durch Issue Orchestrator im Rahmen des Owner-Entscheidungslaufs*
