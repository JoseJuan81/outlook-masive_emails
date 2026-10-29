"""Tests for POST /api/send.

Validates FIX 1 (write+flush+fsync in web/app.py:295-299) and the staging
JSON contract:

* The file written to disk contains exactly the staged emails.
* `count` matches the contacts returned by the repository.
* ``test_email`` overrides recipients to a single address.
* When using ``test_email``, the staging payload uses the uploaded subject
  (not a recycled one from a prior load).
"""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.durable_write import EspiaDurabilidad


class FakeRepo:
    """Minimal stand-in for a real contact repository."""

    def __init__(self, contacts):
        self._contacts = contacts

    def get_contacts(self):
        return self._contacts


class FakeCompletedProcess:
    """Stand-in for subprocess.run's return value (used for wslpath)."""

    def __init__(self, stdout="C:\\fake\\path\\send_from_staging.py"):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


@contextmanager
def _patch_send_runtime(repo):
    """Stub out everything /api/send needs beyond the staging write:

    * the contact repository factory
    * subprocess.run (used to call wslpath)
    * subprocess.Popen  (used to launch send_from_staging.py)
    """
    popens: list[MagicMock] = []
    from web import app as web_app

    def fake_popen(*args, **kwargs):
        m = MagicMock()
        popens.append(m)
        return m

    def fake_run(*args, **kwargs):
        # The endpoint calls subprocess.run(["wslpath", "-w", ...]) once.
        return FakeCompletedProcess()

    web_app._send_process = None
    with patch.object(web_app, "_build_repository", return_value=repo), \
         patch.object(subprocess, "Popen", side_effect=fake_popen), \
         patch.object(subprocess, "run", side_effect=fake_run):
        yield popens


def test_api_send_writes_staging_with_correct_subject(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """`/api/send` must write the staging JSON with the session's current subject."""
    eml = tmp_eml_factory(subject="Caso B", n_images=2)
    upload = client.post(
        "/api/upload-eml",
        files={"file": ("b.eml", eml.read_bytes(), "message/rfc822")},
    )
    assert upload.status_code == 200

    repo = FakeRepo([{"Nombre": "Maria Lopez", "Correo": "maria@example.com"}])
    with _patch_send_runtime(repo):
        resp = client.post(
            "/api/send",
            json={"source": "csv", "test_email": "staging@example.com"},
        )

    assert resp.status_code == 200, resp.text
    assert staging_file.exists(), "staging JSON was not written"

    staged = json.loads(staging_file.read_text(encoding="utf-8"))
    assert len(staged) == 1
    assert staged[0]["subject"] == "Caso B"
    assert staged[0]["to"] == "staging@example.com"


def test_api_send_uses_test_email_override(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """All staged recipients collapse to test_email when provided."""
    eml = tmp_eml_factory(subject="Cualquiera", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("x.eml", eml.read_bytes(), "message/rfc822")},
    )

    contacts = [
        {"Nombre": "A", "Correo": "a@example.com"},
        {"Nombre": "B", "Correo": "b@example.com"},
    ]
    repo = FakeRepo(contacts)
    with _patch_send_runtime(repo):
        resp = client.post(
            "/api/send",
            json={"source": "csv", "test_email": "only@example.com"},
        )

    assert resp.status_code == 200
    staged = json.loads(staging_file.read_text(encoding="utf-8"))
    assert [e["to"] for e in staged] == ["only@example.com"]
    assert len(staged) == 1  # test_email short-circuits the loop


def test_api_send_uses_session_subject_not_stale(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """Regression for bug A: after a second upload, staging must use the NEW subject.

    Scenario:
        load "Caso A" -> send -> load "Caso B" -> send
    The second staging file must contain "Caso B", not "Caso A".
    """
    # First upload + send (we don't really care about the first staging contents)
    eml_a = tmp_eml_factory(subject="Caso A", n_images=1)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml_a.read_bytes(), "message/rfc822")},
    )
    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        r1 = client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})
    assert r1.status_code == 200

    # Second upload with NEW subject
    eml_b = tmp_eml_factory(subject="Caso B", n_images=1)
    client.post(
        "/api/upload-eml",
        files={"file": ("b.eml", eml_b.read_bytes(), "message/rfc822")},
    )
    with _patch_send_runtime(repo):
        r2 = client.post("/api/send", json={"source": "csv", "test_email": "y@example.com"})
    assert r2.status_code == 200

    staged = json.loads(staging_file.read_text(encoding="utf-8"))
    assert all(e["subject"] == "Caso B" for e in staged), (
        f"Staging file leaked the previous subject: {[e['subject'] for e in staged]}"
    )


