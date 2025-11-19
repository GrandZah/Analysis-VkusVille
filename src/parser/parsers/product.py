import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from lxml import html

from parsers.helpers import (
    as_text,
    fetch_html,
    first_text,
    get_response,
    grams,
    num,
    rel_repo_path,
    shelf_days,
    slug_from_page_url,
    temps,
)
from settings.runtime import CONFIG_PATHS

log = logging.getLogger(__name__)


@dataclass
class Product:
    url: str
    name: Optional[str] = None
    price_rub: Optional[float] = None
    weight_g: Optional[float] = None
    kcal_per_100g: Optional[float] = None
    proteins_g_per_100g: Optional[float] = None
    fats_g_per_100g: Optional[float] = None
    carbs_g_per_100g: Optional[float] = None
    shelf_life_days: Optional[float] = None
    storage_temp_min_c: Optional[float] = None
    storage_temp_max_c: Optional[float] = None
    category_main: Optional[str] = None
    category_path: Optional[str] = None
    brand: Optional[str] = None
    country: Optional[str] = None
    manufacturer: Optional[str] = None
    rating: Optional[float] = None
    ratings_count: Optional[int] = None
    ingredients: Optional[str] = None 
    tags: Optional[str] = None
    image_path: Optional[str] = None


def _info_elem(doc: html.HtmlElement, title_contains: str) -> Optional[html.HtmlElement]:
    xp = "//div[contains(@class,'VV23_DetailProdPageInfoDescItem')]"
    candidates = doc.xpath(xp)
    for item in candidates:
        title_nodes = item.xpath(".//h4")
        title = as_text(title_nodes[0]) if title_nodes else ""
        if title_contains.lower() in title.lower():
            log.debug(f"[nutrition] container by title '{title_contains}' found: {title}")
            return item
    return None

def _info_value(doc: html.HtmlElement, title_contains: str) -> Optional[str]:
    item = _info_elem(doc, title_contains)
    if item is None:
        return None
    descs = item.xpath(".//div[contains(@class,'VV23_DetailProdPageInfoDescItem__Desc')]")
    return as_text(descs[0]) if descs else None

def _fallback_energy_container(doc: html.HtmlElement) -> Optional[html.HtmlElement]:
    nodes = doc.xpath("//*[contains(@class,'EnergyDesc') or contains(@class,'EnergyValue') or contains(@class,'EnergyItem')]")
    if not nodes:
        return None
    anc = nodes[0].xpath("ancestor::div[contains(@class,'VV23_DetailProdPageInfoDescItem')][1]")
    if anc:
        log.debug("[nutrition] container fallback via Energy* classes")
        return anc[0]
    anc = nodes[0].xpath("ancestor::div[contains(@class,'DetailProdPageAccordion')][1]")
    if anc:
        log.debug("[nutrition] container fallback via Accordion ancestor")
        return anc[0]
    return None

def _parse_price(doc: html.HtmlElement) -> Optional[float]:
    p = first_text(doc, "//*[@itemprop='price']/@content")
    if p:
        return num(p)
    p2 = first_text(doc, "//*[contains(@class,'js-datalayer-catalog-list-price') and contains(@class,'hidden')]")
    return num(p2)

def _parse_weight(doc: html.HtmlElement) -> Optional[float]:
    w = (
        first_text(doc, "//*[contains(@class,'ProductCard_weight') or contains(@class,'ProductCard__weight')]")
        or _info_value(doc, "Вес/объем")
    )
    g = grams(w)
    if g is not None:
        return g

    per_kg = doc.xpath(
        "boolean(//*[contains(@class,'Currency') or contains(@class,'Price') or contains(@class,'Product_price')]"
        "[contains(., '/кг') or contains(., '/ кг')])"
    )
    if per_kg:
        return 1000.0

    return None


def _parse_description(doc: html.HtmlElement) -> Optional[str]:
    d = first_text(doc, "//*[@itemprop='description']/@content") or first_text(doc, "//*[@itemprop='description']")
    return d or _info_value(doc, "Описание")



_NUTRIENT_KEYS = {
    "белк": "proteins",
    "жир": "fats",
    "углевод": "carbs",
    "ккал": "kcal",
    "энергетичес": "kcal",
}

def _assign_nutrient(bucket: dict, key_text: str, val_text: str) -> None:
    lt = key_text.lower()
    for frag, field in _NUTRIENT_KEYS.items():
        if frag in lt:
            v = num(val_text)
            if v is not None:
                bucket[field] = v
            return


