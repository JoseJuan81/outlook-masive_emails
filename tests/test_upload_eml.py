"""Tests for POST /api/upload-eml.

Verifies:

* The endpoint extracts subject, html body and inline images and stores
  them in ``web.app._session``.
* Calling the endpoint a second time REPLACES state — no leakage from a
  prior load (FIX 2: contamination guard).
* ``save_images`` wipes ``html/images/body/`` before writing the new set,
  so the directory never accumulates files across uploads.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_upload_eml_populates_session(client, tmp_eml_factory, body_images_dir):
    """First upload populates _session with the parsed subject + builder."""
    eml = tmp_eml_factory(subject="Caso A", n_images=2)

    resp = client.post(
        "/api/upload-eml",
        files={"file": ("caso_a.eml", eml.read_bytes(), "message/rfc822")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject"] == "Caso A"
    assert body["images_count"] == 2

    # _session should now hold the builder + subject.
    from web import app as web_app
    assert web_app._session["subject"] == "Caso A"
    assert web_app._session["builder"] is not None
    assert web_app._session["html_body"] is not None


def test_upload_eml_replaces_session_on_second_upload(
    client, tmp_eml_factory, body_images_dir
):
    """Second upload completely overwrites prior state (no leakage)."""
    # First upload: subject="Caso A", 2 images
    eml_a = tmp_eml_factory(subject="Caso A", n_images=2)
    resp_a = client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml_a.read_bytes(), "message/rfc822")},
    )
    assert resp_a.status_code == 200
    assert resp_a.json()["subject"] == "Caso A"

    # Second upload: subject="Caso B", 1 image
    eml_b = tmp_eml_factory(subject="Caso B", n_images=1)
    resp_b = client.post(
        "/api/upload-eml",
        files={"file": ("b.eml", eml_b.read_bytes(), "message/rfc822")},
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["subject"] == "Caso B"

    # _session.subject must reflect Caso B (not "Caso A" or anything stale)
    from web import app as web_app
    assert web_app._session["subject"] == "Caso B", (
        "Subject contamination: session still holds the previous upload"
    )

    # _session.builder must have been replaced (different instance or at
    # least different output).
    builder = web_app._session["builder"]
    assert builder is not None
    rendered = builder.build("Juan")
    assert "Juan" in rendered


def test_upload_eml_save_images_wipes_directory_on_each_load(
    client, tmp_eml_factory, body_images_dir
):
    """FIX 2 supporting check: save_images clears old images before writing new ones."""
    # First upload: 3 images -> 3 files in body_images_dir.
    eml_a = tmp_eml_factory(subject="Caso A", n_images=3)
    resp_a = client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml_a.read_bytes(), "message/rfc822")},
    )
    assert resp_a.status_code == 200
    files_after_a = sorted(p.name for p in body_images_dir.iterdir())
    assert len(files_after_a) == 3, files_after_a

    # Second upload: 1 image -> exactly 1 file, not 3+1=4 mixed up.
    eml_b = tmp_eml_factory(subject="Caso B", n_images=1)
    resp_b = client.post(
        "/api/upload-eml",
        files={"file": ("b.eml", eml_b.read_bytes(), "message/rfc822")},
    )
    assert resp_b.status_code == 200

    files_after_b = sorted(p.name for p in body_images_dir.iterdir())
    assert len(files_after_b) == 1, (
        f"save_images did not wipe existing files; dir contains: {files_after_b}"
    )


def test_upload_eml_rejects_unsupported_extension(client, tmp_path):
    """Endpoint rejects anything that's not .eml or .msg."""
    bogus = tmp_path / "foo.txt"
    bogus.write_bytes(b"hello")
    resp = client.post(
        "/api/upload-eml",
        files={"file": ("foo.txt", bogus.read_bytes(), "text/plain")},
    )
    assert resp.status_code == 400, resp.text


def test_upload_eml_rejects_empty_filename(client, tmp_path):
    """Missing filename is a 400."""
    resp = client.post(
        "/api/upload-eml",
        files={"file": ("", b"", "message/rfc822")},
    )
    # FastAPI/Starlette may surface this as 422 (validation) or 400 — accept either
    assert resp.status_code in (400, 422), resp.text
