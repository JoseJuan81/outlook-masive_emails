"""Shared fixtures for the regression test suite.

These fixtures isolate each test from global state in:

- ``web.app._session``               (in-memory dict, FastAPI app)
- ``html/images/body/``              (IMAGES_DIR used by save_images + send_from_staging)
- ``staging/emails_to_send.json``    (STAGING_FILE written by /api/send)
- ``staging/send_progress.json``     (PROGRESS_FILE)

The isolation is TOTAL: every path the code under test WRITES to lives under
``tmp_path``. The production code keeps its paths in module level constants,
so the autouse ``clean_state`` fixture repoints those constants at a temporary
directory for the duration of every test (see the redirection map below).

``html/images/body/`` deserves a note: its contents are NOT source assets but
the output of the last EML import (``import_email_template.save_images()``
wipes the directory and rewrites ``a.png``..``h.png``). Before this change the
suite wiped that REAL directory before AND after every test, which meant:

* two concurrent pytest runs clobbered each other, and
* a real dispatch running at that moment went out without images
  (``send_from_staging.get_images()`` returns ``[]`` on an empty directory).

Now the real directory is only READ, never written. The session-scoped
guardian ``_body_images_untouched`` compares it byte by byte against the
snapshot taken when this module was imported and FAILS the run if anything
changed it. That guardian is the net that catches a write path nobody
remembered to redirect.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Project paths (mirror the constants in web/app.py and send_from_staging.py)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The REAL repository paths. The suite only READS from them: the session
# guardian compares `html/images/body/` against the snapshot taken at import
# time and fails if anything changed it. Nothing here is ever written.
#
# The real staging files (`staging/emails_to_send.json` and
# `staging/send_progress.json`) are protected the same way: the redirection
# map below points every write at `tmp_path`, so the work in progress of the
# user is never deleted by a test run.
_BODY_IMAGES_DIR = _PROJECT_ROOT / "html" / "images" / "body"
_BODY_IMAGES_RELDIR = "html/images/body"


# ---------------------------------------------------------------------------
# Snapshot of the versioned body images
# ---------------------------------------------------------------------------
#
# Taken at import time, i.e. BEFORE any test runs, so it reflects the state the
# repository was in when the suite started. The snapshot is READ-ONLY from
# here on: the guardian compares against it, it never restores anything.


def _snapshot_dir(path: Path) -> dict[str, bytes]:
    """Map of file name -> content for every file directly inside `path`."""
    if not path.exists():
        return {}
    return {
        child.name: child.read_bytes()
        for child in path.iterdir()
        if child.is_file()
    }


def _restore_dir(path: Path, snapshot: dict[str, bytes]) -> None:
    """Put back the files of `snapshot` inside `path`.

    Files that already exist are left untouched: if another process (e.g. a
    fresh EML import) regenerated them, that version wins.

    NOTE: this helper is only exercised on TEMPORARY directories by the
    tests. The suite never restores anything inside the real repository.
    """
    path.mkdir(parents=True, exist_ok=True)
    for name, data in snapshot.items():
        target = path / name
        if not target.exists():
            target.write_bytes(data)


def _git_tracked_blobs(rel_dir: str) -> dict[str, bytes]:
    """Files versioned by git inside `rel_dir`, with their content at HEAD."""
    try:
        listado = subprocess.run(
            ["git", "ls-files", "--", rel_dir],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return {}

    blobs: dict[str, bytes] = {}
    for nombre in listado:
        try:
            blob = subprocess.run(
                ["git", "show", f"HEAD:{nombre}"],
                cwd=_PROJECT_ROOT,
                capture_output=True,
                check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        blobs[Path(nombre).name] = blob
    return blobs


def _snapshot_body_images() -> tuple[dict[str, bytes], set[str]]:
    """Original state of `html/images/body/`.

    What is in the working tree wins (it may be a fresh import). Files that git
    versions but that are missing from the working tree are taken from the git
    index, so the snapshot also covers the versioned PNGs the repository must
    never lose.

    Returns the snapshot and the names that had to be taken from git.
    """
    snapshot = _snapshot_dir(_BODY_IMAGES_DIR)
    from_git: set[str] = set()
    for nombre, blob in _git_tracked_blobs(_BODY_IMAGES_RELDIR).items():
        if nombre not in snapshot:
            snapshot[nombre] = blob
            from_git.add(nombre)
    return snapshot, from_git


_BODY_IMAGES_SNAPSHOT, _BODY_IMAGES_FROM_GIT = _snapshot_body_images()


# ---------------------------------------------------------------------------
# Isolated paths: everything the code under test WRITES lives under tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture
def staging_file(tmp_path: Path) -> Path:
    """Path to the staging JSON file written by /api/send (isolated)."""
    path = tmp_path / "staging" / "emails_to_send.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def progress_file(tmp_path: Path) -> Path:
    """Path to the progress JSON written while dispatching (isolated)."""
    path = tmp_path / "staging" / "send_progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def body_images_dir(tmp_path: Path) -> Path:
    """Directory where the inline images of the body are written (isolated)."""
    path = tmp_path / "body"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# autouse: clean global state and redirect every write path
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Reset the in-memory session and redirect every write path to tmp_path.

    Runs before AND after every test. We import the modules under test lazily
    so their top-level side effects (load_dotenv, setup_logging) happen once
    in the test session, not per fixture invocation.

    REDIRECTION MAP (module constant -> temporary path):

    - ``web.app._STAGING_FILE``             -> tmp staging JSON
    - ``web.app._PROGRESS_FILE``            -> tmp progress JSON
    - ``web.app._BODY_IMAGES_DIR``          -> tmp body images
    - ``import_email_template.IMAGES_DIR``  -> tmp body images
    - ``main._STAGING_FILE``                -> tmp staging JSON
    - ``send_from_staging._STAGING_FILE``   -> tmp staging JSON
    - ``send_from_staging._PROGRESS_FILE``  -> tmp progress JSON
    - ``send_from_staging._IMAGES_DIR``     -> tmp body images
    - ``outlook_desktop_adapter._BODY_IMAGES_DIR`` -> tmp body images
      (solo LEE, pero así sus tests no dependen del árbol de trabajo)

    NOTE: ``web/app.py`` mounts ``StaticFiles(directory=str(_BODY_IMAGES_DIR))``
    at IMPORT time, so the static mount keeps pointing at the real directory.
    That is correct: it only serves images, it never writes them.
    """
    staging = tmp_path / "staging" / "emails_to_send.json"
    progress = tmp_path / "staging" / "send_progress.json"
    body = tmp_path / "body"
    staging.parent.mkdir(parents=True, exist_ok=True)
    # El directorio de imágenes NO se crea aquí: lo crea la fixture
    # `body_images_dir`, que es la que lo expone a los tests. Crearlo en los
    # dos sitios haría colidir con los tests que crean su propio
    # `tmp_path / "body"`.

    import import_email_template
    import main
    import send_from_staging
    from infrastructure.adapters import outlook_desktop_adapter
    from web import app as web_app

    monkeypatch.setattr(web_app, "_STAGING_FILE", staging)
    monkeypatch.setattr(web_app, "_PROGRESS_FILE", progress)
    monkeypatch.setattr(web_app, "_BODY_IMAGES_DIR", body)
    monkeypatch.setattr(import_email_template, "IMAGES_DIR", body)
    monkeypatch.setattr(main, "_STAGING_FILE", staging)
    monkeypatch.setattr(send_from_staging, "_STAGING_FILE", staging)
    monkeypatch.setattr(send_from_staging, "_PROGRESS_FILE", progress)
    monkeypatch.setattr(send_from_staging, "_IMAGES_DIR", body)
    monkeypatch.setattr(outlook_desktop_adapter, "_BODY_IMAGES_DIR", body)

    _reset_session()
    yield
    _reset_session()


