import argparse
import csv
from dataclasses import asdict
from typing import Any, Dict, List, Set

from parsers.links import collect_product_links
from parsers.product import parse_product
from settings.constants import COLUMNS
from settings.logging_setup import configure_root_logger, get_logger
from settings.runtime import CONFIG_PATHS


def _format_row(row: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k in COLUMNS:
        v = row.get(k)
        if v is None:
            out[k] = ""
        elif isinstance(v, float):
            out[k] = f"{v:.10g}"
        else:
            out[k] = str(v)
    return out


def _load_existing_urls() -> Set[str]:
    if not CONFIG_PATHS.tsv_path.exists():
        return set()
    urls: Set[str] = set()
    with CONFIG_PATHS.tsv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            u = (r.get("url", "")).strip()
            if u:
                urls.add(u)
    return urls


def write_tsv(rows: List[Dict[str, Any]]) -> None:
    with CONFIG_PATHS.tsv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(_format_row(r))

def _append_tsv_row(row: Dict[str, Any]) -> None:
    tsv_path = CONFIG_PATHS.tsv_path
    file_exists = tsv_path.exists()
    with tsv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in COLUMNS})

def main() -> None:
    parser = argparse.ArgumentParser(description="VkusVill dataset builder")
    parser.add_argument("--target-links", type=int, default=None)
    parser.add_argument("--download-images", action="store_true")
    args = parser.parse_args()

    configure_root_logger()
    log = get_logger(__name__)
    existing = _load_existing_urls()
    if existing:
        log.info(f"Existing URLs detected: {len(existing)} (will be skipped)")

    links = collect_product_links(
        target_count=args.target_links,
        existing_urls=existing,
        max_pages=None,
    )

    total = len(links)
    log.info(f"Parsing {total} product page(s)…")

    written = 0
    for i, url in enumerate(links, start=1):
        log.info(f"Product {i}/{total}: {url}")
        try:
            p = parse_product(url, need_image=args.download_images)
            row = asdict(p)
            _append_tsv_row(row)
            written += 1
            existing.add(row.get("url", url))
            log.info(f"Wrote row #{written} -> {CONFIG_PATHS.tsv_path}")
        except Exception:
            log.exception(f"Failed to parse: {url}")

    log.info(f"Finished. Total new rows written: {written}. TSV -> {CONFIG_PATHS.tsv_path}")

if __name__ == "__main__":
    main()
