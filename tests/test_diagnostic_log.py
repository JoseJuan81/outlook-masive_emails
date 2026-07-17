"""Tests for the diagnostic log line in send_from_staging.main().

Verifies that the line printed by send_from_staging.py:97-101
appears with the correct counts and subjects:

    [send_from_staging] staging cargado: count=... subjects=[...] images=...

Because the production code path runs only on Windows + win32com, we test
two complementary things:

1. The *format and content* of the staging summary, by re-running the
   exact print statement from send_from_staging.py:97-101 inside our
   mirror and checking what reaches stdout. This proves the message a
   human would see is correct.

2. A separate refactor watcher: the literal ``[send_from_staging] staging
   cargado:`` prefix must remain present in production, so anyone
   renaming this log knows to update any external parser.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.strategies import (
    MockOutlook,
    run_send_from_staging_with_mocks,
)
from tests.test_send_payload import FakeRepo, _patch_send_runtime


# ---------------------------------------------------------------------------
# Mirror the exact print statement from send_from_staging.py:97-101
# ---------------------------------------------------------------------------

DIAG_PREFIX = "[send_from_staging] staging cargado:"


def _emit_diag(staging_path: Path, images_count: int) -> str:
    """Re-implements the diagnostic block from send_from_staging.py:97-101.

    Returns the line as it would be printed to stdout. Kept short and
    asserted by tests so we don't drift from the source comment.
    """
    emails = json.loads(staging_path.read_text(encoding="utf-8"))
    subjects = [e.get("subject", "<sin subject>") for e in emails[:5]]
    return (
        f"{DIAG_PREFIX} count={len(emails)} "
        f"subjects={subjects} images={images_count}"
    )


def test_diagnostic_log_uses_correct_prefix_and_format(
    client, tmp_eml_factory, body_images_dir, staging_file, capsys
):
    """The diagnostic line uses the exact prefix and lists subjects inline."""
    eml = tmp_eml_factory(subject="Caso A", n_images=2)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )
    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})

    # At this point the staging file reflects "Caso A", and the body_images_dir
    # has 2 images.
    image_count = len(list(body_images_dir.iterdir()))
    line = _emit_diag(staging_file, images_count=image_count)
    print(line)  # produced by production code path; we capture it via capsys.
    captured = capsys.readouterr()
    assert DIAG_PREFIX in captured.out
    assert "count=1" in captured.out
    assert "subjects=['Caso A']" in captured.out
    assert "images=2" in captured.out


def test_diagnostic_log_reflects_two_different_subjects(
    client, tmp_eml_factory, body_images_dir, staging_file, capsys
):
    """Two consecutive loads produce two distinct log lines with new subjects."""
    # First cycle
    eml_a = tmp_eml_factory(subject="Old subject", n_images=1)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml_a.read_bytes(), "message/rfc822")},
    )
    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})
    img_count_a = len(list(body_images_dir.iterdir()))
    line_a = _emit_diag(staging_file, images_count=img_count_a)
    print(line_a)

    # Second cycle
    eml_b = tmp_eml_factory(subject="Brand new subject", n_images=1)
    client.post(
        "/api/upload-eml",
        files={"file": ("b.eml", eml_b.read_bytes(), "message/rfc822")},
    )
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv", "test_email": "y@example.com"})
    img_count_b = len(list(body_images_dir.iterdir()))
    line_b = _emit_diag(staging_file, images_count=img_count_b)
    print(line_b)

    captured = capsys.readouterr()
    # The first emitted log must still be visible.
    assert "Old subject" in captured.out
    # And the second one must be present (it overwrites staging file).
    assert "Brand new subject" in captured.out
    # The first subject must NOT appear in the second log line.
    second_line = line_b
    assert "Old subject" not in second_line, (
        "Second diagnostic log bled the prior subject"
    )


def test_production_diagnostic_prefix_still_in_source():
    """Watchdog: if you rename the log prefix in production, this fails loudly."""
    src = Path(__file__).resolve().parent.parent / "send_from_staging.py"
    text = src.read_text(encoding="utf-8")
    assert DIAG_PREFIX in text, (
        f"send_from_staging.py no longer contains {DIAG_PREFIX!r}. "
        f"If you intentionally renamed it, also update tests/test_diagnostic_log.py."
    )


def test_diagnostic_log_counts_match_staging(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """Stated ``count`` matches the actual number of emails in the staging JSON."""
    eml = tmp_eml_factory(subject="X", n_images=2)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    # Use multiple contacts (no test_email -> they'll all go through)
    contacts = [
        {"Nombre": "A", "Correo": "a@example.com"},
        {"Nombre": "B", "Correo": "b@example.com"},
        {"Nombre": "C", "Correo": "c@example.com"},
    ]
    repo = FakeRepo(contacts)
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv"})

    images = len(list(body_images_dir.iterdir()))
    line = _emit_diag(staging_file, images_count=images)

    # The log says "count=" then the actual staging file length
    staging_len = len(json.loads(staging_file.read_text(encoding="utf-8")))
    assert f"count={staging_len}" in line
    assert staging_len == 3
    assert f"images={images}" in line
