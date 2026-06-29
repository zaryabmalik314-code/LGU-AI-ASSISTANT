"""
Policy Scraper — Phase 7.

Fetches LGU / HEC admission policy pages and normalises their content into
a list of ScrapedRule dicts that the differ can compare against the DB.

Design principles:
  - Pure function surface: scrape_sources() takes a list of SourceConfig and
    returns a list of ScrapedRule.  No DB access here.  The scheduler wires DB.
  - Every ScrapedRule carries the raw text it was parsed from, so a human
    reviewer can always verify the diff against the original source.
  - On ANY fetch/parse error the source is skipped and logged — scraper errors
    must never propagate to the API or break the scheduler loop.
  - Normalisation is intentionally simple (regex + heuristics).  If LGU
    publishes a structured JSON feed in future, replace _parse_page() only.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from datetime import date

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15  # seconds
USER_AGENT = "LGU-PolicyBot/1.0 (internal; policy-update-pipeline)"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SourceConfig:
    """One URL to watch, associated with a program in our DB."""
    url: str
    program_id: Optional[int]       # None if program not yet in DB
    program_name: str               # human label for logging / diff summary


# Default sources — extend this list as more pages are identified.
# URLs are illustrative; update when LGU publishes real structured pages.
DEFAULT_SOURCES: list[SourceConfig] = [
    SourceConfig(
        url="https://www.lgu.edu.pk/admissions/",
        program_id=None,
        program_name="LGU General Admissions",
    ),
    SourceConfig(
        url="https://www.hec.gov.pk/english/pages/admissions.aspx",
        program_id=None,
        program_name="HEC Admission Policy",
    ),
]


# ---------------------------------------------------------------------------
# Scraped data model
# ---------------------------------------------------------------------------

@dataclass
class ScrapedRule:
    """Normalised admission rule as seen on the source page."""
    source_url: str
    program_id: Optional[int]
    program_name: str

    # Parsed fields — None means the field was not found on the page.
    min_matric_pct: Optional[float]
    min_inter_pct: Optional[float]
    allowed_streams: list[str]
    required_subjects: list[str]

    # Provenance
    scraped_on: date
    raw_text: str           # excerpt of page text used for parsing (for audit)
    parse_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

def _fetch_page(url: str) -> str:
    """Return page text or raise requests.RequestException."""
    resp = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

_MATRIC_PATTERN = re.compile(
    r"matric(?:ulation)?\s*(?:marks|percentage|%|pct)[^0-9]*(\d{2,3})\s*%?",
    re.IGNORECASE,
)
_INTER_PATTERN = re.compile(
    r"inter(?:mediate)?\s*(?:marks|percentage|%|pct)[^0-9]*(\d{2,3})\s*%?",
    re.IGNORECASE,
)
_STREAM_KEYWORDS: dict[str, str] = {
    "pre-engineering": "Pre-Engineering",
    "pre engineering": "Pre-Engineering",
    "ics": "ICS",
    "pre-medical": "Pre-Medical",
    "pre medical": "Pre-Medical",
    "humanities": "Humanities",
    "commerce": "Commerce",
    "general science": "General Science",
    "arts": "Arts",
}
_SUBJECT_KEYWORDS = [
    "Mathematics", "Physics", "Chemistry", "Biology",
    "Computer Science", "English", "Statistics", "Economics",
]


def _extract_percentage(pattern: re.Pattern, text: str) -> Optional[float]:
    m = pattern.search(text)
    if m:
        val = float(m.group(1))
        if 30.0 <= val <= 100.0:    # sanity range
            return val
    return None


def _extract_streams(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for keyword, canonical in _STREAM_KEYWORDS.items():
        if keyword in lower and canonical not in found:
            found.append(canonical)
    return found


def _extract_subjects(text: str) -> list[str]:
    return [s for s in _SUBJECT_KEYWORDS if s.lower() in text.lower()]


def _extract_text_from_html(html: str) -> str:
    """Very light HTML strip — no external deps (BeautifulSoup optional upgrade)."""
    # Remove script/style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Strip tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Core parse function
# ---------------------------------------------------------------------------

def _parse_page(html: str, source: SourceConfig, today: date) -> ScrapedRule:
    text = _extract_text_from_html(html)
    # Keep only a relevant excerpt (first 4000 chars) to avoid storing huge blobs
    excerpt = text[:4000]

    warnings: list[str] = []

    matric = _extract_percentage(_MATRIC_PATTERN, text)
    inter = _extract_percentage(_INTER_PATTERN, text)
    streams = _extract_streams(text)
    subjects = _extract_subjects(text)

    if matric is None:
        warnings.append("min_matric_pct not found on page")
    if inter is None:
        warnings.append("min_inter_pct not found on page")
    if not streams:
        warnings.append("no recognised stream keywords found on page")

    return ScrapedRule(
        source_url=source.url,
        program_id=source.program_id,
        program_name=source.program_name,
        min_matric_pct=matric,
        min_inter_pct=inter,
        allowed_streams=streams,
        required_subjects=subjects,
        scraped_on=today,
        raw_text=excerpt,
        parse_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_sources(
    sources: list[SourceConfig] | None = None,
    today: date | None = None,
) -> list[ScrapedRule]:
    """
    Fetch and parse each source URL.  Errors per-source are logged and skipped.
    Returns a (possibly empty) list of successfully parsed ScrapedRule objects.
    """
    sources = DEFAULT_SOURCES if sources is None else sources
    today = today or date.today()
    results: list[ScrapedRule] = []

    for source in sources:
        try:
            logger.info(f"Scraping: {source.url}")
            html = _fetch_page(source.url)
            rule = _parse_page(html, source, today)
            if rule.parse_warnings:
                logger.warning(
                    f"Parse warnings for {source.url}: {rule.parse_warnings}"
                )
            results.append(rule)
        except requests.RequestException as e:
            logger.error(f"Fetch failed for {source.url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error scraping {source.url}: {e}", exc_info=True)

    logger.info(f"Scraper finished: {len(results)}/{len(sources)} sources parsed")
    return results