def _num_near(blob: str, key_frag: str) -> Optional[float]:
    """
    Ищет число рядом с ключом как в варианте 'жиры ... 6', так и '6 ... жиры'.
    """
    m = (re.search(fr"{key_frag}\w*\D*([\d.,]+)", blob, re.I) or
         re.search(fr"([\d.,]+)\D*{key_frag}\w*", blob, re.I))
    return num(m.group(1)) if m else None

def _parse_nutrition_from_text(container: html.HtmlElement) -> dict:
    blob = as_text(container)
    bucket: dict = {}

    v = _num_near(blob, "белк")
    if v is not None:
        bucket["proteins"] = v

    v = _num_near(blob, "жир")
    if v is not None:
        bucket["fats"] = v

    v = _num_near(blob, "углевод")
    if v is not None:
        bucket["carbs"] = v

    # ккал чаще идёт как "<число> ккал", оставим как было
    m_kcal = (re.search(r"([\d.,]+)\s*ккал", blob, re.I) or
              re.search(r"энергетичес\w*.*?([\d.,]+)\s*ккал", blob, re.I))
    if m_kcal:
        bucket["kcal"] = num(m_kcal.group(1))

    log.debug(f"[nutrition][text] parsed={bucket} from='{blob}'")
    return bucket


def _parse_nutrition_from_blocks(container: html.HtmlElement) -> dict:
    bucket: dict = {}

    items = container.xpath(".//div[contains(@class,'EnergyItem')]")
    log.debug(f"[nutrition][blocks] EnergyItem count={len(items)}")
    for it in items:
        key = it.xpath(".//*[contains(@class,'EnergyDesc')]")
        val = it.xpath(".//*[contains(@class,'EnergyValue')]")
        if key and val:
            ks, vs = as_text(key[0]), as_text(val[0])
            _assign_nutrient(bucket, ks, vs)
            log.debug(f"[nutrition][blocks] pair '{ks}' = '{vs}'")

    if len(bucket) < 4:
        values = container.xpath(".//*[contains(@class,'EnergyValue')]")
        descs  = container.xpath(".//*[contains(@class,'EnergyDesc')]")
        log.debug(f"[nutrition][blocks] EnergyDesc={len(descs)} EnergyValue={len(values)} (loose)")
        for key_node, val_node in zip(descs, values):
            ks, vs = as_text(key_node), as_text(val_node)
            _assign_nutrient(bucket, ks, vs)

    if len(bucket) < 4:
        trs = container.xpath(".//tr")
        log.debug(f"[nutrition][blocks] table rows={len(trs)}")
        for tr in trs:
            cells = tr.xpath("./th|./td")
            if len(cells) >= 2:
                _assign_nutrient(bucket, as_text(cells[0]), as_text(cells[-1]))

    if len(bucket) < 4:
        rows = container.xpath(".//li | .//p | .//div[contains(@class,'Row') or contains(@class,'Item') or contains(@class,'line')]")
        log.debug(f"[nutrition][blocks] rows={len(rows)}")
        for n in rows:
            text = as_text(n)
            if ":" in text:
                k, v = text.split(":", 1)
                _assign_nutrient(bucket, k, v)
            else:
                for frag, field in _NUTRIENT_KEYS.items():
                    if frag in text.lower():
                        m = re.search(r"([-+]?\d+(?:[.,]\d+)?)", text)
                        if m:
                            bucket[field] = float(m.group(1).replace(",", "."))
                        break

    log.debug(f"[nutrition][blocks] parsed={bucket}")
    return bucket

def _merge_pref(primary: dict, fallback: dict) -> dict:
    """
    primary имеет приоритет над fallback.
    """
    keys = ("proteins", "fats", "carbs", "kcal")
    merged = {k: (primary.get(k) if primary.get(k) is not None else fallback.get(k)) for k in keys}
    log.debug(f"[nutrition] merged={merged} (primary={primary}, fallback={fallback})")
    return merged


