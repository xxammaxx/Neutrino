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

from neutrino.models.policy import PolicyRule, RateLimit, ScopeEntry, ScopePolicy


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
            re.compile(r"(\d+)\s*(?:requests?\s*per\s*hour|reqs?/h(?:our)?)", re.IGNORECASE),
            "requests_per_hour",
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
        rph: int | None = None
        concurrent: int | None = None

        for pattern, key in self._RATE_LIMIT_PATTERNS:
            match = pattern.search(text)
            if match:
                value = float(match.group(1)) if "." in match.group(1) else int(match.group(1))
                if key == "requests_per_second":
                    rps = float(value)
                elif key == "requests_per_hour":
                    rph = int(value)
                elif key == "concurrent_requests":
                    concurrent = int(value)

        if rps is None and rph is None and concurrent is None:
            return None

        return RateLimit(
            requests_per_second=rps,
            requests_per_hour=rph,
            concurrent_requests=concurrent,
        )

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
