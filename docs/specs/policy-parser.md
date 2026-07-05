# Specification: Policy Parser

> Status: DRAFT
> Version: 0.1.0
> Erstellt: 2026-07-05
> Issue: #1
> Speckit Phase: 2 (Specify)

---

## 1. Overview

The Policy Parser is the entry module of the Neutrino Safety Core. It reads bug bounty program policies (in text or HTML form) and extracts structured `ScopePolicy` data. This data is the foundation for all subsequent scope validation, rate-limit enforcement, and safety decisions.

## 2. User Stories

### US-1: Parse a Bug Bounty Policy Page
**As a** Neutrino operator  
**I want to** feed a bug bounty program policy URL or text to the parser  
**So that** I receive a structured `ScopePolicy` object with in-scope domains, rules, and rate limits  

**Acceptance Criteria:**
- Parser accepts a URL (string) or raw text (string) as input
- Parser returns a `ScopePolicy` object (or raises a descriptive error if parsing fails)
- `ScopePolicy.source_url` and `ScopePolicy.source_fetched_at` are always populated
- The original text is preserved in `ScopePolicy.raw_text` for audit trail

### US-2: Extract In-Scope and Out-of-Scope Assets
**As a** Neutrino operator  
**I want to** know which targets are in scope and which are explicitly excluded  
**So that** I can configure ScopeGuard correctly  

**Acceptance Criteria:**
- `ScopePolicy.in_scope` contains parsed entries with `pattern`, `type`, `description`
- `ScopePolicy.out_of_scope` contains parsed entries with the same structure
- Wildcard patterns (e.g., `*.example.com`) are recognized
- Unknown/unparseable entries are marked with `type="unknown"` (not silently dropped)

### US-3: Extract Rate Limits
**As a** Neutrino operator  
**I want to** know the program's rate limits  
**So that** ScopeGuard can enforce them automatically  

**Acceptance Criteria:**
- `ScopePolicy.rate_limits` is parsed when the policy specifies request limits
- `RateLimit.requests_per_second`, `requests_per_hour`, `concurrent_requests` are extracted if present
- If no rate limits are found, `rate_limits` is `None` (not an error)

### US-4: Extract Rules
**As a** Neutrino operator  
**I want to** know the program's testing rules  
**So that** violations can be blocked before they occur  

**Acceptance Criteria:**
- `ScopePolicy.rules` contains parsed `PolicyRule` entries
- Each rule has a `description`, `category`, and `is_blocking` flag
- Blocking rules (e.g., "no automated scanning") are flagged with `is_blocking=True`

## 3. Data Model

### ScopePolicy
```python
class ScopePolicy(BaseModel):
    source_url: str
    source_fetched_at: datetime
    program_name: Optional[str] = None
    platform: Optional[str] = None
    in_scope: list[ScopeEntry] = []
    out_of_scope: list[ScopeEntry] = []
    rate_limits: Optional[RateLimit] = None
    rules: list[PolicyRule] = []
    raw_text: str = ""
```

### ScopeEntry
```python
class ScopeEntry(BaseModel):
    pattern: str
    type: str = "domain"
    description: Optional[str] = None
    bounty_eligible: bool = False
```

### RateLimit
```python
class RateLimit(BaseModel):
    requests_per_second: Optional[float] = None
    requests_per_hour: Optional[int] = None
    concurrent_requests: Optional[int] = None
    auto_throttle: bool = True
```

### PolicyRule
```python
class PolicyRule(BaseModel):
    description: str
    category: str = "general"
    is_blocking: bool = False
```

## 4. Parser Interface

```python
class PolicyParser:
    def parse_from_url(self, url: str, timeout: int = 30) -> ScopePolicy:
        """Fetch and parse a policy page from a URL."""

    def parse_from_text(self, text: str, source_label: str = "direct-input") -> ScopePolicy:
        """Parse policy from raw text (no network request)."""

    def _extract_in_scope(self, text: str) -> list[ScopeEntry]:
        """Extract in-scope assets from text."""

    def _extract_out_of_scope(self, text: str) -> list[ScopeEntry]:
        """Extract out-of-scope assets from text."""

    def _extract_rate_limits(self, text: str) -> Optional[RateLimit]:
        """Extract rate-limit information from text."""

    def _extract_rules(self, text: str) -> list[PolicyRule]:
        """Extract testing rules from text."""
```

## 5. Non-Goals (Explicitly Excluded)

- No active network requests against real targets (except policy page itself)
- No LLM-based scope decisions or semantic analysis
- No automatic scope approval or denial
- No modification of original policy text
- No HTML rendering/JavaScript execution (static HTML parsing only)

## 6. Edge Cases

| Scenario | Expected Behavior |
|----------|------------------|
| Empty policy text | Raise `PolicyParseError("Empty policy text")` |
| URL unreachable (timeout) | Raise `PolicyParseError("Failed to fetch policy: <reason>")` |
| Policy with no in-scope section | Return `ScopePolicy` with empty `in_scope` list |
| Malformed HTML | Attempt to extract text content; mark unparseable entries as `type="unknown"` |
| Policy with only out-of-scope entries | Return `ScopePolicy` with `in_scope=[]`, populate `out_of_scope` |
| Duplicate scope entries | Deduplicate by `pattern` field |

## 7. Security Considerations

- **Default-Deny:** Unknown policy statements are marked as `UNKNOWN`, not silently accepted
- **No active validation:** Parser does not probe targets to verify scope claims
- **Audit Trail:** `raw_text` is preserved for all downstream audit and evidence requirements
- **Input Sanitization:** URLs are validated (scheme must be `https`); text is size-limited (default 10 MB)
- **No Credentials:** Parser never sends authentication headers or cookies

## 8. Acceptance Tests

1. **Happy Path:** Parse a well-formed HackerOne-style policy → all fields populated
2. **Empty Text:** Pass empty string → `PolicyParseError` raised
3. **Fetch Error:** Pass unreachable URL → `PolicyParseError` raised with cause
4. **Determinism:** Same input twice → identical `ScopePolicy` output
5. **Partial Data:** Policy with only rules, no scope → `ScopePolicy` returned with partial data

## 9. Dependencies

| Dependency | Purpose |
|-----------|---------|
| `httpx` | HTTP client for fetching policy pages |
| `pydantic` | Data model validation and serialization |
| `datetime` | Source timestamping (stdlib) |
| `re` | Text pattern extraction (stdlib) |

## 10. Future Extensions (Not in Scope for #1)

- Multi-format support (JSON policy files, API responses)
- Caching of fetched policies
- Diffing of policy changes over time
- Machine-learning-based extraction (requires YELLOW_REVIEW)
