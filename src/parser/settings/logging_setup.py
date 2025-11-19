import logging
from logging import Logger
from logging.handlers import RotatingFileHandler

from settings.runtime import CONFIG_PATHS


def configure_root_logger() -> None:
    root = logging.getLogger()
    if root.handlers:
        for h in list(root.handlers):
            root.removeHandler(h)

    root.setLevel(logging.DEBUG)

    file_path = CONFIG_PATHS.run_log_dir / "app.log"
    fh = RotatingFileHandler(file_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    root.addHandler(ch)

    for noisy in ("matplotlib", "PIL"):
        logging.getLogger(noisy).disabled = True


def get_logger(name: str) -> Logger:
    return logging.getLogger(name)
