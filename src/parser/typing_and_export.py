import csv
import json

from settings.constants import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS, COLUMNS, STRING_COLUMNS
from settings.runtime import CONFIG_PATHS
from settings.logging_setup import configure_root_logger, get_logger


def arff_escape(v: str) -> str:
    if v is None or v == "":
        return "?"
    if any(ch in v for ch in [",", " ", "'", "{", "}", "\\"]):
        return "'" + v.replace("'", "\\'") + "'"
    return v


def load_rows():
    with CONFIG_PATHS.tsv_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_arff(rows):
    with CONFIG_PATHS.arff_path.open("w", encoding="utf-8", newline="") as f:
        f.write("@RELATION vkusvill_ready_meals\n\n")
        for c in COLUMNS:
            if c in NUMERIC_COLUMNS:
                f.write(f"@ATTRIBUTE {c} NUMERIC\n")
            elif c in STRING_COLUMNS:
                f.write(f"@ATTRIBUTE {c} STRING\n")
            elif c in CATEGORICAL_COLUMNS:
                values = sorted({r[c] for r in rows if r.get(c)})
                nominal = ",".join(arff_escape(v) for v in values)
                f.write(f"@ATTRIBUTE {c} {{{nominal}}}\n")
        f.write("\n@DATA\n")
        for r in rows:
            line = []
            for c in COLUMNS:
                v = r.get(c, "")
                line.append(arff_escape(v))
            f.write(",".join(line) + "\n")


def write_json(rows):
    header = []
    for c in COLUMNS:
        if c in NUMERIC_COLUMNS:
            header.append({"feature_name": c, "type": "numeric"})
        elif c in CATEGORICAL_COLUMNS:
            values = sorted({str(r[c]).strip()
                             for r in rows if r.get(c) not in (None, "")})
            header.append({"feature_name": c, "type": "category", "values": values})
        else:
            header.append({"feature_name": c, "type": "text"})

    def cast_value(v, col):
        if v in ("", None):
            return None
        if col in NUMERIC_COLUMNS:
            try:
                return float(v)
            except Exception:
                return None
        return v

    data = [{c: cast_value(r.get(c, None), c) for c in COLUMNS} for r in rows]

    with CONFIG_PATHS.json_path.open("w", encoding="utf-8") as f:
        json.dump({"header": header, "data": data}, f, ensure_ascii=False, indent=2)



def main():
    configure_root_logger()
    log = get_logger(__name__)
    rows = load_rows()
    log.info(f"Loaded {len(rows)} rows")
    write_arff(rows)
    write_json(rows)
    log.info(f"Wrote: {CONFIG_PATHS.arff_path}, {CONFIG_PATHS.json_path}")


if __name__ == "__main__":
    main()
