# Security Policy

## Sicherheitsphilosophie

Neutrino folgt einem **Default-Deny**-Prinzip. Alles ist verboten, was nicht explizit
durch eine deterministische Sicherheitsentscheidung authorisiert wurde.

## Harte Verbote

Die folgenden Aktionen sind **immer** blockiert und werden nie automatisch ausgeführt:

1. Automatische aktive Security-Validierung gegen reale Ziele
2. Credential-Angriffe (Brute Force, Credential Stuffing, etc.)
3. Datenexfiltration von Targets
4. Freie Shell-Kommandos für Agenten
5. Exploit-Ausführung außerhalb lokaler Labs
6. Automatische Report-Einreichung an Bug-Bounty-Plattformen
7. LLM-Entscheidung über Scope oder Evidence als final
8. ScopeGuard oder Human Approval umgehen
9. GitHub Actions oder Remote-CI automatisch aktivieren (lokale Gates haben Vorrang)
10. Automatische Erlaubnis bei UNKNOWN-Status

## Sicherheitsdokumentation

Das vollständige Sicherheitsmodell ist im [Safety Decision Manifest](./docs/governance/SAFETY_DECISION_MANIFEST.md) dokumentiert.

## Meldung von Sicherheitsproblemen

Sicherheits-relevante Probleme im Neutrino-Code bitte als Issue mit dem Label `type:security` melden.

**Wichtig:** Dieses Repository ist ein Safety-Core-Framework, kein Bug-Bounty-Programm.
Meldungen über Schwachstellen in Drittsystemen gehören nicht hierher.

## Scope dieses Repositories

Neutrino ist **ausschließlich** für lokale oder absichtlich verwundbare Lab-Ziele gedacht.
Jegliche Nutzung gegen reale Systeme ohne explizite schriftliche Genehmigung des System-Inhabers
verstößt gegen diese Security Policy.
