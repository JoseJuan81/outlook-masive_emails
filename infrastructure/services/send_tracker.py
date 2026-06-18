"""Persistent tracking of email send results per run."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TRACKING_DIR = _PROJECT_ROOT / "tracking"


class SendTracker:
    """Records the outcome of each email in a timestamped JSON file."""

    def __init__(self, tracking_dir: Path | None = None) -> None:
        self._dir = tracking_dir or _TRACKING_DIR
        self._run_id: str | None = None
        self._started_at: str | None = None
        self._emails: list[dict] = []

    def start_run(self) -> None:
        now = datetime.now()
        self._run_id = now.strftime("%Y-%m-%d_%H-%M-%S")
        self._started_at = now.isoformat()
        self._emails = []
        logger.info("Tracking run iniciado -> %s", self._run_id)

    def record_sent(self, to: str, subject: str, entry_id: str | None = None) -> None:
        self._emails.append({
            "to": to,
            "subject": subject,
            "status": "sent",
            "sent_at": datetime.now().isoformat(),
            "entry_id": entry_id,
            "error": None,
            "attempts": 1,
        })

    def record_failed(self, to: str, subject: str, error: str, attempts: int) -> None:
        self._emails.append({
            "to": to,
            "subject": subject,
            "status": "failed",
            "sent_at": None,
            "entry_id": None,
            "error": error,
            "attempts": attempts,
        })

    def finish_run(self) -> Path:
        self._dir.mkdir(exist_ok=True)
        sent = sum(1 for e in self._emails if e["status"] == "sent")
        failed = sum(1 for e in self._emails if e["status"] == "failed")

        report = {
            "run_id": self._run_id,
            "started_at": self._started_at,
            "finished_at": datetime.now().isoformat(),
            "total": len(self._emails),
            "sent": sent,
            "failed": failed,
            "emails": self._emails,
        }

        file_path = self._dir / f"run_{self._run_id}.json"
        file_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Tracking guardado -> %s", file_path)
        return file_path

    def print_summary(self) -> None:
        sent = sum(1 for e in self._emails if e["status"] == "sent")
        failed = sum(1 for e in self._emails if e["status"] == "failed")
        total = len(self._emails)

        print(f"\n{'=' * 40}")
        print(f"  RESUMEN DE ENVÍO — {self._run_id}")
        print(f"{'=' * 40}")
        print(f"  Total:    {total}")
        print(f"  Enviados: {sent}")
        print(f"  Fallidos: {failed}")

        if failed:
            print(f"\n  Correos fallidos:")
            for e in self._emails:
                if e["status"] == "failed":
                    print(f"    - {e['to']} ({e['error']})")

        print(f"{'=' * 40}\n")

    def get_failed(self) -> list[dict]:
        return [e for e in self._emails if e["status"] == "failed"]

    @staticmethod
    def get_pending_from_last_run(tracking_dir: Path | None = None) -> list[dict]:
        """Load failed emails from the most recent tracking file."""
        directory = tracking_dir or _TRACKING_DIR
        if not directory.exists():
            return []

        files = sorted(directory.glob("run_*.json"), reverse=True)
        if not files:
            return []

        report = json.loads(files[0].read_text(encoding="utf-8"))
        return [e for e in report["emails"] if e["status"] == "failed"]
