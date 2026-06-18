"""Central logging configuration: timestamped file per run + console."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def setup_logging(log_dir: str | Path | None = None) -> Path:
    """Configure root logger to write to console and a timestamped log file.

    Returns the path of the log file created.
    """
    log_path = Path(log_dir) if log_dir else _PROJECT_ROOT / "logs"
    log_path.mkdir(exist_ok=True)

    log_file = log_path / f"send_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    fmt = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    logging.getLogger(__name__).info("Logging iniciado -> archivo=%s", log_file)
    return log_file
