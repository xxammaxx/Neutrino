---
name: Bug Report
about: Melde einen Fehler im Neutrino-Code
title: '[Bug] '
labels: ['type:bug', 'status:yellow-review']
assignees: ''
---

## Ziel

Einen reproduzierbaren Fehler im Neutrino-Ökosystem dokumentieren.

## Rolle in der Zielarchitektur

- **Neutrino Core:** Betroffene Safety-Komponente identifizieren
- **n8n Workflow Bridge:** Falls Workflow-bezogen
- **Paperclip Control Plane:** Falls Agent-bezogen

## Sicherheitsklasse

> ⚠️ **WICHTIG:** Bevor du diesen Bug Report einreichst, lies das [Safety Decision Manifest](../blob/main/docs/governance/SAFETY_DECISION_MANIFEST.md).

> **Default-Deny-Regel:** Dieser Bug Report darf KEINE aktiven Security-Tests gegen reale Ziele beschreiben, KEINE Exploit-Details gegen Drittsysteme enthalten und KEINE Credential-Angriffe dokumentieren. Bug-Bounty-relevante Schwachstellen gehören NICHT hierher — nutze dafür das [Security Report Template](?template=security_report.md).

| Klassifikation | Wert |
|----------------|------|
| Sicherheitsklasse | `YELLOW_REVIEW` (muss vor Fix geprüft werden) |
| Betroffene Komponente | `[Neutrino]` / `[n8n]` / `[Paperclip]` / `[Lab]` / `[Report]` |

## Beschreibung

<!-- Klare, präzise Beschreibung des Fehlers -->

## Reproduktion

<!-- Schritt-für-Schritt-Anleitung zur Reproduktion -->

1. 
2. 
3. 

## Erwartetes Verhalten

<!-- Was sollte stattdessen passieren? -->

## Tatsächliches Verhalten

<!-- Was passiert tatsächlich? -->

## Umgebung

| Metadatum | Wert |
|-----------|------|
| Betriebssystem | <!-- z.B. Ubuntu 24.04 --> |
| Python-Version | <!-- z.B. Python 3.11.9 --> |
| Neutrino-Version / Commit | <!-- `git rev-parse HEAD` --> |
| Docker-Version (falls relevant) | <!-- z.B. Docker 26.x --> |

## Evidenz

<!-- Logs, Screenshots, Stack Traces — KEINE Secrets, KEINE Target-URLs von Drittsystemen -->

```
<!-- Stack Trace oder Log-Auszug hier -->
```

## Zusätzlicher Kontext

<!-- Alles Weitere, das relevant sein könnte -->

## Safety Notes

- [ ] Ich bestätige, dass dieser Bug Report KEINE aktiven Security-Tests gegen reale Ziele beschreibt
- [ ] Ich bestätige, dass dieser Bug Report KEINE Credentials oder Secrets enthält
- [ ] Ich bestätige, dass dieser Bug Report sich auf Neutrino-Code bezieht, nicht auf Drittsysteme
