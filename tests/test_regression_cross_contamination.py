"""End-to-end regression: cross-contamination between two consecutive EML loads.

This is the bug the user actually reported: load EML A, send, then load EML B
and send -- the second send inherits "Caso A"'s subject or its images.

We simulate the full happy path twice in the same test, with NO process
isolation in between, so any global state leakage is observable.
"""

from __future__ import annotations

import json

import pytest

from tests.strategies import (
    MockOutlook,
    run_send_from_staging_with_mocks,
)
from tests.test_send_payload import FakeRepo, _patch_send_runtime


def test_two_consecutive_emls_do_not_contaminate_each_other(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """Two complete load -> /api/send -> mock-dispatch cycles must be isolated.

    Cycle 1:
        upload "Caso A" with 2 images -> /api/send -> mock dispatch
    Cycle 2:
        upload "Caso B" with 3 images -> /api/send -> mock dispatch
    Assertions:
        - First dispatch sees subject="Caso A" and 2 images
        - Second dispatch sees subject="Caso B" and 3 images (NOT 5 mixed up)
        - body_images_dir has exactly 3 files at the end of cycle 2
          (proving save_images wiped between cycles).
    """
    # -------- Cycle 1: Caso A, 2 images --------
    eml_a = tmp_eml_factory(subject="Caso A", n_images=2)
    r_upload = client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml_a.read_bytes(), "message/rfc822")},
    )
    assert r_upload.status_code == 200, r_upload.text

    # Sanity: 2 image files written
    assert len(list(body_images_dir.iterdir())) == 2

    # Mock run for cycle 1
    repo_a = FakeRepo([{"Nombre": "Maria", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo_a):
        r_send_a = client.post(
            "/api/send",
            json={"source": "csv", "test_email": "stage1@example.com"},
        )
    assert r_send_a.status_code == 200
    assert staging_file.exists()

    # Confirm cycle 1 staging used "Caso A"
    staging_a = json.loads(staging_file.read_text(encoding="utf-8"))
    assert staging_a[0]["subject"] == "Caso A"

    # Dispatch cycle 1 with our mock and verify
    outlook_a = MockOutlook()
    sent_a = run_send_from_staging_with_mocks(
        staging_path=staging_file,
        body_images_dir=body_images_dir,
        outlook=outlook_a,
    )
    assert len(sent_a) == 1
    assert sent_a[0].Subject == "Caso A"
    assert sent_a[0].To == "stage1@example.com"
    assert len(sent_a[0].attachments) == 2

    # -------- Cycle 2: Caso B, 3 images --------
    eml_b = tmp_eml_factory(subject="Caso B", n_images=3)
    r_upload_b = client.post(
        "/api/upload-eml",
        files={"file": ("b.eml", eml_b.read_bytes(), "message/rfc822")},
    )
    assert r_upload_b.status_code == 200, r_upload_b.text
    # 2 -> 3, NOT 2+3=5
    assert len(list(body_images_dir.iterdir())) == 3, (
        "save_images did not wipe Caso A's 2 images before writing Caso B's 3"
    )

    # Mock run for cycle 2
    repo_b = FakeRepo([{"Nombre": "Juan", "Correo": "j@example.com"}])
    with _patch_send_runtime(repo_b):
        r_send_b = client.post(
            "/api/send",
            json={"source": "csv", "test_email": "stage2@example.com"},
        )
    assert r_send_b.status_code == 200

    staging_b = json.loads(staging_file.read_text(encoding="utf-8"))
    assert staging_b[0]["subject"] == "Caso B"

    # Dispatch cycle 2 -- THE KEY ASSERTION: subject must be "Caso B", NOT "Caso A"
    outlook_b = MockOutlook()
    sent_b = run_send_from_staging_with_mocks(
        staging_path=staging_file,
        body_images_dir=body_images_dir,
        outlook=outlook_b,
    )
    assert len(sent_b) == 1
    assert sent_b[0].Subject == "Caso B", (
        f"Subject recycled from previous dispatch: {sent_b[0].Subject!r}"
    )
    assert sent_b[0].To == "stage2@example.com"
    # 3 attachments only (no leftover from cycle 1)
    assert len(sent_b[0].attachments) == 3, (
        f"Attachment count contaminated: got {len(sent_b[0].attachments)}, expected 3"
    )

    # Also verify the MAPI proptag (the original bug surface) gets the right value
    props_b = sent_b[0]._property_log
    mapi_b = [e for e in props_b if e["name"].endswith("0x0037001F")]
    assert mapi_b and mapi_b[0]["value"] == "Caso B", (
        f"PR_SUBJECT still holds Caso A: {mapi_b}"
    )


def test_session_subject_does_not_bleed_into_subsequent_send(
    client, tmp_eml_factory, staging_file
):
    """Tight regression: session.subject is what /api/send writes to staging.

    Loads once with subject X, sends twice in a row. The staging file's
    subject must equal X on both calls -- proves there is no internal
    state corruption between calls.
    """
    eml = tmp_eml_factory(subject="Cold Start", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("x.eml", eml.read_bytes(), "message/rfc822")},
    )
    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])

    with _patch_send_runtime(repo):
        r1 = client.post("/api/send", json={"source": "csv", "test_email": "1@x.com"})
    assert r1.status_code == 200

    first = json.loads(staging_file.read_text(encoding="utf-8"))
    assert first[0]["subject"] == "Cold Start"

    # Re-send immediately (no new upload). Session subject is unchanged.
    with _patch_send_runtime(repo):
        r2 = client.post("/api/send", json={"source": "csv", "test_email": "2@x.com"})
    assert r2.status_code == 200

    second = json.loads(staging_file.read_text(encoding="utf-8"))
    assert second[0]["subject"] == "Cold Start"
    assert second[0]["to"] == "2@x.com"


def test_save_images_avoids_orphan_files_across_cycles(
    client, tmp_eml_factory, body_images_dir
):
    """save_images must NOT leave stale files from a previous load.

    Note: save_images is only invoked when inline_images is non-empty
    (see web/app.py: ``if inline_images:``). So this test only asserts the
    invariant between loads that DO carry images.
    """
    # Cycle 1: 4 images
    eml_a = tmp_eml_factory(subject="X", n_images=4)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml_a.read_bytes(), "message/rfc822")},
    )
    files = sorted(p.name for p in body_images_dir.iterdir() if p.is_file())
    assert len(files) == 4, files

    # Cycle 2: 1 image -- must fully replace cycle 1's files
    eml_b = tmp_eml_factory(subject="Y", n_images=1)
    client.post(
        "/api/upload-eml",
        files={"file": ("b.eml", eml_b.read_bytes(), "message/rfc822")},
    )
    files = sorted(p.name for p in body_images_dir.iterdir() if p.is_file())
    assert len(files) == 1, files

    # Cycle 3: 0 images -- endpoint does NOT call save_images, so the previous
    # image stays. Documented behavior: a zero-image load doesn't trigger
    # the wipe (the production endpoint has ``if inline_images:`` guard).
    eml_c = tmp_eml_factory(subject="Z", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("c.eml", eml_c.read_bytes(), "message/rfc822")},
    )
    files = sorted(p.name for p in body_images_dir.iterdir() if p.is_file())
    assert len(files) == 1, files  # the one from cycle 2 is still there
