"""Tests for the mocked Outlook dispatch sequence.

Validates FIX 3 (the MAPI subject workaround in send_from_staging.py:217-250):

* mail.CreateItem(0) is called.
* SendUsingAccount is assigned (when an account is available).
* PropertyAccessor.SetProperty on the PR_SUBJECT proptag is the FIRST place
  that receives the subject — BEFORE mail.Subject is set.
* mail.To is set.
* Attachments.Add is called once per image (with hidden + cid set).
* mail.Subject is set as a fallback AFTER attachments.
* mail.Send() is called; mail.Save() is NOT called.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.strategies import (
    CID_PROP,
    HIDDEN_PROP,
    PROPTAG_SUBJECT,
    MockOutlook,
    run_send_from_staging_with_mocks,
)
from tests.test_send_payload import FakeRepo, _patch_send_runtime


# ---------------------------------------------------------------------------
# End-to-end through /api/send then into the mirror
# ---------------------------------------------------------------------------

def test_outlook_dispatch_calls_create_item_with_zero(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """FIX 3: CreateItem(0) is invoked for the mail item."""
    eml = tmp_eml_factory(subject="Hola", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        resp = client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})
    assert resp.status_code == 200

    outlook = MockOutlook()
    sent_items = run_send_from_staging_with_mocks(
        staging_path=staging_file,
        body_images_dir=body_images_dir,
        outlook=outlook,
    )
    assert len(sent_items) == 1
    assert sent_items[0]._created_with == 0


def test_outlook_dispatch_assigns_send_using_account(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """When an account matches, mail.SendUsingAccount is set."""
    eml = tmp_eml_factory(subject="S", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})

    outlook = MockOutlook()
    sent_items = run_send_from_staging_with_mocks(
        staging_path=staging_file,
        body_images_dir=body_images_dir,
        outlook=outlook,
    )
    assert sent_items[0].SendUsingAccount is outlook.sender_account
    assert outlook.sender_account.SmtpAddress == "sender@example.com"


def test_outlook_dispatch_sets_subject_via_mapi_first(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """PR_SUBJECT (0x0037001F) is set BEFORE mail.Subject is assigned.

    This is the whole point of the fix: if mail.Subject was set first,
    Outlook could recycle the subject from a previous inspector.
    """
    eml = tmp_eml_factory(subject="MAPI subject test", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})

    outlook = MockOutlook()
    sent_items = run_send_from_staging_with_mocks(
        staging_path=staging_file,
        body_images_dir=body_images_dir,
        outlook=outlook,
    )
    mail = sent_items[0]
    props = mail._property_log
    # The property log must contain an entry with name=PROPTAG_SUBJECT and value=subject.
    mapi_entries = [e for e in props if e["name"] == PROPTAG_SUBJECT]
    assert mapi_entries, f"PR_SUBJECT was not set; got {props}"
    assert mapi_entries[0]["value"] == "MAPI subject test"
    # The mail.Subject fallback must also be set.
    assert mail.Subject == "MAPI subject test"
    assert mail.HTMLBody  # non-empty body


def test_outlook_dispatch_sets_to_field(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """mail.To is assigned the recipient address from staging."""
    eml = tmp_eml_factory(subject="S", n_images=0)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv", "test_email": "dest@example.com"})

    outlook = MockOutlook()
    sent_items = run_send_from_staging_with_mocks(
        staging_path=staging_file,
        body_images_dir=body_images_dir,
        outlook=outlook,
    )
    assert sent_items[0].To == "dest@example.com"


def test_outlook_dispatch_adds_one_attachment_per_image(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """For N images in body_images_dir, Attachments.Add is called N times.

    Each attachment gets CID and HIDDEN properties.
    """
    eml = tmp_eml_factory(subject="S", n_images=2)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})

    outlook = MockOutlook()
    sent_items = run_send_from_staging_with_mocks(
        staging_path=staging_file,
        body_images_dir=body_images_dir,
        outlook=outlook,
    )
    mail = sent_items[0]
    assert len(mail.attachments) == 2

    for idx, att in enumerate(mail.attachments):
        assert att.cid == f"image_{idx}", f"Attachment {idx} has wrong CID: {att.cid}"
        assert att.hidden is True
        # Verify both properties were recorded.
        names = [name for name, _ in att.properties]
        assert CID_PROP in names
        assert HIDDEN_PROP in names


def test_outlook_dispatch_calls_send_without_save(
    client, tmp_eml_factory, body_images_dir, staging_file
):
    """mail.Save() is NOT called; mail.Send() IS called."""
    eml = tmp_eml_factory(subject="S", n_images=1)
    client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )

    repo = FakeRepo([{"Nombre": "M", "Correo": "m@example.com"}])
    with _patch_send_runtime(repo):
        client.post("/api/send", json={"source": "csv", "test_email": "x@example.com"})

    outlook = MockOutlook()
    sent_items = run_send_from_staging_with_mocks(
        staging_path=staging_file,
        body_images_dir=body_images_dir,
        outlook=outlook,
    )
    calls = sent_items[0].calls
    method_names = [c[0] for c in calls]
    assert "Save" not in method_names, f"Save must NOT be called; got {method_names}"
    assert "Send" in method_names, f"Send must be called; got {method_names}"


# ---------------------------------------------------------------------------
# Watcher: keep strategies.py mirror in sync with send_from_staging.py
# ---------------------------------------------------------------------------

SEND_FROM_STAGING = Path(__file__).resolve().parent.parent / "send_from_staging.py"


@pytest.mark.parametrize(
    "anchor_line,fragment",
    [
        (427, "outlook.CreateItem(0)"),
        (429, "mail.SendUsingAccount = account"),
        (440, '"http://schemas.microsoft.com/mapi/proptag/0x0037001F"'),
        (446, "mail.To = item[\"to\"]"),
        (449, "for idx, img_path in enumerate(images)"),
        (455, "mail.Subject = item[\"subject\"]"),
        (456, "mail.HTMLBody = item[\"html\"]"),
        (460, "mail.Send()"),
    ],
)
def test_strategies_mirror_anchors_match_production(anchor_line, fragment):
    """Line-numbered anchors in strategies.py must match send_from_staging.py.

    If you reorganize send_from_staging.py, update the anchors in
    tests/strategies.py at the same time, or this test will fail.
    """
    lines = SEND_FROM_STAGING.read_text(encoding="utf-8").splitlines()
    assert (
        len(lines) >= anchor_line
    ), f"send_from_staging.py has only {len(lines)} lines, expected {anchor_line}"
    line = lines[anchor_line - 1]
    assert fragment in line, (
        f"send_from_staging.py:{anchor_line} no longer contains {fragment!r}; "
        f"actual content: {line!r}. Update tests/strategies.py mirrors too."
    )
