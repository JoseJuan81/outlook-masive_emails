"""Shared fixtures for the regression test suite.

These fixtures isolate each test from global state in:

- ``web.app._session``               (in-memory dict, FastAPI app)
- ``html/images/body/``              (IMAGES_DIR used by save_images + send_from_staging)
- ``staging/emails_to_send.json``    (STAGING_FILE written by /api/send)
- ``staging/send_progress.json``     (PROGRESS_FILE)

The ``clean_state`` fixture is autouse: it wipes all of the above
before AND after every test, so no test leaks state into the next one.
"""

from __future__ import annotations

import json
import shutil
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Project paths (mirror the constants in web/app.py and send_from_staging.py)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BODY_IMAGES_DIR = _PROJECT_ROOT / "html" / "images" / "body"
_STAGING_FILE = _PROJECT_ROOT / "staging" / "emails_to_send.json"
_PROGRESS_FILE = _PROJECT_ROOT / "staging" / "send_progress.json"


# ---------------------------------------------------------------------------
# autouse: clean global state
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_state():
    """Wipe global session, image dir, staging file and progress file.

    Runs before AND after every test. We import web.app lazily so its
    top-level side effects (load_dotenv, setup_logging) happen once
    in the test session, not per fixture invocation.
    """
    _reset_session()
    _wipe_dir(_BODY_IMAGES_DIR)
    _remove_file(_STAGING_FILE)
    _remove_file(_PROGRESS_FILE)
    yield
    _reset_session()
    _wipe_dir(_BODY_IMAGES_DIR)
    _remove_file(_STAGING_FILE)
    _remove_file(_PROGRESS_FILE)


def _reset_session() -> None:
    """Reset the web.app._session dict to its initial empty state."""
    from web import app as web_app  # lazy import: triggers env load once
    web_app._session["subject"] = None
    web_app._session["html_body"] = None
    web_app._session["builder"] = None


def _wipe_dir(path: Path) -> None:
    if path.exists():
        for child in path.iterdir():
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
            except FileNotFoundError:
                pass


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> TestClient:
    """In-process FastAPI TestClient. No live server, no network."""
    # Importing web.app runs setup_logging() which writes a log file.
    # That's a project-wide side effect that's safe to keep.
    from web.app import app  # noqa: WPS433 (intentional lazy import)
    return TestClient(app)


# ---------------------------------------------------------------------------
# EML factory: build valid .eml files with subject + HTML + N inline images
# ---------------------------------------------------------------------------

def _png_bytes(seed: int) -> bytes:
    """Return valid-looking PNG bytes (1x1 transparent) for a given seed.

    We don't need real images for testing: ``save_images`` writes the raw
    bytes to disk and ``send_from_staging`` only cares that files exist.
    Using a 1x1 PNG keeps the EML valid MIME.
    """
    # Minimal 1x1 transparent PNG. The payload varies by seed only in the
    # idat data byte so file content differs per image.
    base = (
        b"\x89PNG\r\n\x1a\n"          # signature
        b"\x00\x00\x00\rIHDR"        # IHDR chunk header
        b"\x00\x00\x00\x01\x00\x00\x00\x01"  # 1x1
        b"\x08\x06\x00\x00\x00"      # 8-bit RGBA
        b"\x1f\x15\xc4\x89"          # IHDR CRC (valid for above)
        b"\x00\x00\x00\x0cIDAT"      # IDAT chunk header (12 bytes)
        b"\x08\x99\x63\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8\x97"  # payload
        b"\x00\x00\x00\x00IEND"      # IEND
        b"\xaeB`\x82"                # IEND CRC
    )
    return base + bytes([seed % 256])


def _make_eml_bytes(subject: str, html_body: str, n_images: int) -> bytes:
    """Serialize an EmailMessage with the given parts to an .eml payload."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg.set_content("Plain-text fallback")
    msg.add_alternative(html_body, subtype="html")

    for idx in range(n_images):
        # cid:image_N style so HtmlEmailBuilder can convert back to cid:image_N
        cid = f"image_{idx}@test"
        # Ensure the HTML references the cid (so ordered_cids_from_html finds them).
        # If the html doesn't include the cid yet, inject one img tag per cid.
        img_html = (
            html_body
            if f"cid:{cid}" in html_body
            else html_body + f'<img src="cid:{cid}"/>'
        )
        if not html_body.endswith(img_html[-len(html_body) - len(f'<img src="cid:{cid}"/>') :]):
            # We rebuilt img_html because html_body had no cid references; reset.
            pass

        msg.add_attachment(
            _png_bytes(idx),
            maintype="image",
            subtype="png",
            cid=f"<{cid}>",
            filename=f"img{idx}.png",
        )

    # The above rebuild logic is brittle; use a simpler approach: build the
    # message parts fresh with HTML referencing the cid inline.
    msg2 = EmailMessage()
    msg2["Subject"] = subject
    msg2["From"] = "sender@example.com"
    msg2["To"] = "recipient@example.com"

    body_with_cids = html_body
    cids: list[str] = []
    for idx in range(n_images):
        cid = f"image_{idx}@test"
        cids.append(cid)
        body_with_cids += f'<img src="cid:{cid}"/>'

    msg2.set_content("Plain-text fallback")
    msg2.add_alternative(body_with_cids, subtype="html")
    for idx, cid in enumerate(cids):
        msg2.add_attachment(
            _png_bytes(idx),
            maintype="image",
            subtype="png",
            cid=f"<{cid}>",
            filename=f"img{idx}.png",
        )
    return msg2.as_bytes()


@pytest.fixture
def tmp_eml_factory(tmp_path: Path) -> Callable[..., Path]:
    """Factory that writes a .eml file to tmp_path and returns its path.

    Usage::

        def test_x(eml_factory):
            eml_path = eml_factory(subject="Caso A", n_images=2)
            ...

    Parameters
    ----------
    subject : str
        Email Subject header. Use distinct subjects to detect cross-contamination.
    html_body : str
        HTML body. Defaults to a minimal <p>Hola {name}</p> so HtmlEmailBuilder
        substitutes the recipient's first name.
    n_images : int
        How many inline images to attach. CIDs are image_0@test, image_1@test...
    suffix : str
        Filename suffix, default ".eml".
    """
    default_html = "<html><body><p>Hola {name}</p></body></html>"

    def _factory(
        subject: str = "Test Subject",
        html_body: str | None = None,
        n_images: int = 0,
        suffix: str = ".eml",
    ) -> Path:
        eml_path = tmp_path / f"fixture{suffix}"
        eml_path.write_bytes(
            _make_eml_bytes(
                subject=subject,
                html_body=html_body or default_html,
                n_images=n_images,
            )
        )
        return eml_path

    return _factory


# ---------------------------------------------------------------------------
# Re-exports so tests don't have to dig for project paths
# ---------------------------------------------------------------------------

@pytest.fixture
def staging_file() -> Path:
    """Path to the staging JSON file written by /api/send."""
    return _STAGING_FILE


@pytest.fixture
def progress_file() -> Path:
    return _PROGRESS_FILE


@pytest.fixture
def body_images_dir() -> Path:
    return _BODY_IMAGES_DIR


# ---------------------------------------------------------------------------
# Helper to load staging JSON in tests
# ---------------------------------------------------------------------------

def load_staging(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))
