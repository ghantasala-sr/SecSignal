"""SEC EDGAR EFTS API client for fetching 10-K, 10-Q, and 8-K filings."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# EDGAR EFTS (full-text search) base URL — free, no API key required
EFTS_BASE_URL = "https://efts.sec.gov/LATEST"
# EDGAR company filings endpoint
FILINGS_BASE_URL = "https://data.sec.gov/submissions"
# EDGAR filing archives
ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"

# SEC requires a descriptive User-Agent header
DEFAULT_USER_AGENT = "SecSignal Research agent@secsignal.dev"

# Rate limit: SEC allows max 10 requests/second
REQUEST_DELAY_SECONDS = 0.12

FILING_TYPES = ("10-K", "10-Q", "8-K")


@dataclass
class Filing:
    """Represents a single SEC filing."""

    accession_number: str
    cik: str
    company_name: str
    ticker: str
    filing_type: str
    filing_date: str
    primary_document: str
    primary_doc_url: str
    filing_index_url: str
    metadata: dict[str, Any] = field(default_factory=dict)


class EdgarClient:
    """Async client for SEC EDGAR APIs.

    Uses the free EFTS (full-text search) and SUBMISSIONS endpoints.
    No API key required — just a proper User-Agent header.
    """

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._user_agent = user_agent
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        self._last_request_time: float = 0.0

    async def _rate_limit(self) -> None:
        """Enforce SEC's 10 req/s rate limit."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            await _async_sleep(REQUEST_DELAY_SECONDS - elapsed)
        self._last_request_time = time.monotonic()

    async def _get(self, url: str) -> dict[str, Any]:
        """Make a rate-limited GET request."""
        await self._rate_limit()
        logger.debug("edgar_request", url=url)
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()

    async def _get_bytes(self, url: str) -> bytes:
        """Make a rate-limited GET request returning raw bytes (for PDFs/HTML)."""
        await self._rate_limit()
        logger.debug("edgar_request_bytes", url=url)
        response = await self._client.get(url)
        response.raise_for_status()
        return response.content

    async def get_cik_for_ticker(self, ticker: str) -> str | None:
        """Resolve a stock ticker to its CIK number via EDGAR company tickers JSON."""
        url = "https://www.sec.gov/files/company_tickers.json"
        data = await self._get(url)
        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker") == ticker_upper:
                # CIK is zero-padded to 10 digits
                return str(entry["cik_str"]).zfill(10)
        return None

    async def get_company_filings(
        self,
        cik: str,
        filing_types: tuple[str, ...] = FILING_TYPES,
        max_filings: int = 40,
    ) -> list[Filing]:
        """Fetch recent filings for a company by CIK.

        Args:
            cik: 10-digit zero-padded CIK number.
            filing_types: Tuple of filing types to include.
            max_filings: Maximum number of filings to return.

        Returns:
            List of Filing objects, most recent first.
        """
        cik_padded = cik.zfill(10)
        url = f"{FILINGS_BASE_URL}/CIK{cik_padded}.json"
        data = await self._get(url)

        company_name = data.get("name", "")
        tickers = data.get("tickers", [])
        ticker = tickers[0] if tickers else ""

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])

        filings: list[Filing] = []
        for i, form in enumerate(forms):
            if form not in filing_types:
                continue
            if len(filings) >= max_filings:
                break

            accession = accessions[i]
            accession_no_dash = accession.replace("-", "")
            primary_doc = primary_docs[i]

            filing = Filing(
                accession_number=accession,
                cik=cik_padded,
                company_name=company_name,
                ticker=ticker,
                filing_type=form,
                filing_date=dates[i],
                primary_document=primary_doc,
                primary_doc_url=f"{ARCHIVES_BASE_URL}/{int(cik_padded)}/{accession_no_dash}/{primary_doc}",
                filing_index_url=f"{ARCHIVES_BASE_URL}/{int(cik_padded)}/{accession_no_dash}/",
            )
            filings.append(filing)

        logger.info(
            "fetched_filings",
            cik=cik_padded,
            company=company_name,
            count=len(filings),
        )
        return filings

    async def search_filings(
        self,
        query: str,
        filing_types: tuple[str, ...] = FILING_TYPES,
        date_range: tuple[str, str] | None = None,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text search across EDGAR filings via EFTS.

        Args:
            query: Free-text search query.
            filing_types: Filing types to filter.
            date_range: Optional (start_date, end_date) in YYYY-MM-DD format.
            max_results: Maximum results to return.

        Returns:
            List of search result dicts with filing metadata.
        """
        params: dict[str, Any] = {
            "q": query,
            "forms": ",".join(filing_types),
            "from": 0,
            "size": max_results,
        }
        if date_range:
            params["dateRange"] = "custom"
            params["startdt"] = date_range[0]
            params["enddt"] = date_range[1]

        url = f"{EFTS_BASE_URL}/search-index"
        data = await self._get(f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")

        hits = data.get("hits", {}).get("hits", [])
        logger.info("efts_search", query=query, results=len(hits))
        return hits

    async def download_filing_document(self, url: str) -> bytes:
        """Download a filing document (HTML, PDF, XBRL) as raw bytes."""
        return await self._get_bytes(url)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> EdgarClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()


async def _async_sleep(seconds: float) -> None:
    """Async sleep helper."""
    import asyncio

    await asyncio.sleep(seconds)
