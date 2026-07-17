"""Helpers for loading the project .env from the repository root."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_project_env() -> None:
    """Load the root .env file explicitly to avoid cwd-dependent resolution."""
    load_dotenv(dotenv_path=ENV_PATH, override=True)
