## Ziel

<!-- Klare, präzise Beschreibung, was dieser PR tut -->

Closes #<!-- Issue-Nummer -->

## Rolle in der Zielarchitektur

<!-- Welche Komponenten sind betroffen? (Mehrfachnennung möglich) -->

- [ ] **Neutrino Core** — Safety-Komponenten
- [ ] **n8n Workflow Bridge** — Workflow-Orchestrierung
- [ ] **Paperclip Control Plane** — Agent-Koordination
- [ ] **Lokale Labs** — Test- und Lab-Infrastruktur
- [ ] **Reporting / Dashboard** — Ausgabe-Features
- [ ] **Foundation / Governance** — Docs, Templates, CI

## Sicherheitsklasse

> ⚠️ **[Safety Decision Manifest](../blob/main/docs/governance/SAFETY_DECISION_MANIFEST.md) — bindend für alle PRs.**

| Klassifikation | Wert |
|----------------|------|
| Sicherheitsklasse | `GREEN_SAFE` / `YELLOW_REVIEW` / `RED_BLOCK` |
| Begründung | <!-- Warum diese Klassifikation? --> |

## Änderungen

<!-- Zusammenfassung der wichtigsten Änderungen -->

### Geänderte Dateien

<!-- `git diff --stat main`-Auszug -->
```
```

## Safety Checkliste (MUSS)

- [ ] **Default-Deny:** Diese Änderung schwächt KEINE bestehenden Safety-Gates
- [ ] **Human Approval:** Aktive Aktionen (Netzwerk, Shell, Exploits) sind NUR mit Human Approval möglich
- [ ] **Scope-Bindung:** Neue Features respektieren ScopeGuard-Grenzen
- [ ] **Keine Secrets:** Commit enthält KEINE Credentials, Tokens, API-Keys, Passwörter
- [ ] **Keine Red Blocks:** Keine der 10 harten Verbote aus dem Safety Decision Manifest werden verletzt
- [ ] **UNKNOWN = Blockiert:** Keine automatische Erlaubnis bei unsicherem Status
- [ ] **Evidence vor Claims:** Security-relevante Änderungen enthalten reproduzierbare Evidenz

## Test Checkliste (MUSS)

- [ ] Neue Tests für alle neuen Funktionen geschrieben
- [ ] Alle bestehenden Tests laufen weiterhin (`pytest` grün)
- [ ] Test-Coverage nicht verschlechtert
- [ ] Edge Cases dokumentiert und getestet

### Testergebnisse

```
<!-- pytest output hier -->
```

## Audit Trail

- [ ] Alle relevanten Entscheidungen sind im Audit-Log protokolliert
- [ ] Issue-Kommentare (Start/End) sind auf GitHub vorhanden

## Nicht-Ziele

<!-- Was wird EXPLIZIT NICHT Teil dieses PRs sein? -->

- 

## Abhängigkeiten

- **Blockiert durch:** 
- **Blockiert:** 

## Zusätzlicher Kontext

<!-- Screenshots, Logs, Architektur-Referenzen -->
