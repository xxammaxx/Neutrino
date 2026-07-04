# Safety Decision Manifest

> Version: 1.0.0
> Erstellt: 2026-07-04
> Status: ACCEPTED — bindend für alle Agenten und Workflows
> Scope: Repository-weit, projektübergreifend für Neutrino-Ökosystem

---

## Präambel

Dieses Manifest definiert die unverhandelbaren Sicherheitsregeln des Neutrino-Ökosystems.
Jeder Agent, jeder Workflow, jede CI-Pipeline und jede menschliche Entscheidung muss
diesen Regeln folgen. Verstöße gegen dieses Manifest sind RED_BLOCK und werden nicht
automatisch ausgeführt.

---

## 1. Fundamentale Sicherheitsprinzipien

### 1.1 Default Deny

**Alles ist verboten, was nicht explizit erlaubt ist.** Jeder Netzwerk-Request,
jede Shell-Ausführung, jede Dateioperation muss durch eine explizite,
deterministische Sicherheitsentscheidung authorisiert sein.

### 1.2 Evidence vor Claims

Kein Security-Finding, keine Severity-Bewertung, kein Report darf als Fakt
behauptet werden ohne reproduzierbare, verifizierbare Evidenz. LLM-Ausgaben
sind Hypothesen, keine Fakten.

### 1.3 Human in the Loop

Jede aktive Aktion (Netzwerk-Request gegen ein Target, Shell-Ausführung,
Exploit-Validierung, Report-Einreichung) benötigt explizite menschliche
Freigabe. Automatische Freigaben sind nicht erlaubt.

### 1.4 Least Privilege

Agenten, Workflows und Tools erhalten nur die minimal notwendigen Berechtigungen.
Kein Agent hat Shell-Zugriff. Kein Agent hat Netzwerk-Zugriff ohne ScopeGuard.

### 1.5 Audit Trail

Jede Sicherheitsentscheidung, jede Agent-Aktion, jeder Workflow-Schritt wird
in einem append-only, unveränderlichen AuditLog protokolliert.

---

## 2. Harte Verbote (RED_BLOCK)

Diese Aktionen sind **immer** blockiert und werden nie automatisch ausgeführt:

| # | Verbot | Begründung |
|---|--------|-----------|
| 1 | Automatische aktive Security-Validierung gegen reale Ziele | Braucht Human Approval + Scope |
| 2 | Credential-Angriffe (Brute Force, Credential Stuffing, etc.) | Immer außerhalb Scope, potenziell illegal |
| 3 | Datenexfiltration von Targets | Datenschutzverletzung, potenziell strafbar |
| 4 | Freie Shell-Kommandos für Agenten | Unkontrollierbare Ausführung |
| 5 | Exploit-Ausführung außerhalb lokaler Labs | Nur in kontrollierten Umgebungen |
| 6 | Automatische Report-Einreichung an Bug-Bounty-Plattformen | Braucht mehrstufige Human Review |
| 7 | LLM-Entscheidung über Scope oder Evidence als final | LLM ist Hypothesengenerator, kein Richter |
| 8 | ScopeGuard oder Human Approval umgehen | Sicherheitsbruch |
| 9 | GitHub Actions oder Remote-CI automatisch aktivieren | Lokale Gates haben Vorrang |
| 10 | Automatische Erlaubnis bei UNKNOWN-Status | UNKNOWN = Blockieren |

---

## 3. Entscheidungsmodell

### 3.1 Klassifikation

| Status | Bedeutung | Automatische Aktion |
|--------|-----------|-------------------|
| `GREEN_SAFE` | Sicher, foundational, keine Risiken | Darf automatisch ausgeführt werden |
| `YELLOW_REVIEW` | Sinnvoll, braucht Owner-Entscheidung | BLOCKIERT bis menschliche Entscheidung |
| `RED_BLOCK` | Gefährlich, unklar, verboten | Immer BLOCKIERT |
| `UNKNOWN` | Nicht genug Informationen | BLOCKIERT, als RED_BLOCK behandelt |

### 3.2 Entscheidungsbaum

```text
Request eingehend
  │
  ├── Request-Typ: Aktiv (Netzwerk, Shell, Exploit)?
  │     │
  │     ├── JA → Human Approval vorhanden?
  │     │         ├── JA → ScopeGuard: In-Scope?
  │     │         │         ├── JA → ALLOW (mit Audit)
  │     │         │         └── NEIN → DENY
  │     │         └── NEIN → DENY (Human Approval fehlt)
  │     │
  │     └── NEIN → Passiv (Read-only, Research)?
  │               ├── ScopeGuard: In-Scope?
  │               │         ├── JA → ALLOW (mit Rate-Limit)
  │               │         └── NEIN → DENY
  │               └── UNKNOWN → DENY
  │
  └── UNKNOWN Request-Typ → DENY
```

