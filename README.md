# Neutrino — Local Safety Core

> **Status:** Pre-Implementation / Architecture & Governance Phase
> **Safety Level:** Default-Deny — alle aktiven Aktionen brauchen Human Approval

## Was ist Neutrino?

Neutrino ist der **lokale Safety Core** des Neutrino-Ökosystems. Es ist die einzige Instanz,
die Sicherheitsentscheidungen trifft. Neutrino implementiert:

- **Policy Parser** — Extrahiert Scope-Regeln aus Bug-Bounty-Programmen
- **ScopeGuard** — Prüft jeden Request gegen die geladene ScopePolicy (Default-Deny)
- **Human Approval** — Erzwingt menschliche Freigabe für aktive Aktionen
- **AuditLog** — Append-only, unveränderliches Log aller Entscheidungen
- **Evidence Oracle** — Prüft Evidenz-Qualität und Reproduzierbarkeit
- **Report Quality Gate** — Blockiert Reports ohne Evidenz

## Zielarchitektur

```text
Paperclip (Agent Control Plane) → Aufgaben & Tickets
        ↓
n8n (Workflow Bridge) → deterministische Workflows
        ↓
NEUTRINO (Safety Core) → entscheidet: GREEN / YELLOW / RED
        ↓
Lokale Labs & Reports → nur nach Freigabe
```

## Wichtige Regeln

1. **Keine** automatische aktive Security-Validierung gegen reale Ziele
2. **Keine** Credential-Angriffe oder Datenexfiltration
3. **Keine** Exploit-Ausführung außerhalb lokaler Labs
4. **Keine** automatische Report-Einreichung
5. **Keine** LLM-Entscheidung über Scope oder Evidence als final
6. **UNKNOWN = Blockieren**

## Dokumentation

- [Zielarchitektur](./docs/architecture/NEUTRINO_N8N_PAPERCLIP_TARGET_ARCHITECTURE.md)
- [Safety Decision Manifest](./docs/governance/SAFETY_DECISION_MANIFEST.md)
- [Issue Alignment Report](./docs/roadmap/NEUTRINO_ISSUE_ALIGNMENT_REPORT.md)

## Aktueller Stand

- Repository: Foundation-Phase (0 Commits, Architektur- und Governance-Dokumente)
- Issues: 49 + 1 Meta-Issue, alle auf Zielarchitektur ausgerichtet
- Builds: Noch keine — Phasen 0-7 geplant

## Erste Schritte

1. Lies das [Safety Decision Manifest](./docs/governance/SAFETY_DECISION_MANIFEST.md)
2. Prüfe die [Zielarchitektur](./docs/architecture/NEUTRINO_N8N_PAPERCLIP_TARGET_ARCHITECTURE.md)
3. Sieh dir das [Issue Alignment](./docs/roadmap/NEUTRINO_ISSUE_ALIGNMENT_REPORT.md) an
4. Triff YELLOW_REVIEW-Entscheidungen im Meta-Issue #50

## Lizenz

Noch nicht festgelegt.
