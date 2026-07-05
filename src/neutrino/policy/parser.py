"""Policy Parser — deterministic extraction of structured scope data from policy texts.

This module implements the core parsing logic for bug bounty program policies.
It extracts in-scope domains, out-of-scope exclusions, rate limits, and rules
using deterministic pattern matching (regex). No LLM-based decisions are made.

All network requests are made through httpx with explicit timeouts.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx

from neutrino.models.policy import AutomationPolicy, PolicyRule, RateLimit, ScopeEntry, ScopePolicy


class PolicyParseError(Exception):
    """Raised when policy parsing fails for any reason."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class PolicyParser:
    """Deterministic parser for bug bounty program policies.

    Usage:
        parser = PolicyParser()
        policy = parser.parse_from_url("https://hackerone.com/example")
        print(policy.in_scope)

    All parsing is regex-based. No LLM, no semantic analysis.
    """

    _RATE_LIMIT_PATTERNS = [
        (
            re.compile(
                r"(\d+(?:\.\d+)?)\s*(?:requests?\s*per\s*second|reqs?/s(?:ec)?)", re.IGNORECASE
            ),
            "requests_per_second",
        ),
        (
            re.compile(r"(\d+)\s*(?:requests?\s*per\s*minute|reqs?/m(?:in)?)", re.IGNORECASE),
            "requests_per_minute",
        ),
        (
            re.compile(r"(\d+)\s*(?:requests?\s*per\s*hour|reqs?/h(?:our)?)", re.IGNORECASE),
            "requests_per_hour",
        ),
        (
            re.compile(r"(\d+)\s*(?:requests?\s*per\s*day|reqs?/d(?:ay)?)", re.IGNORECASE),
            "requests_per_day",
        ),
        (re.compile(r"(\d+)\s*concurrent\s*requests?", re.IGNORECASE), "concurrent_requests"),
    ]

    _MAX_TEXT_SIZE = 10 * 1024 * 1024  # 10 MB

    def parse_from_url(self, url: str, *, timeout: int = 30) -> ScopePolicy:
        """Fetch and parse a policy page from a URL.

        Args:
            url: The URL of the bug bounty policy page. Must use HTTPS.
            timeout: Request timeout in seconds.

        Returns:
            A parsed ScopePolicy object.

        Raises:
            PolicyParseError: If the URL is invalid, unreachable, or returns an error.
        """
        if not url.startswith("https://"):
            raise PolicyParseError(f"Only HTTPS URLs are supported. Got: {url}")

        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PolicyParseError(f"Failed to fetch policy from {url}: {exc}") from exc

        return self.parse_from_text(
            text=response.text,
            source_label=url,
        )

    def parse_from_text(self, text: str, *, source_label: str = "direct-input") -> ScopePolicy:
        """Parse policy from raw text (no network request).

        Args:
            text: The raw policy text (HTML or plain text).
            source_label: A label for the source (URL or identifier).

        Returns:
            A parsed ScopePolicy object.

        Raises:
            PolicyParseError: If the text is empty or exceeds size limits.
        """
        if not text or not text.strip():
            raise PolicyParseError("Empty policy text — nothing to parse.")

        if len(text.encode()) > self._MAX_TEXT_SIZE:
            raise PolicyParseError(
                f"Policy text exceeds maximum size of {self._MAX_TEXT_SIZE // (1024 * 1024)} MB."
            )

        # Strip HTML tags for text-based extraction
        clean_text = self._strip_html(text)

        return ScopePolicy(
            source_url=source_label,
            source_fetched_at=datetime.utcnow(),
            program_name=self._extract_program_name(clean_text),
            in_scope=self._extract_in_scope(clean_text),
            out_of_scope=self._extract_out_of_scope(clean_text),
            rate_limits=self._extract_rate_limits(clean_text),
            rules=self._extract_rules(clean_text),
            automation_policy=self._extract_automation_policy(clean_text),
            allowed_test_types=self._extract_test_types(clean_text, kind="allowed"),
            prohibited_test_types=self._extract_test_types(clean_text, kind="prohibited"),
            raw_text=text,
        )

    # ------------------------------------------------------------------
    # Private extraction methods
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags and decode common entities.

        Args:
            text: Raw HTML text.

        Returns:
            Clean text with HTML tags removed.
        """
        import html

        # Remove script/style blocks entirely
        clean = re.sub(
            r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Remove remaining HTML tags
        clean = re.sub(r"<[^>]+>", " ", clean)
        # Decode HTML entities
        clean = html.unescape(clean)
        # Normalize whitespace: collapse spaces but preserve newlines
        clean = re.sub(r"[ \t]+", " ", clean)  # Collapse horizontal whitespace
        clean = re.sub(r"\n{3,}", "\n\n", clean)  # Collapse 3+ newlines to 2
        clean = clean.strip()
        return clean

    def _extract_program_name(self, text: str) -> str | None:
        """Try to extract the program name from the text.

        Heuristic: Look for common header patterns.
        """
        # Try to find a heading that looks like a program name
        patterns = [
            # "# Example Corp Bug Bounty Program" — Markdown heading (capture entire heading)
            r"^#\s+(.+?)(?:\s*\n|$)",
            # "Bugcrowd Program: Acme Inc" or "Program: Acme Inc" — platform format
            r"(?:Bug Bounty Program|Program)\s*[:–-]\s*(.+?)(?:\s*\n|$)",
            # "Welcome to the X Bug Bounty Program"
            r"Welcome to the\s+(.+?)\s+(?:Bug Bounty|program)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                name = match.group(1).strip()
                # Only accept reasonable-length names
                if 3 <= len(name) <= 120:
                    return name
        return None

    def _extract_in_scope(self, text: str) -> list[ScopeEntry]:
        """Extract in-scope assets from policy text.

        Looks for sections labeled "In Scope", "Scope", "Targets", etc.
        and extracts domain, IP, URL, and wildcard patterns from them.
        """
        section = self._find_section(
            text,
            start_markers=["in scope", "in-scope", "scope", "targets", "eligible"],
            end_markers=[
                "out of scope",
                "out-of-scope",
                "exclusions",
                "rules",
                "requirements",
                "bounty",
            ],
        )
        if not section:
            return []

        entries = self._extract_scope_entries(section, source_section="in_scope")
        # Deduplicate by pattern
        seen: set[str] = set()
        deduped: list[ScopeEntry] = []
        for entry in entries:
            if entry.pattern.lower() not in seen:
                seen.add(entry.pattern.lower())
                deduped.append(entry)
        return deduped

    def _extract_out_of_scope(self, text: str) -> list[ScopeEntry]:
        """Extract out-of-scope assets from policy text.

        Looks for sections labeled "Out of Scope", "Exclusions",
        "Ineligible", "Prohibited Targets", etc.
        """
        section = self._find_section(
            text,
            start_markers=[
                "out of scope",
                "out-of-scope",
                "exclusion",
                "not in scope",
                "excluded",
                "ineligible",
                "prohibited targets",
                "not eligible",
            ],
            end_markers=[
                "rules",
                "requirements",
                "bounty",
                "reporting",
                "disclosure",
                "safe harbor",
            ],
        )
        if not section:
            return []

        entries = self._extract_scope_entries(section, source_section="out_of_scope")
        # Deduplicate by pattern
        seen: set[str] = set()
        deduped: list[ScopeEntry] = []
        for entry in entries:
            if entry.pattern.lower() not in seen:
                seen.add(entry.pattern.lower())
                deduped.append(entry)
        return deduped

    def _extract_rate_limits(self, text: str) -> RateLimit | None:
        """Extract rate-limit information from policy text."""
        rps: float | None = None
        rpm: int | None = None
        rph: int | None = None
        rpd: int | None = None
        concurrent: int | None = None

        for pattern, key in self._RATE_LIMIT_PATTERNS:
            match = pattern.search(text)
            if match:
                value = float(match.group(1)) if "." in match.group(1) else int(match.group(1))
                if key == "requests_per_second":
                    rps = float(value)
                elif key == "requests_per_minute":
                    rpm = int(value)
                elif key == "requests_per_hour":
                    rph = int(value)
                elif key == "requests_per_day":
                    rpd = int(value)
                elif key == "concurrent_requests":
                    concurrent = int(value)

        if rps is None and rpm is None and rph is None and rpd is None and concurrent is None:
            return None

        return RateLimit(
            requests_per_second=rps,
            requests_per_minute=rpm,
            requests_per_hour=rph,
            requests_per_day=rpd,
            concurrent_requests=concurrent,
        )

    def _extract_automation_policy(self, text: str) -> AutomationPolicy:
        """Extract automation policy from policy text.

        Conservative rules:
        - If automation is explicitly prohibited → "prohibited"
        - If automation requires prior approval → "requires_approval"
        - If automation is explicitly allowed → "allowed"
        - If nothing found → "unknown"
        - Contradictory statements → most restrictive wins
        """

        prohibited_patterns = [
            re.compile(
                r"automated\s+(?:scanning|testing|tools?|scanners?)\s+(?:is|are)\s+prohibited",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:do\s+not|no|never)\s+(?:use\s+)?automated\s+(?:scanning|testing|tools?|scanners?)",
                re.IGNORECASE,
            ),
            re.compile(
                r"automated\s+(?:scanning|testing|tools?|scanners?)\s+(?:is|are)\s+not\s+(?:allowed|permitted)",
                re.IGNORECASE,
            ),
            re.compile(
                r"prohibit(?:ed|s)\s+automated\s+(?:scanning|testing|tools?)", re.IGNORECASE
            ),
            re.compile(
                r"without\s+(?:prior|explicit)\s+(?:written\s+)?(?:permission|approval|consent|authori[sz]ation)",
                re.IGNORECASE,
            ),
            re.compile(
                r"no\s+automated\s+(?:tools?|scanning|testing)\s+(?:without|unless)", re.IGNORECASE
            ),
        ]

        requires_approval_patterns = [
            re.compile(
                r"automated\s+(?:testing|scanning|tools?)\s+(?:requires?|needs?|must\s+have)\s+(?:prior|explicit|written)\s+(?:approval|permission|consent|authori[sz]ation)",
                re.IGNORECASE,
            ),
            re.compile(
                r"requires?\s+(?:prior|explicit|written)\s+(?:approval|permission|consent|authori[sz]ation)\s+(?:for|to\s+use)\s+automated",
                re.IGNORECASE,
            ),
            re.compile(
                r"automated\s+(?:testing|scanning|tools?)\s+(?:is|are)\s+permitted\s+(?:only|solely)\s+with\s+(?:prior|explicit|written)",
                re.IGNORECASE,
            ),
            re.compile(
                r"must\s+(?:obtain|get|have|seek)\s+(?:prior|explicit|written)\s+(?:written\s+)?(?:approval|permission)",
                re.IGNORECASE,
            ),
            re.compile(
                r"contact\s+(?:us|the\s+team)\s+(?:before|prior\s+to)\s+(?:automated|using\s+automated)",
                re.IGNORECASE,
            ),
        ]

        allowed_patterns = [
            re.compile(
                r"automated\s+(?:testing|scanning|tools?)\s+(?:is|are)\s+(?:allowed|permitted|welcome|encouraged)",
                re.IGNORECASE,
            ),
            re.compile(
                r"automation\s+(?:is|are)\s+(?:allowed|permitted|welcome|encouraged)", re.IGNORECASE
            ),
            re.compile(
                r"(?:you\s+may|feel\s+free\s+to)\s+use\s+automated\s+(?:testing|scanning|tools?)",
                re.IGNORECASE,
            ),
            re.compile(
                r"automated\s+(?:testing|scanning|tools?)\s+(?:is|are)\s+(?:allowed|permitted)\s+within\s+(?:the\s+)?(?:published|rate\s+limit)",
                re.IGNORECASE,
            ),
        ]

        # Check prohibited first (highest priority)
        for pattern in prohibited_patterns:
            match = pattern.search(text)
            if match:
                return AutomationPolicy(status="prohibited", evidence=match.group(0))

        # Check "without prior approval" patterns -- these are prohibited
        # unless paired with a "can be allowed" clause
        for pattern in prohibited_patterns[4:]:  # The last two patterns relate to approval
            match = pattern.search(text)
            if match:
                return AutomationPolicy(status="prohibited", evidence=match.group(0))

        # Check requires_approval
        for pattern in requires_approval_patterns:
            match = pattern.search(text)
            if match:
                return AutomationPolicy(status="requires_approval", evidence=match.group(0))

        # Check allowed (lowest priority — only if nothing restrictive matched)
        for pattern in allowed_patterns:
            match = pattern.search(text)
            if match:
                return AutomationPolicy(status="allowed", evidence=match.group(0))

        # Default: unknown
        return AutomationPolicy(status="unknown")

    _KNOWN_PROHIBITED_TEST_TYPES: dict[str, re.Pattern[str]] = {
        "brute_force": re.compile(r"(?:brute[\s-]*force|bruteforce)", re.IGNORECASE),
        "credential_stuffing": re.compile(r"credential[\s-]*stuffing", re.IGNORECASE),
        "social_engineering": re.compile(r"social[\s-]*engineering", re.IGNORECASE),
        "phishing": re.compile(r"phishing", re.IGNORECASE),
        "spam": re.compile(r"\bspam\b", re.IGNORECASE),
        "ddos": re.compile(r"\bddos\b|denial[\s-]*of[\s-]*service", re.IGNORECASE),
        "destructive_testing": re.compile(r"destructive[\s-]*testing", re.IGNORECASE),
        "physical_attacks": re.compile(r"physical[\s-]*(?:attack|access|security)", re.IGNORECASE),
        "data_exfiltration": re.compile(
            r"(?:data[\s-]*exfiltration|exfiltrate?\s+(?:data|information))", re.IGNORECASE
        ),
        "accessing_user_data": re.compile(
            r"access(?:ing)?\s+(?:user|personal|customer)\s+data", re.IGNORECASE
        ),
        "automated_scanning": re.compile(
            r"(?:do\s+not|no|never|prohibited)\s+(?:use\s+)?automated\s+(?:scanning|testing|tools?)",
            re.IGNORECASE,
        ),
        "social_media_phishing": re.compile(
            r"social[\s-]*media[\s-]*(?:phishing|scams?)", re.IGNORECASE
        ),
        "website_defacement": re.compile(r"(?:website\s+)?deface(?:ment|ing)", re.IGNORECASE),
        "ransomware": re.compile(r"ransomware", re.IGNORECASE),
        "port_scanning_out_of_scope": re.compile(
            r"port[\s-]*scan(?:ning)?\s+(?:of|on|against)\s+(?:systems?\s+)?(?:outside|out[\s-]*of[\s-]*scope)",
            re.IGNORECASE,
        ),
    }

    _KNOWN_ALLOWED_TEST_TYPES: dict[str, re.Pattern[str]] = {
        "web_application_testing": re.compile(
            r"web[\s-]*(?:application|app)[\s-]*test(?:ing)?", re.IGNORECASE
        ),
        "api_testing": re.compile(r"\bapi[\s-]*test(?:ing)?", re.IGNORECASE),
        "authenticated_testing": re.compile(
            r"authenticated[\s-]*test(?:ing)?(?:\s+with\s+test\s+accounts?)?", re.IGNORECASE
        ),
        "non_destructive_testing": re.compile(
            r"non[\s-]*destructive[\s-]*test(?:ing)?", re.IGNORECASE
        ),
        "rate_limited_automated_testing": re.compile(
            r"rate[\s-]*limited?\s+automated\s+test(?:ing)?", re.IGNORECASE
        ),
        "test_accounts": re.compile(r"(?:create|use|register)\s+test\s+accounts?", re.IGNORECASE),
        "manual_testing": re.compile(r"manual[\s-]*test(?:ing)?", re.IGNORECASE),
        "code_review": re.compile(r"(?:code|source)[\s-]*review", re.IGNORECASE),
        "configuration_analysis": re.compile(r"configuration[\s-]*analysis", re.IGNORECASE),
        "vulnerability_scanning": re.compile(r"vulnerability[\s-]*scan(?:ning)?", re.IGNORECASE),
    }

    def _extract_test_types(self, text: str, *, kind: str = "prohibited") -> list[str]:
        """Extract test types from policy text.

        Args:
            text: The clean policy text.
            kind: "allowed" or "prohibited" — which types to extract.

        Returns:
            List of matched test type keys (no duplicates).
        """
        patterns = (
            self._KNOWN_PROHIBITED_TEST_TYPES
            if kind == "prohibited"
            else self._KNOWN_ALLOWED_TEST_TYPES
        )
        found: list[str] = []
        seen: set[str] = set()

        for key, pattern in patterns.items():
            if pattern.search(text) and key not in seen:
                found.append(key)
                seen.add(key)

        return found

    def _extract_rules(self, text: str) -> list[PolicyRule]:
        """Extract testing rules from policy text.

        Looks for bullet points or numbered lists in the rules section.
        """
        section = self._find_section(
            text,
            start_markers=[
                "rules",
                "requirements",
                "expectations",
                "guidelines",
                "do not",
                "prohibited",
            ],
            end_markers=["reporting", "disclosure", "safe harbor", "bounty", "rewards", "contact"],
        )
        if not section:
            return []

        rules: list[PolicyRule] = []

        # Find bullet points or numbered items
        lines = section.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Match bullet points: "- ", "* ", "• ", "1. ", etc.
            bullet_match = re.match(r"^(?:[-*•]|\d+\.)\s+(.+)$", stripped)
            if bullet_match:
                desc = bullet_match.group(1).strip()
                if len(desc) > 10:  # Filter out too-short entries
                    is_blocking = any(
                        keyword in desc.lower()
                        for keyword in [
                            "do not",
                            "prohibited",
                            "must not",
                            "never",
                            "forbidden",
                            "not allowed",
                        ]
                    )
                    category = self._classify_rule(desc)
                    rules.append(
                        PolicyRule(description=desc, category=category, is_blocking=is_blocking)
                    )

            # Also catch standalone lines that look like rules (in a rules section)
            elif len(stripped) > 30 and not re.match(r"^#+\s", stripped):
                # It might be a paragraph about a specific rule
                # Only if we're in a clearly identified rules section
                pass  # For now, only capture bullet points for reliability

        return rules

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _find_section(text: str, *, start_markers: list[str], end_markers: list[str]) -> str | None:
        """Find a section of text between start and end markers.

        Args:
            text: The full text to search.
            start_markers: Section header keywords (case-insensitive match).
            end_markers: Keywords that indicate the end of the section.

        Returns:
            The matched section text, or None if not found.
        """
        text_lower = text.lower()

        # Find the earliest start marker
        start_idx = -1
        start_len = 0
        for marker in start_markers:
            idx = text_lower.find(marker)
            if idx != -1 and (start_idx == -1 or idx < start_idx):
                start_idx = idx
                start_len = len(marker)

        if start_idx == -1:
            return None

        # Find the earliest end marker after start
        section_start = start_idx + start_len
        end_idx = -1
        for marker in end_markers:
            idx = text_lower.find(marker, section_start)
            if idx != -1 and (end_idx == -1 or idx < end_idx):
                end_idx = idx

        if end_idx == -1:
            # Take the next ~2000 characters
            return text[section_start : section_start + 2000].strip()

        return text[section_start:end_idx].strip()

    # ------------------------------------------------------------------
    # Regex patterns for scope extraction (compiled once at class level)
    # ------------------------------------------------------------------

    _IP_RANGE_PATTERN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})\b")

    _URL_PATTERN = re.compile(
        r"(?:(?:https?://)?(?:\*\.)?"
        r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
        r"[a-zA-Z]{2,}"
        r"(?:/[^\s,;)\]]*)?)"
    )

    _DOMAIN_PATTERN_SIMPLE = re.compile(
        r"(?:(?:https?://)?(?:\*\.)?"
        r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
        r"[a-zA-Z]{2,})"
    )

    @staticmethod
    def _extract_scope_entries(text: str, *, source_section: str = "unknown") -> list[ScopeEntry]:
        """Extract scope entries (domains, IPs, URLs, wildcards) from text.

        Processes the text line-by-line to capture IP ranges, URLs with paths,
        wildcard domains, and plain domains. Each entry is classified with an
        appropriate asset type and source section reference.

        Args:
            text: The section text to extract entries from.
            source_section: Label for the policy section (e.g. "in_scope",
                "out_of_scope") — preserved on each entry for audit.

        Returns:
            List of ScopeEntry objects for all recognised patterns.
        """
        entries: list[ScopeEntry] = []

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Strip common bullet / list markers
            line_clean = re.sub(r"^[-*••]\s*", "", line).strip()
            if not line_clean:
                continue

            # --- 1) IP range ---
            ip_match = PolicyParser._IP_RANGE_PATTERN.search(line_clean)
            if ip_match:
                entries.append(
                    ScopeEntry(
                        pattern=ip_match.group(1),
                        type="ip_range",
                        is_wildcard=False,
                        source_section=source_section,
                        bounty_eligible=(source_section == "in_scope"),
                    )
                )
                continue

            # --- 2) URL (domain with optional path) ---
            url_match = PolicyParser._URL_PATTERN.search(line_clean)
            if url_match:
                raw = url_match.group(0)
                # Normalize: strip protocol
                if "://" in raw:
                    raw = raw.split("://", 1)[1]

                raw = raw.rstrip("/")
                is_wildcard = raw.startswith("*.")
                has_path = "/" in raw

                if is_wildcard:
                    entry_type = "wildcard_domain"
                elif has_path and ("/api" in raw.lower() or "/v" in raw):
                    entry_type = "api"
                elif has_path:
                    entry_type = "url"
                else:
                    entry_type = "domain"

                entries.append(
                    ScopeEntry(
                        pattern=raw.strip(),
                        type=entry_type,
                        is_wildcard=is_wildcard,
                        source_section=source_section,
                        bounty_eligible=(source_section == "in_scope"),
                    )
                )
                continue

            # --- 3) Plain domain (fallback) ---
            domain_match = PolicyParser._DOMAIN_PATTERN_SIMPLE.search(line_clean)
            if domain_match:
                domain = domain_match.group(0)
                if "://" in domain:
                    domain = domain.split("://", 1)[1]
                domain = domain.strip()
                is_wildcard = domain.startswith("*.")
                entries.append(
                    ScopeEntry(
                        pattern=domain,
                        type="wildcard_domain" if is_wildcard else "domain",
                        is_wildcard=is_wildcard,
                        source_section=source_section,
                        bounty_eligible=(source_section == "in_scope"),
                    )
                )

        return entries

    @staticmethod
    def _classify_rule(description: str) -> str:
        """Classify a rule into a category based on keywords.

        Args:
            description: The rule description text.

        Returns:
            Category string: "testing", "reporting", "disclosure", or "general".
        """
        desc_lower = description.lower()
        if any(
            kw in desc_lower
            for kw in ["scan", "test", "automated", "tool", "brute force", "exploit"]
        ):
            return "testing"
        if any(kw in desc_lower for kw in ["report", "submit", "bug", "vulnerability"]):
            return "reporting"
        if any(kw in desc_lower for kw in ["disclose", "publish", "public", "responsible"]):
            return "disclosure"
        return "general"
