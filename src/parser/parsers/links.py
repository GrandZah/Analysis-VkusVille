import logging
import re
import urllib.parse as up
from typing import List, Optional, Set

from lxml import html

from parsers.helpers import fetch_html
from settings.constants import BASE_CATEGORY_URL, MAX_PAGES

log = logging.getLogger(__name__)

_PRODUCT_RX = re.compile(r"/goods/[^/]+-\d+\.html$")


def _extract_links(doc: html.HtmlElement) -> List[str]:
    out: Set[str] = set()
    for a in doc.xpath("//a[@href]"):
        href = a.get("href", "")
        if _PRODUCT_RX.search(href):
            out.add(up.urljoin(BASE_CATEGORY_URL, href))
    return sorted(out)


def collect_product_links(
    target_count: Optional[int] = None,
    existing_urls: Optional[Set[str]] = None,
    max_pages: Optional[int] = None,
) -> List[str]:
    limit_pages = max_pages or MAX_PAGES
    want = target_count if (target_count and target_count > 0) else None
    seen: Set[str] = set()
    skip: Set[str] = existing_urls or set()
    links: List[str] = []
    page = 1
    pages_scanned = 0

    while page <= limit_pages:
        url = BASE_CATEGORY_URL if page == 1 else f"{BASE_CATEGORY_URL}?PAGEN_1={page}"
        doc = fetch_html(url)
        found = _extract_links(doc)
        new = [u for u in found if u not in seen and u not in skip]

        for u in new:
            seen.add(u)
            links.append(u)

        pages_scanned += 1
        log.info(f"Page {page}: found={len(found)} new={len(new)} total_new={len(links)}")

        if want is not None and len(links) >= want:
            log.info(f"Target reached: collected {len(links)} new links (target={want}) on page {page}")
            break

        page += 1

    if want is not None and len(links) < want:
        log.warning(
            f"Collected {len(links)} new links < target {want} after scanning {pages_scanned} page(s) "
            f"(limit_pages={limit_pages})."
        )

    log.info(f"Total product links collected: {len(links)}")
    return links[:want] if want is not None else links
