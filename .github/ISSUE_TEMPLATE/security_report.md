---
name: Security Report
about: Melde ein Sicherheitsproblem im Neutrino-Code (NICHT für Drittsystem-Schwachstellen)
title: '[Security] '
labels: ['type:security', 'status:yellow-review']
assignees: ''
---

## ⚠️ WICHTIG — Vor dem Einreichen lesen

### Dieser Security Report ist AUSSCHLIESSLICH für Neutrino-eigenen Code

> **Dieses Repository ist ein Safety-Core-Framework, KEIN Bug-Bounty-Programm.**

Melde hier NUR Sicherheitsprobleme, die den **Neutrino-Code selbst** betreffen:

- Sicherheitslücken in Neutrinos Policy-Parser
- Umgehungen des ScopeGuard
- Fehler im Human-Approval-Workflow
- Audit-Log-Manipulationen
- Unsichere Defaults in Neutrino-Komponenten

**NICHT hierher gehören:**
- Schwachstellen in Drittsystemen (Websites, APIs, Server)
- Bug-Bounty-Findings gegen externe Ziele
- Exploits gegen Produktivsysteme
- Credential-Leaks von Drittanbietern

Verstöße gegen diese Richtlinie werden gelöscht.

---

## Responsible Disclosure

> **Bitte gib uns 90 Tage Zeit zur Behebung, bevor du Details veröffentlichst.**

Falls das Problem kritisch ist und sofortige Aufmerksamkeit erfordert, kontaktiere uns direkt per E-Mail (siehe [SECURITY.md](../blob/main/SECURITY.md)).

---

## Ziel

<!-- Klare Beschreibung des Sicherheitsproblems im Neutrino-Code -->

## Rolle in der Zielarchitektur

<!-- Welche Komponente ist betroffen? -->

- **Neutrino Core:** <!-- z.B. ScopeGuard, Policy-Parser, Human Approval -->
- **n8n Workflow Bridge:** <!-- z.B. MCP-Tool-Exposure -->
- **Paperclip Control Plane:** <!-- z.B. Agent-Permission-Escalation -->
- **Lokale Labs:** <!-- z.B. Container-Escape -->

## Sicherheitsklasse

| Klassifikation | Wert |
|----------------|------|
| Sicherheitsklasse | `RED_BLOCK` (muss vor Veröffentlichung behoben werden) |
| CVSS-Schätzung | <!-- z.B. CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H — NUR Schätzung, keine Behauptung --> |

## Beschreibung

<!-- Detaillierte technische Beschreibung des Problems -->

## Reproduktion

<!-- Schritt-für-Schritt-Anleitung zur Reproduktion (NUR in lokaler Lab-Umgebung!) -->

1. 
2. 
3. 

## Evidenz

<!-- Logs, Code-Snippets, PoC (NUR gegen lokale Labs, NIE gegen reale Ziele) -->

```
<!-- Evidenz hier -->
```

## Auswirkung

<!-- Was ist die potenzielle Auswirkung auf das Neutrino-Ökosystem? -->

## Vorgeschlagene Lösung

<!-- Falls du einen Fix-Vorschlag hast -->

## Safety Notes

- [ ] Dieser Report betrifft AUSSCHLIESSLICH Neutrino-eigenen Code
- [ ] Dieser Report beschreibt KEINE Schwachstellen in Drittsystemen
- [ ] Dieser Report enthält KEINE aktiven Exploits gegen reale Ziele
- [ ] Ich habe die [Security Policy](../blob/main/SECURITY.md) gelesen
- [ ] Ich akzeptiere die 90-Tage Responsible-Disclosure-Frist
