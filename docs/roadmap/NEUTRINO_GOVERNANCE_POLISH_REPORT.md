# Neutrino Governance Polish Report

> Issue-Body-Normalisierung & Konsistenzbereinigung
> Datum: 2026-07-05
> Repository: github.com/xxammaxx/Neutrino
> Lauf-Typ: Governance Polish (kein Code-Implementierungs-Lauf)

---

## Kurzfazit

**GREEN** — Der Governance-Polish-Lauf wurde vollständig und ohne Fehler durchgeführt.

- Alle 49 Issue-Bodies wurden auf das neue Ziel-Template normalisiert
- Alte Architekturbegriffe („NEUTRINO AI") wurden bereinigt
- 6 neue Governance/Foundation-Issues erstellt (#51-#56)
- Issue #50 konsistent aktualisiert
- Keine Code-Implementierung, keine Security-Scans, keine aktiven Tests

---

## Reality Refresh

| Metadatum | Wert |
|-----------|------|
| Repository | github.com/xxammaxx/Neutrino |
| Default Branch | `main` |
| Letzter Commit | `7b665d9 Phase 0: Repository Foundation — Governance, Architecture & Issue Alignment` |
| Vorhandene Dateien | README.md, SECURITY.md, CONTRIBUTING.md, docs/architecture/NEUTRINO_N8N_PAPERCLIP_TARGET_ARCHITECTURE.md, docs/governance/SAFETY_DECISION_MANIFEST.md, docs/roadmap/NEUTRINO_ISSUE_ALIGNMENT_REPORT.md |
| GitHub Actions | Keine (kein `.github/workflows/` Verzeichnis) |
| Pull Requests | Keine |
| Issues (offen) | 56 (49 Original + 1 Meta-Issue #50 + 6 neue) |
| Issues (geschlossen) | 0 |
| Labels | 56 (inkl. aller layer:*, safety:*, status:*, type:* Labels) |
| Milestones | 8 (Phase 0 — Phase 7) |

---

## Geänderte Issues

Alle 49 Issues (#1-#49) wurden normalisiert. Jeder Issue-Body wurde vom alten Format:

```
## Kontext → ## Aufgabe → ## Akzeptanzkriterien → ## Abhängigkeiten → ## Vibe Coding Hinweise
```

in das neue Ziel-Template überführt:

```
## Ziel → ## Rolle in der Zielarchitektur → ## Sicherheitsklasse → ## Kontext →
## Aufgabe → ## Akzeptanzkriterien → ## Nicht-Ziele → ## Abhängigkeiten →
## Verification Contract → ## Safety Notes → ## Next-Step-Handoff
```

### GREEN_SAFE Issues (36 Issues)

Vollständig normalisiert mit:
- Klaren Nicht-Zielen (was darf NICHT gebaut werden?)
- Verification Contract (welche Tests/Checks müssen grün sein?)
- Safety Notes (Default-Deny, Evidence vor Claims, UNKNOWN = Blockieren)
- Next-Step-Handoff (was kommt nach diesem Issue?)

**Betroffene Issues:** #1-#7, #9-#16, #18-#21, #28-#32, #34-#37, #42-#49

### YELLOW_REVIEW Issues (12 Issues)

Mit Blockierungs-Hinweisen versehen:
- `> ⚠️ YELLOW_REVIEW — Blockiert bis Owner-Entscheidung`
- Begründung für die Blockierung
- Einschränkungen für den Fall der Freigabe
- Abhängigkeit: „Blockiert durch: Owner-Entscheidung (YELLOW_REVIEW)"

**Betroffene Issues:**
- #22-#27: RAG/Intelligence-Pipeline
- #38-#41: CLI vs. n8n-Webhooks
- #8: Passive-Recon-Workflow (Phasen-Zuordnung unklar)
- #17: Firecracker/gVisor-Isolation (zu komplex für initiale Phase)

### SPLIT_CANDIDATE (1 Issue)

- #33: Safe-Validation-Plan-Builder — dokumentiert als Split in Teil A (Paperclip: Plan-Generierung) und Teil B (Neutrino: Plan-Ausführung)

### MERGE_CANDIDATE (1 Issue)

- #14: Active-Validation-Gate — dokumentiert als Merge-Kandidat mit #4 (Human Authorization)

---

## Neue Issues

6 neue Governance/Foundation-Issues erstellt (alle GREEN_SAFE):

| # | Titel | Phase | Typ |
|---|-------|-------|-----|
| #51 | [Governance] GitHub Issue- und PR-Templates anlegen | Phase 0 | Foundation |
| #52 | [Governance] Code-Konventionen und lokalen Build-Standard definieren | Phase 0 | Documentation |
| #53 | [n8n] Workflow-Bridge Grunddesign spezifizieren | Phase 3 | Documentation |
| #54 | [n8n] Human-in-the-loop Approval Workflow spezifizieren | Phase 3 | Workflow |
| #55 | [Paperclip] Control-Plane Rollenmodell spezifizieren | Phase 4 | Agent-Governance |
| #56 | [Dashboard] Projektstatusseite für Governance- und Safety-Status spezifizieren | Phase 7 | Documentation |

Alle neuen Issues folgen dem Ziel-Template und enthalten:
- Klare Nicht-Ziele
- Verification Contracts
- Safety Notes
- Keine Code-Implementierung (reine Spezifikation)

---

## Aktualisierte Dokumente

1. **Issue #50** — Body aktualisiert:
   - „Dokumente committed" als erledigt markiert (Dokumente sind im Repo)
   - Governance Polish Follow-up-Checkliste ergänzt
   - Neue Issues (#51-#56) referenziert
   - Tabelle mit neuen Issues eingefügt

2. **`docs/roadmap/NEUTRINO_GOVERNANCE_POLISH_REPORT.md`** — Dieser Report (neu erstellt)

---

## Offene YELLOW_REVIEW-Entscheidungen

| # | Entscheidung | Optionen | Empfehlung | Betroffene Issues |
|---|-------------|----------|-----------|-------------------|
| 1 | RAG/Intelligence-Pipeline: Teil des Scopes? | A: Später, B: Auslagern, C: Vereinfacht jetzt | A — erst Safety Core stabilisieren | #22-#27 |
| 2 | CLI vs. n8n-Webhooks: UI-Strategie? | A: CLI, B: Nur n8n, C: Beides parallel | C — CLI für Dev/Debug, n8n für Produktion | #38-#41 |
| 3 | Firecracker/gVisor: Jetzt oder später? | A: Jetzt, B: Docker-Compose-first | B — Docker-Compose ausreichend für Phase 6 | #17 |
| 4 | Passive-Recon: Phase 1 oder Phase 5? | A: Phase 1, B: Phase 5 | B — abhängig von Paperclip-Research | #8 |
| 5 | #33 (Validation-Plan-Builder): Splitten? | A: Ja, B: Zusammenhalten | A — klare Trennung Planung/Ausführung | #33 |
| 6 | #14 (Active-Validation-Gate): Mit #4 mergen? | A: Mergen, B: Getrennt lassen | B — getrennt, aber Abhängigkeit dokumentieren | #14 |

---

## RED_BLOCK

Keine RED_BLOCK-Issues identifiziert. Alle 49 Original-Issues respektieren die Safety-Regeln.

---

## Konsistenzkorrekturen

### Begriffliche Bereinigung

| Vorher | Nachher |
|--------|---------|
| „NEUTRINO AI" | „Neutrino-Ökosystem" oder „Neutrino Core" |
| `[Compliance]` in Abhängigkeiten | Entfernt (Komponenten-Präfixe bereinigt) |
| `[Security]` in Abhängigkeiten | Entfernt |
| `[Core]` in Abhängigkeiten | Entfernt |
| `[Agent]` in Abhängigkeiten | Entfernt |
| `[UI]` in Abhängigkeiten | Entfernt |
| `[DB]` in Abhängigkeiten | Entfernt |
| `[API]` in Abhängigkeiten | Entfernt |

### Template-Standardisierung

- **Vorher:** 5 optionale Sektionen (`## Kontext`, `## Aufgabe`, `## Akzeptanzkriterien`, `## Abhängigkeiten`, `## Vibe Coding Hinweise`)
- **Nachher:** 11 verpflichtende Sektionen inkl. Sicherheitsdeklaration

---

## Was kann das Repo nach diesem Lauf besser?

1. **Jeder Issue-Body ist selbsterklärend** — kein externes Wissen nötig, um zu verstehen, was ein Issue erreichen soll
2. **Sicherheitsgrenzen sind explizit** — jedes Issue sagt klar, was NICHT gebaut werden darf
3. **Verification Contracts sind definiert** — jedes Issue hat messbare Erfolgskriterien
4. **YELLOW_REVIEW-Issues sind klar blockiert** — kein Risiko versehentlicher Implementierung
5. **Dependency-Referenzen sind konsistent** — kein Verweis auf alte Komponentennamen
6. **Foundation-Lücken sind geschlossen** — Templates, Konventionen und Spezifikationen als Issues vorhanden
7. **Next-Step-Handoff** — jedes Issue sagt, was als nächstes kommt

---

## Nächste empfohlene Läufe

1. **Owner-Entscheidungslauf** — YELLOW_REVIEW-Entscheidungen treffen (12 Issues)
2. **Phase 0 Abschluss** — #51 (Templates) und #52 (Code-Konventionen) umsetzen
3. **Phase 1 Start** — Policy Parser #1 implementieren (erster Code-Commit)
4. **Phase 3/4 Spezifikation** — #53-#56 umsetzen (n8n-Bridge, Paperclip-Rollen, Dashboard)
5. **CI/CD-Planung** — GitHub Actions erst nach lokaler Build-Stabilität aktivieren (Safety-Regel #9)

---

*Report erstellt am 2026-07-05 durch Issue Orchestrator im Rahmen des Governance Polish*