def _parse_nutrition(doc: html.HtmlElement) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    container = _info_elem(doc, "Пищевая") or _info_elem(doc, "Пищевая и энергетическая")
    if container is None:
        container = _fallback_energy_container(doc)
    if container is None:
        titles = [as_text(h) for h in doc.xpath("//div[contains(@class,'VV23_DetailProdPageInfoDescItem')]//h4")]
        log.debug(f"[nutrition] container NOT found; titles={titles[:6]}")
        return None, None, None, None

    from_blocks = _parse_nutrition_from_blocks(container)
    from_text = _parse_nutrition_from_text(container)

    merged = _merge_pref(from_blocks, from_text)

    return (
        merged.get("proteins"),
        merged.get("fats"),
        merged.get("carbs"),
        merged.get("kcal"),
    )



def _parse_shelf_and_storage(doc: html.HtmlElement) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    days = shelf_days(_info_value(doc, "Годен"))
    tmin, tmax = temps(_info_value(doc, "Условия хранения"))
    return days, tmin, tmax


def _parse_categories(doc: html.HtmlElement) -> Tuple[Optional[str], Optional[str]]:
    cat_main = first_text(doc, "//*[@id='log_section_name']/@value")
    path_raw = first_text(doc, "//*[contains(@class,'js-datalayer-catalog-list-category') and contains(@class,'hidden')]")
    if path_raw:
        path = " / ".join([p.strip() for p in path_raw.split("//") if p.strip()])
    else:
        path = cat_main
    return (cat_main.strip() if cat_main else None, path.strip() if path else None)


def _parse_brand_country_manufacturer(doc: html.HtmlElement) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    brand = first_text(doc, "//*[@itemprop='brand']//*[@itemprop='name']/text()")
    country = _info_value(doc, "Страна производства")
    manuf = _info_value(doc, "Изготовитель") or _info_value(doc, "Производитель")
    return brand, country, manuf

def _parse_ingredients(doc: html.HtmlElement) -> Optional[str]:
    for title in ("Состав", "Ингредиенты", "Состав продукта"):
        v = _info_value(doc, title)
        if v:
            return v
    return None


def _parse_rating(doc: html.HtmlElement) -> Tuple[Optional[float], Optional[int]]:
    r = first_text(doc, "//*[@itemprop='aggregateRating']//*[@itemprop='ratingValue']/@content")
    c = first_text(doc, "//*[@itemprop='aggregateRating']//*[@itemprop='reviewCount']/@content")
    return num(r), int(num(c)) if c and num(c) is not None else None


def _first_image_url(doc: html.HtmlElement) -> Optional[str]:
    for xp in [
        "//img[contains(@src,'img.vkusvill.ru')][contains(@src,'.webp')]/@src",
        "//img[contains(@src,'img.vkusvill.ru')]/@src",
    ]:
        u = first_text(doc, xp)
        if u:
            return u
    return None


def _download_image(doc: html.HtmlElement, page_url: str) -> Optional[str]:
    img_url = _first_image_url(doc)
    if not img_url:
        return None
    r = get_response(img_url)

    slug = slug_from_page_url(page_url)
    fname = f"{slug}.jpg"
    path = CONFIG_PATHS.pics_dir / fname

    path.write_bytes(r.content)
    log.debug(f"Saved image -> {path}")

    return rel_repo_path(path)



def parse_product(url: str, need_image: bool = True) -> Product:
    doc = fetch_html(url)

    name = first_text(doc, "//h1[contains(@class,'Product__title')]")

    price = _parse_price(doc)
    weight = _parse_weight(doc)
    prot, fat, carb, kcal = _parse_nutrition(doc)
    if not any([prot, fat, carb, kcal]):
        log.debug(f"[nutrition] EMPTY for {url} -> will remain None in dataset")

    shelf, tmin, tmax = _parse_shelf_and_storage(doc)
    cat_main, cat_path = _parse_categories(doc)
    brand, country, manuf = _parse_brand_country_manufacturer(doc)
    rating, rating_cnt = _parse_rating(doc)
    ingredients = _parse_ingredients(doc)
    desc = _parse_description(doc)
    image_path = _download_image(doc, url) if need_image else None

    return Product(
        url=url,
        name=name,
        price_rub=price,
        weight_g=weight,
        kcal_per_100g=kcal,
        proteins_g_per_100g=prot,
        fats_g_per_100g=fat,
        carbs_g_per_100g=carb,
        shelf_life_days=shelf,
        storage_temp_min_c=tmin,
        storage_temp_max_c=tmax,
        category_main=cat_main,
        category_path=cat_path,
        brand=brand,
        country=country,
        manufacturer=manuf,
        rating=rating,
        ratings_count=rating_cnt,
        ingredients=ingredients,
        tags=desc,
        image_path=image_path,
    )
