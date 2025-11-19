import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

import requests
from lxml import etree, html

from settings.proxy import CLIENT
from settings.runtime import CONFIG_PATHS

log = logging.getLogger(__name__)

def get_response(url: str) -> requests.Response:
    r = CLIENT.http_get(url=url)
    return r
    
def fetch_html(url: str) -> html.HtmlElement:
    r = get_response(url)
    return html.fromstring(r.text)


_WS_RE = re.compile(r"\s+")

def _clean_ws(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return _WS_RE.sub(" ", s).replace("\u00a0", " ").strip()

def as_text(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, html.HtmlElement) or isinstance(node, etree._Element):
        txt = " ".join(node.xpath(".//text()"))
        return _clean_ws(txt) or ""
    if isinstance(node, (etree._ElementUnicodeResult, str)):
        return _clean_ws(str(node)) or ""
    if isinstance(node, (bytes, bytearray)):
        return _clean_ws(node.decode("utf-8", errors="ignore")) or ""
    return _clean_ws(str(node)) or ""

def first_text(doc: html.HtmlElement, xp: str) -> Optional[str]:
    got = doc.xpath(xp)
    if not got:
        return None
    return as_text(got[0])

def slug_from_page_url(page_url: str) -> str:
    return Path(urlparse(page_url).path).stem

def rel_repo_path(p: Path) -> str:
    rel = p.relative_to(CONFIG_PATHS.base_dir)
    return os.path.join("\\", CONFIG_PATHS.base_dir.name, *rel.parts)


def num(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(s).replace("\u00a0", " "))
    return float(m.group(0).replace(",", ".")) if m else None

UNIT_TO_GRAMS = {
    "кг": 1000.0,
    "л": 1000.0,
    "г": 1.0,
    "гр": 1.0,
    "мл": 1.0,
}

TIME_TO_DAYS = {
    "час": 1.0 / 24.0,
    "сут": 1.0,
    "дн": 1.0,
    "недел": 7.0,
    "мес": 30.0,
    "месяц": 30.0,
    "год": 365.0,
}

def grams(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    s_norm = s.lower().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(кг|г|гр|мл|л)\b", s_norm)
    if m:
        value = float(m.group(1))
        unit = m.group(2)
        return value * UNIT_TO_GRAMS.get(unit, 1.0)

    # если встретились шт, то возвращаем None
    if re.search(r"\bшт\.?\b", s_norm):
        return None

    x = num(s_norm)
    return float(x) if x is not None else None


def shelf_days(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    s_low = s.lower()
    value = num(s_low)
    if value is None:
        return None
    for key, mult in TIME_TO_DAYS.items():
        if key in s_low:
            return value * mult
    return value

def temps(s: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    if not s:
        return None, None
    vals = [float(x.replace(",", ".")) for x in re.findall(r"[-+]?\d+(?:[.,]\d+)?", s)]
    if len(vals) >= 2:
        return vals[0], vals[1]
    if len(vals) == 1:
        return vals[0], None
    return None, None
