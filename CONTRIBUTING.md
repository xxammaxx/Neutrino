# Contributing to Neutrino

## Vor dem ersten Beitrag

1. Lies das [Safety Decision Manifest](./docs/governance/SAFETY_DECISION_MANIFEST.md)
2. Verstehe die [Zielarchitektur](./docs/architecture/NEUTRINO_N8N_PAPERCLIP_TARGET_ARCHITECTURE.md)
3. Prüfe den [Issue Alignment Report](./docs/roadmap/NEUTRINO_ISSUE_ALIGNMENT_REPORT.md)

## Safety Rules für Contributors

- **Default Deny:** Jeder neue Feature-Vorschlag muss Safety-Gates respektieren
- **Keine aktiven Tests gegen reale Ziele:** Nur lokale Labs
- **Human Approval:** Aktive Aktionen brauchen immer menschliche Freigabe
- **Evidence vor Claims:** Kein Code darf Behauptungen ohne Evidenz als Fakten ausgeben
- **UNKNOWN = Blockieren:** Bei Unsicherheit konservativ entscheiden

## Build-Reihenfolge

Die Entwicklung folgt strikt dieser Reihenfolge:

1. **Phase 0** — Repository Foundation
2. **Phase 1** — Neutrino Safety Core
3. **Phase 2** — Storage & Evidence
4. **Phase 3** — n8n Workflow Bridge
5. **Phase 4** — Paperclip Control Plane
6. **Phase 5** — Passive Research
7. **Phase 6** — Local Lab Validation
8. **Phase 7** — Reporting & Dashboard

## Issue-Konventionen

Issues folgen dem Format aus dem [Issue Alignment Report](./docs/roadmap/NEUTRINO_ISSUE_ALIGNMENT_REPORT.md):

- **Titel:** `[Komponente] Beschreibung`
- **Komponenten:** `[Neutrino]`, `[n8n]`, `[Paperclip]`, `[Lab]`, `[Report]`
- **Labels:** `layer:*`, `safety:*`, `status:*`, `type:*`

## Code-Konventionen

- Noch nicht definiert — werden in Phase 1 festgelegt.

## License

Noch nicht festgelegt.
