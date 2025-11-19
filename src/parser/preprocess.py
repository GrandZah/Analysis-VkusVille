from __future__ import annotations

import re
from typing import List

import numpy as np
import pandas as pd
from settings.constants import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS
from settings.runtime import CONFIG_PATHS
from settings.logging_setup import configure_root_logger, get_logger

TARGET = "category_main"

DROP: List[str] = [
    "url", "name", "category_path",
    "manufacturer",
    "tags", "ingredients",
    "image_path",
]

ORG_RE = re.compile(r"\b(ООО|АО|ПАО|ЗАО|ОАО|ИП)\b\s*[«\"]?\s*([A-Za-zА-Яа-я0-9\s\-\._]+)", re.I | re.U)


def extract_manufacturer_name(raw: str | None) -> str:
    if not raw or str(raw).strip() in {"", "None", "nan"}:
        return "unknown"
    s = str(raw).replace("„", "«").replace("“", "»").replace(":", " ")
    m = ORG_RE.search(s)
    if not m:
        return "unknown"
    name = (m.group(1) + " " + m.group(2)).strip()
    name = name.replace('"', "").replace("«", "").replace("»", "")
    name = re.sub(r"\s{2,}", " ", name)
    return name if name else "unknown"


def select_model_columns(df: pd.DataFrame) -> pd.DataFrame:
    numeric_present = [c for c in NUMERIC_COLUMNS if c in df.columns]
    ohe_prefixes = tuple([f"{c}_" for c in (CATEGORICAL_COLUMNS + ["manufacturer_name"]) if c != TARGET])
    ohe_present = [c for c in df.columns if c.startswith(ohe_prefixes)]
    cols = [TARGET] + numeric_present + ohe_present
    return df[cols]


def count_ratings(df: pd.DataFrame) -> None:
    rc = df.get("ratings_count")
    if rc is not None:
        no_reviews = rc.isna() | (rc == 0)
        df["ratings_count"] = rc.fillna(0.0)
    else:
        no_reviews = pd.Series(False, index=df.index)

    if "rating" in df.columns:
        df.loc[no_reviews, "rating"] = df.loc[no_reviews, "rating"].fillna(0.0)
        med_rating = df.loc[~no_reviews, "rating"].median(skipna=True)
        df.loc[~no_reviews, "rating"] = df.loc[~no_reviews, "rating"].fillna(0.0 if np.isnan(med_rating) else med_rating)

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df[TARGET] = df[TARGET].astype(str).replace({"", "None", "nan"}, "unknown")
    
    for c in NUMERIC_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    count_ratings(df)

    for c in [x for x in NUMERIC_COLUMNS if x not in ("rating", "ratings_count")]:
        med = df[c].median(skipna=True)
        df[c] = df[c].fillna(0.0 if np.isnan(med) else med)


    df["manufacturer_name"] = df.get("manufacturer", "").apply(extract_manufacturer_name)
    df["manufacturer_name"] = df["manufacturer_name"].replace({"", "None", "nan"}, "unknown").fillna("unknown")

    cat_cols = [c for c in (CATEGORICAL_COLUMNS + ["manufacturer_name"]) if c in df.columns]
    for c in cat_cols:
        if c == TARGET:
            continue
        df[c] = df[c].replace({"", "None", "nan"}, "unknown").fillna("unknown")

    df = df.drop(columns=DROP, errors="ignore")

    ohe_cols = [c for c in cat_cols if c != TARGET and c in df.columns]
    df = pd.get_dummies(df, columns=ohe_cols, dummy_na=False)

    for c in NUMERIC_COLUMNS:
        if c in df.columns:
            vmin, vmax = df[c].min(), df[c].max()
            df[c] = 0.0 if vmax == vmin else (df[c] - vmin) / (vmax - vmin)

    df = select_model_columns(df)
    return df


def main():
    configure_root_logger()
    log = get_logger(__name__)

    df_raw = pd.read_csv(CONFIG_PATHS.tsv_path, sep="\t", dtype=str, keep_default_na=False)
    n0 = len(df_raw)

    df = preprocess(df_raw)
    df.to_csv(CONFIG_PATHS.csv_path, index=False, encoding="utf-8")

    log.info(f"Saved {CONFIG_PATHS.csv_path} rows={n0} -> shape={df.shape}")


if __name__ == "__main__":
    main()