---

## 4. Schicht-Verantwortlichkeiten

### 4.1 Neutrino Core

| Verantwortung | Regel |
|--------------|-------|
| Scope-Prüfung | Jeder Request wird gegen ScopePolicy geprüft |
| Default Deny | Unbekannte Ziele werden blockiert |
| Human Approval | Aktive Aktionen brauchen Approval |
| AuditLog | Alle Entscheidungen werden protokolliert |
| Evidence Oracle | Evidenz-Qualität wird geprüft |
| Report Quality Gate | Reports ohne Evidenz werden blockiert |

### 4.2 n8n Workflow Bridge

| Verantwortung | Regel |
|--------------|-------|
| Workflow-Orchestrierung | Darf Workflows nur über Neutrino-APIs starten |
| Human-in-the-loop | Approval-Workflows mit menschlicher Bestätigung |
| MCP-Bridge | Exportiert nur sichere, begrenzte Tools |
| Status/Notifications | Informiert über Systemzustände |
| GitHub-Integration | Synchronisiert Issues und Status |

### 4.3 Paperclip Control Plane

| Verantwortung | Regel |
|--------------|-------|
| Agent-Koordination | Darf Aufgaben verteilen und priorisieren |
| Ticket-Management | Darf Issues öffnen, kommentieren, schließen |
| Budget-Kontrolle | Darf Kostenlimits setzen |
| Goal Alignment | Darf Agenten an Zielen ausrichten |
| KEINE aktiven Tests | Darf keine Security-Tests starten |

---

## 5. MCP-Tool-Sicherheitsgrenzen

### 5.1 Erlaubte MCP-Tools

```json
{
  "tools": [
    {
      "name": "neutrino_scope_check",
      "description": "Prüft ein Target gegen die geladene ScopePolicy",
      "parameters": { "target": "string" },
      "returns": "GREEN_SAFE | YELLOW_REVIEW | RED_BLOCK | UNKNOWN"
    },
    {
      "name": "neutrino_policy_parse",
      "description": "Parst eine Bug-Bounty-Programm-Policy",
      "parameters": { "url": "string" },
      "returns": "ScopePolicy JSON"
    },
    {
      "name": "neutrino_audit_query",
      "description": "Fragt den AuditLog ab",
      "parameters": { "filter": "object" },
      "returns": "AuditEvent[]"
    },
    {
      "name": "neutrino_evidence_export",
      "description": "Exportiert ein Evidence Bundle",
      "parameters": { "bundle_id": "string" },
      "returns": "Bundle path"
    }
  ]
}
```

### 5.2 Verbotene MCP-Tools

- `neutrino_bypass_scope` — existiert nicht
- `neutrino_execute_exploit` — existiert nicht
- `neutrino_submit_report` — existiert nicht
- Shell/Bash-Kommandos — werden nicht exportiert
- Netzwerk-Tools ohne ScopeGuard — werden nicht exportiert

---

## 6. Lab-Regeln

### 6.1 Lokale Labs (erlaubt)

- Juice Shop (OWASP)
- WebGoat (OWASP)
- DVWA (Damn Vulnerable Web Application)
- Absichtlich verwundbare Docker-Container
- Eigene Test-Apps mit dokumentierten Schwachstellen

### 6.2 Lab-Bedingungen

- Ausschließlich lokal (localhost oder isoliertes Netzwerk)
- Jeder Request wird durch ScopeGuard geprüft
- Jeder Schritt wird auditiert
- Human Approval bleibt verpflichtend für aktive Schritte
- Keine Verbindung zu realen Targets

### 6.3 Verbotene Lab-Ziele

- Reale Produktivsysteme ohne explizite schriftliche Freigabe
- Systeme Dritter ohne Authorization
- Ziele außerhalb des dokumentierten Scopes

---

## 7. Änderungen an diesem Manifest

1. Änderungen benötigen ein ADR (Architecture Decision Record)
2. Änderungen benötigen Owner-Approval
3. Änderungen werden im AuditLog protokolliert
4. Änderungen führen zu einer neuen Version dieses Manifests
5. Alte Versionen bleiben als Referenz erhalten

---

## 8. Version-Historie

| Datum | Version | Autor | Änderung |
|-------|---------|-------|----------|
| 2026-07-04 | 1.0.0 | Issue Orchestrator | Initiale Version nach Reality Refresh |
