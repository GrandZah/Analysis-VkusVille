# DS/settings/net_minimal.py
from __future__ import annotations

import hashlib
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

FIRST_ATTEMPT_CONNECT_TIMEOUT = 12   # сек на 1-й попытке (длиннее)
RETRY_CONNECT_TIMEOUT = 6            # сек на 2-й/3-й попытке (короче)
READ_TIMEOUT = 15                    # сек
MAX_ATTEMPTS = 3
ALLOW_DIRECT_FALLBACK = True         # можно выключить, если запрещён прямой выход

START_JITTER_MS_RANGE: Tuple[int, int] = (20, 80)  # мс

PRE_REQUEST_SLEEP_RANGE_SEC: Tuple[float, float] = (2, 4) # сек

UA_POOL: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

MASK_URLS_IN_LOGS: bool = True                 # включить/выключить маскировку реальных доменов в логах
MASK_HASH_LEN: int = 10                        # длина хеша, попадающего в лог
LOG_MASK_SALT: str = os.environ.get("LOG_MASK_SALT", "vv_mask_salt")

def _hash_host(host: str) -> str:
    hx = hashlib.sha256((LOG_MASK_SALT + "|" + host).encode("utf-8")).hexdigest()
    return hx[:MASK_HASH_LEN]

def mask_url_for_logs(url: str) -> str:
    if not MASK_URLS_IN_LOGS:
        return url
    try:
        p = urlparse(url)
        host_mask = f"host#{_hash_host(p.netloc or '')}"
        path = p.path or "/"
        return f"{p.scheme}://{host_mask}{path}"
    except Exception:
        return url

def _rand_ms(a: int, b: int) -> float:
    return random.uniform(a / 1000.0, b / 1000.0)

def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=1, connect=1, read=1,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=40, pool_maxsize=40)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def _build_headers(user_agent: str, accept_language: str = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7") -> Dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": accept_language,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
    }

def _mask_proxy_for_logs(url: str) -> str:
    try:
        at = url.split("@")[-1]
        scheme, host = at.split("://")[0], at.split("://", 1)[1]
        return f"{scheme}://{host}"
    except Exception:
        return url

@dataclass
class Endpoint:
    name: str                
    proxy_url: Optional[str] 
    session: requests.Session
    headers: Dict[str, str]

class MinimalHttpClient:
    def __init__(self, proxy_urls: List[str], allow_direct: bool = ALLOW_DIRECT_FALLBACK):
        self.endpoints: List[Endpoint] = []
        for i, purl in enumerate(proxy_urls):
            ua = UA_POOL[i % len(UA_POOL)]
            ep = Endpoint(
                name=_mask_proxy_for_logs(purl),
                proxy_url=purl,
                session=_build_session(),
                headers=_build_headers(ua),
            )
            ep.session.headers.clear()
            ep.session.headers.update(ep.headers)
            self.endpoints.append(ep)
        if allow_direct:
            ua = UA_POOL[len(self.endpoints) % len(UA_POOL)]
            direct = Endpoint(
                name="DIRECT",
                proxy_url=None,
                session=_build_session(),
                headers=_build_headers(ua),
            )
            direct.session.headers.clear()
            direct.session.headers.update(direct.headers)
            self.endpoints.append(direct)

        self._i = 0
        self._allow_direct = allow_direct
        log.info(
            "MinimalHttpClient: endpoints=%d allow_direct=%s names=%s",
            len(self.endpoints), self._allow_direct, [e.name for e in self.endpoints]
        )

    def _pick(self) -> Optional[Endpoint]:
        if not self.endpoints:
            return None
        ep = self.endpoints[self._i % len(self.endpoints)]
        self._i += 1
        return ep

    def http_get(
        self,
        url: str,
        referer: Optional[str] = None,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> requests.Response:
        if not self.endpoints:
            raise RuntimeError("Proxy pool is empty (no endpoints).")

        masked_url = mask_url_for_logs(url)
        last_exc: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            ep = self._pick()
            if ep is None:
                break

            headers = dict(ep.headers)
            if referer:
                headers["Referer"] = referer

            proxies = {"http": ep.proxy_url, "https": ep.proxy_url} if ep.proxy_url else None
            connect_timeout = FIRST_ATTEMPT_CONNECT_TIMEOUT if attempt == 1 else RETRY_CONNECT_TIMEOUT
            timeout: Tuple[int, int] = (connect_timeout, READ_TIMEOUT)

            prewait = random.uniform(*PRE_REQUEST_SLEEP_RANGE_SEC)
            time.sleep(prewait)

            jitter = _rand_ms(*START_JITTER_MS_RANGE)
            time.sleep(jitter)

            try:
                log.debug(
                    "GET attempt=%d via=%s url=%s timeout=%ss/%ss prewait_ms=%d jitter_ms=%d",
                    attempt, ep.name, masked_url, timeout[0], timeout[1],
                    int(prewait * 1000), int(jitter * 1000)
                )
                resp = ep.session.get(
                    url, headers=headers, proxies=proxies,
                    timeout=timeout, allow_redirects=True
                )
                size = len(resp.content or b"")
                log.info(
                    "OK attempt=%d via=%s status=%d size=%d url=%s",
                    attempt, ep.name, resp.status_code, size, masked_url
                )
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_exc = e
                log.warning(
                    "FAIL attempt=%d via=%s exc=%s: %s url=%s",
                    attempt, ep.name, type(e).__name__, str(e), masked_url
                )
                continue

        if last_exc:
            raise last_exc
        raise RuntimeError("All attempts exhausted and no response returned.")


def _load_proxies_from_config() -> List[str]:
    try:
        from DS.settings.runtime import CONFIG_PATHS
    except Exception:
        log.warning("CONFIG_PATHS not available; returning empty proxy list")
        return []
    p = CONFIG_PATHS.proxies_file
    try:
        if p.exists():
            lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
            items = [ln for ln in lines if ln]
            log.info("Loaded proxies: %d from %s", len(items), p)
            return items
        else:
            log.info("Proxies file not found: %s", p)
            return []
    except Exception as e:
        log.warning("Failed to read proxies file %s: %s", p, e)
        return []

CLIENT = MinimalHttpClient(_load_proxies_from_config(), allow_direct=ALLOW_DIRECT_FALLBACK)