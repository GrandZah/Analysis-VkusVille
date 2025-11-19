from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ConfigPaths:
    base_dir: Path
    data_dir: Path
    pics_dir: Path
    logs_root_dir: Path
    run_log_dir: Path
    tsv_path: Path
    arff_path: Path
    json_path: Path
    csv_path: Path
    proxies_file: Path
    tsv_path_save_moment: Path

    @classmethod
    def from_base(cls, base: Path, timestamp: str | None = None) -> "ConfigPaths":
        ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        data = base / "data"
        logs_root = data / "log"
        run_log_dir = logs_root / ts
        return cls(
            base_dir=base,
            data_dir=data,
            pics_dir=data / "pics",
            logs_root_dir=logs_root,
            run_log_dir=run_log_dir,
            tsv_path=data / "data.tsv",
            arff_path=data / "data.arff",
            json_path=data / "data.json",
            csv_path=data / "data.csv",
            proxies_file=data / "proxies.txt",
            tsv_path_save_moment = data / "data_save_moment.tsv",
        )

    def ensure_dirs(self) -> None:
        for name, value in self.__dict__.items():
            if isinstance(value, Path) and name.endswith("_dir"):
                value.mkdir(parents=True, exist_ok=True)


def load_config_paths() -> ConfigPaths:
    current_path = Path(__file__).resolve()
    src_dir = next(p for p in current_path.parents if p.name == "src")
    base = src_dir.parent
    paths = ConfigPaths.from_base(base)
    paths.ensure_dirs()
    paths.pics_dir.mkdir(parents=True, exist_ok=True)
    return paths