def test_api_send_rejects_when_no_eml_loaded(client):
    """No upload = no builder = 400."""
    resp = client.post(
        "/api/send",
        json={"source": "csv", "test_email": "x@example.com"},
    )
    assert resp.status_code == 400, resp.text
    assert "Upload" in resp.text or "upload" in resp.text.lower()


def test_api_send_rejects_when_source_missing(client, tmp_eml_factory):
    """Missing 'source' in payload -> 400."""
    eml = tmp_eml_factory(subject="S", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )
    resp = client.post("/api/send", json={"test_email": "x@example.com"})
    assert resp.status_code == 400, resp.text


def test_api_send_rejects_when_repository_empty(client, tmp_eml_factory):
    """Empty contact list -> 400."""
    eml = tmp_eml_factory(subject="S", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )
    repo = FakeRepo([])
    with _patch_send_runtime(repo):
        resp = client.post(
            "/api/send",
            json={"source": "csv", "test_email": "x@example.com"},
        )
    assert resp.status_code == 400, resp.text


def test_api_send_flushes_and_fsyncs_staging_file(
    client, tmp_eml_factory, body_images_dir, staging_file, monkeypatch
):
    """FIX 1: write + flush + fsync are all called on the staging file.

    We instrument ``os.fsync`` to confirm it was invoked on the staging
    file's fileno after the write.
    """
    eml = tmp_eml_factory(subject="Caso X", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def spy_fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", spy_fsync)

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        resp = client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})

    assert resp.status_code == 200
    assert len(fsync_calls) >= 1, "fsync was not called on the staging file"
    assert staging_file.exists()
    data = staging_file.read_text(encoding="utf-8")
    assert "Caso X" in data


def test_api_send_hace_flush_del_staging_antes_del_fsync(
    client, tmp_eml_factory, body_images_dir, staging_file, monkeypatch
):
    """FIX 1: el staging recibe ``flush()`` y el flush va ANTES del ``fsync``.

    ``fh.flush()`` es lo que baja el buffer de Python al descriptor. Si
    desaparece, el ``os.fsync()`` sincroniza un fichero vacío y el staging se
    pierde: por eso el orden importa, no solo que ocurran.
    """
    from web import app as web_app

    eml = tmp_eml_factory(subject="Caso Flush", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    espia = EspiaDurabilidad(monkeypatch, web_app)

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        resp = client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})

    assert resp.status_code == 200
    assert espia.flushes() >= 1, (
        "el staging no recibió flush(): los bytes pueden quedarse en el buffer "
        "de Python y el fsync sincronizaría un fichero vacío"
    )
    assert espia.fsyncs() >= 1, "el staging no recibió os.fsync()"
    assert espia.nombres().index("flush") < espia.nombres().index("fsync"), (
        f"el flush() debe ocurrir antes del fsync(); eventos: {espia.nombres()}"
    )


def test_api_send_tiene_los_bytes_en_el_staging_cuando_hace_fsync(
    client, tmp_eml_factory, body_images_dir, staging_file, monkeypatch
):
    """Cuando se llama a ``os.fsync()``, el JSON ya está en el fichero.

    Es la garantía de fondo del ``flush()``: el tamaño que el SO ve en el
    descriptor tiene que ser el del JSON escrito. Sin el flush, el tamaño
    sería 0 (los bytes siguen en el buffer de Python) y el fsync no
    garantizaría nada.
    """
    eml = tmp_eml_factory(subject="Caso Bytes", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    tamanos: list[int] = []
    inodos: list[int] = []
    fsync_real = os.fsync

    def spy_fsync(fd):
        estado = os.fstat(fd)
        tamanos.append(estado.st_size)
        inodos.append(estado.st_ino)
        return fsync_real(fd)

    monkeypatch.setattr(os, "fsync", spy_fsync)

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        resp = client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})

    assert resp.status_code == 200
    assert tamanos, "os.fsync() no se llamó sobre el staging"
    assert tamanos[0] > 0, (
        "en el momento del fsync el staging estaba vacío en disco: "
        "falta el fh.flush() que vuelca el buffer de Python al descriptor"
    )
    # El fsync tiene que ser sobre el fichero de staging, no sobre otro.
    assert inodos[0] == os.stat(staging_file).st_ino, (
        "el fsync no se hizo sobre el fichero de staging"
    )