@pytest.fixture(scope="session", autouse=True)
def _body_images_untouched():
    """Guardián de sesión: el directorio real de imágenes no puede cambiar.

    Este guardián NO escribe nada: al final de la sesión compara el estado de
    `html/images/body/` con el snapshot tomado al importar este módulo (mismo
    conjunto de ficheros, mismos contenidos) y falla si algo lo modificó.

    Es la red que detecta un camino de escritura que nadie redirigió: si
    apareciera uno, la suite dejaría el repositorio sin sus PNG versionados
    (y un envío real en curso saldría sin imágenes).
    """
    yield
    assert _BODY_IMAGES_DIR.exists(), (
        "la suite borró el directorio real de imágenes del cuerpo: "
        f"{_BODY_IMAGES_DIR}"
    )
    finales = _snapshot_dir(_BODY_IMAGES_DIR)

    faltan = sorted(set(_BODY_IMAGES_SNAPSHOT) - set(finales))
    assert not faltan, (
        "la suite dejó fuera las imágenes versionadas del cuerpo: "
        f"{faltan}"
    )

    extras = sorted(set(finales) - set(_BODY_IMAGES_SNAPSHOT))
    assert not extras, (
        "la suite añadió ficheros al directorio real de imágenes del cuerpo: "
        f"{extras}"
    )

    cambiados = sorted(
        nombre
        for nombre in finales
        if finales[nombre] != _BODY_IMAGES_SNAPSHOT[nombre]
    )
    assert not cambiados, (
        "la suite modificó el contenido de las imágenes del cuerpo: "
        f"{cambiados}"
    )

    if _BODY_IMAGES_FROM_GIT:
        print(
            "[conftest] AVISO: estas imágenes versionadas por git no estaban en "
            "el árbol de trabajo al importar el conftest; el snapshot las cubre "
            f"desde HEAD: {sorted(_BODY_IMAGES_FROM_GIT)}",
            file=sys.stderr,
        )
    if not _BODY_IMAGES_SNAPSHOT:
        print(
            "[conftest] AVISO: el snapshot de html/images/body está vacío; "
            "no hay imágenes del cuerpo que vigilar. Si git versiona imágenes "
            "ahí, ejecuta `git restore html/images/body` antes de la suite.",
            file=sys.stderr,
        )


def _reset_session() -> None:
    """Reset the web.app._session dict to its initial empty state."""
    from web import app as web_app  # lazy import: triggers env load once
    web_app._session["subject"] = None
    web_app._session["html_body"] = None
    web_app._session["builder"] = None


def _wipe_dir(path: Path) -> None:
    """Empty a directory. Only ever called on TEMPORARY directories."""
    if path.exists():
        for child in path.iterdir():
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
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
# Helper to load staging JSON in tests
# ---------------------------------------------------------------------------


def load_staging(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))
