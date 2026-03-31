"""Section-aware parser for SEC EDGAR filings (HTML and XBRL)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger(__name__)


class FilingSection(str, Enum):
    """Standard sections found in 10-K and 10-Q filings."""

    BUSINESS = "item_1"
    RISK_FACTORS = "item_1a"
    PROPERTIES = "item_2"
    LEGAL_PROCEEDINGS = "item_3"
    MDA = "item_7"  # Management Discussion & Analysis
    FINANCIAL_STATEMENTS = "item_8"
    CONTROLS = "item_9a"
    OTHER = "other"

    @classmethod
    def from_header(cls, header_text: str) -> FilingSection:
        """Map a section header string to an enum value.

        Uses regex word-boundary matching so that 'item 1' does not
        accidentally match 'item 10', 'item 11', etc.
        """
        text = header_text.lower().strip()
        # Order matters: check longer patterns first (1a before 1, 9a before 9)
        mapping = [
            (r"\bitem\s+1a\b", cls.RISK_FACTORS),
            (r"\bitem\s+9a\b", cls.CONTROLS),
            (r"\bitem\s+1\b", cls.BUSINESS),
            (r"\bitem\s+2\b", cls.PROPERTIES),
            (r"\bitem\s+3\b", cls.LEGAL_PROCEEDINGS),
            (r"\bitem\s+7\b", cls.MDA),
            (r"\bitem\s+8\b", cls.FINANCIAL_STATEMENTS),
        ]
        for pattern, section in mapping:
            if re.search(pattern, text):
                return section
        return cls.OTHER


@dataclass
class ParsedSection:
    """A single extracted section from a filing."""

    section: FilingSection
    title: str
    text: str
    start_offset: int
    end_offset: int
    word_count: int


@dataclass
class ParsedFiling:
    """Result of parsing a complete filing document."""

    accession_number: str
    filing_type: str
    full_text: str
    sections: list[ParsedSection]
    tables: list[dict[str, list[list[str]]]]
    metadata: dict[str, str]


# Regex patterns for identifying section headers in SEC filings
_ITEM_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:ITEM|Item)\s+(\d+[A-Za-z]?)[\.\:\s\—\-]+(.+?)(?:\n|$)",
    re.MULTILINE,
)


class FilingParser:
    """Parse raw HTML/text SEC filings into structured sections."""

    def parse_html(self, html_content: str | bytes, accession_number: str, filing_type: str) -> ParsedFiling:
        """Parse an HTML filing into structured sections.

        Args:
            html_content: Raw HTML content of the filing.
            accession_number: SEC accession number.
            filing_type: e.g. '10-K', '10-Q', '8-K'.

        Returns:
            ParsedFiling with extracted sections and tables.
        """
        soup = BeautifulSoup(html_content, "lxml")

        # Remove script, style, and hidden elements
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()

        full_text = soup.get_text(separator="\n", strip=True)

        sections = self._extract_sections(full_text)
        tables = self._extract_tables(soup)
        metadata = self._extract_metadata(soup)

        logger.info(
            "parsed_filing",
            accession=accession_number,
            type=filing_type,
            sections=len(sections),
            tables=len(tables),
            words=len(full_text.split()),
        )

        return ParsedFiling(
            accession_number=accession_number,
            filing_type=filing_type,
            full_text=full_text,
            sections=sections,
            tables=tables,
            metadata=metadata,
        )

    def _extract_sections(self, text: str) -> list[ParsedSection]:
        """Extract Item sections from filing text using regex patterns.

        SEC EDGAR HTML filings contain a Table of Contents (TOC) where each
        "Item N" entry is very short (header + page number).  The same item
        headers appear again deeper in the document with full section content.
        We find all matches, group by normalised item number, and keep the
        longest text block for each item so the TOC entries are discarded.
        """
        matches = list(_ITEM_PATTERN.finditer(text))
        if not matches:
            return [
                ParsedSection(
                    section=FilingSection.OTHER,
                    title="Full Document",
                    text=text,
                    start_offset=0,
                    end_offset=len(text),
                    word_count=len(text.split()),
                )
            ]

        # Build a candidate for every consecutive-match pair
        candidates: list[tuple[str, str, str, int, int]] = []  # (item_num, title, text, start, end)
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            item_number = match.group(1).lower()
            title = match.group(2).strip()
            section_text = text[start:end].strip()
            candidates.append((item_number, title, section_text, start, end))

        # Group by item number and keep the longest occurrence (skips TOC)
        best: dict[str, tuple[str, str, str, int, int]] = {}
        for item_num, title, section_text, start, end in candidates:
            if item_num not in best or len(section_text) > len(best[item_num][2]):
                best[item_num] = (item_num, title, section_text, start, end)

        # Sort by document position (start offset) to preserve reading order
        ordered = sorted(best.values(), key=lambda c: c[3])

        sections: list[ParsedSection] = []
        for item_num, title, section_text, start, end in ordered:
            header_text = f"item {item_num}"
            sections.append(
                ParsedSection(
                    section=FilingSection.from_header(header_text),
                    title=title,
                    text=section_text,
                    start_offset=start,
                    end_offset=end,
                    word_count=len(section_text.split()),
                )
            )

        return sections

    def _extract_tables(self, soup: BeautifulSoup) -> list[dict[str, list[list[str]]]]:
        """Extract HTML tables as lists of rows."""
        tables: list[dict[str, list[list[str]]]] = []
        for table_tag in soup.find_all("table"):
            rows: list[list[str]] = []
            for tr in table_tag.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if any(cells):  # skip empty rows
                    rows.append(cells)
            if rows:
                tables.append({"rows": rows})
        return tables

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, str]:
        """Extract document metadata from HTML head and common EDGAR patterns."""
        metadata: dict[str, str] = {}

        # Try title tag
        title = soup.find("title")
        if title:
            metadata["title"] = title.get_text(strip=True)

        # Try common EDGAR meta tags
        for meta in soup.find_all("meta"):
            name = meta.get("name", "")
            content = meta.get("content", "")
            if name and content:
                metadata[name.lower()] = content

        return metadata


def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks for embedding.

    Args:
        text: Input text to chunk.
        chunk_size: Target size of each chunk in characters.
        overlap: Number of overlapping characters between chunks.

    Returns:
        List of text chunks.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        # Try to break at a sentence boundary
        if end < len(text):
            # Look for sentence-ending punctuation near the boundary
            for boundary in (". ", ".\n", "? ", "! "):
                last_boundary = text.rfind(boundary, start + chunk_size // 2, end)
                if last_boundary != -1:
                    end = last_boundary + 1
                    break

        chunks.append(text[start:end].strip())
        start = end - overlap

    return chunks
