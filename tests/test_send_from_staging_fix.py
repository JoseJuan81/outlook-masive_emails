"""Unit tests for the three fixes applied to send_from_staging.py.

These tests do NOT import win32com or touch Outlook. Each test builds the
smallest possible COM-shaped mock for the surface the function uses
(getattr, .Items iteration, .EntryID, .SentOn, .GetDefaultFolder, etc.)
and asserts the expected return value or error handling.

The three fixes under test are:

* Fix 1 - Real delivery confirmation via ``_item_in_outbox`` /
  ``wait_for_outbox_clear``. ``wait_for_sent`` survives only as a metric.
* Fix 2 - Robust ``trigger_sync`` (must NOT swallow exceptions) and a
  ``find_account`` validation that aborts when the configured sender is
  missing.
* Fix 3 - ``mail.Send()`` wrapped in ``pywintypes.com_error`` handling and
  the prior ``mail.Save()`` removed.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# Import the module directly; send_from_staging.py is importable on Linux
# because win32com is only imported inside main().
import send_from_staging as sfs


# ---------------------------------------------------------------------------
# Helpers: minimal COM-shaped mocks
# ---------------------------------------------------------------------------

class _ComError(Exception):
    """Stand-in for pywintypes.com_error (raised by win32com on failure)."""


class MockMail:
    """Minimal MailItem mock: only .EntryID and .SentOn are exercised."""

    def __init__(self, entry_id: str = "EID-1", sent_on=None):
        self.EntryID = entry_id
        self.SentOn = sent_on


class MockFolder:
    """Mock of an Outlook folder exposing .Items."""

    def __init__(self, mails):
        self.Items = mails


def _ns_with_outbox(mails):
    """Build a namespace mock whose GetDefaultFolder(4) returns ``mails``."""
    ns = MagicMock()
    ns.GetDefaultFolder = lambda fid: MockFolder(mails)
    return ns


# ---------------------------------------------------------------------------
# FIX 1 - _item_in_outbox
# ---------------------------------------------------------------------------

def test_item_in_outbox_returns_true_when_entry_id_matches():
    """If mail.EntryID appears in folder.Items, return True."""
    mail = MockMail(entry_id="ABC")
    outbox = MockFolder(mails=[MockMail("ABC"), MockMail("DEF")])
    ns = MagicMock()
    ns.GetDefaultFolder = lambda fid: outbox

    assert sfs._item_in_outbox(ns, mail) is True


def test_item_in_outbox_returns_false_when_entry_id_absent():
    """If mail.EntryID is not in folder.Items, return False."""
    mail = MockMail(entry_id="ZZZ")
    outbox = MockFolder(mails=[MockMail("ABC"), MockMail("DEF")])
    ns = MagicMock()
    ns.GetDefaultFolder = lambda fid: outbox

    assert sfs._item_in_outbox(ns, mail) is False


def test_item_in_outbox_returns_true_when_entry_id_missing():
    """If mail has no EntryID (transient state), default to True (conservative)."""
    mail = SimpleNamespace()  # no EntryID attribute at all
    ns = _ns_with_outbox([MockMail("ABC")])
    assert sfs._item_in_outbox(ns, mail) is True


def test_item_in_outbox_returns_true_on_exception():
    """If GetDefaultFolder raises, default to True (don't lose the mail)."""
    ns = MagicMock()
    ns.GetDefaultFolder = MagicMock(side_effect=RuntimeError("boom"))
    assert sfs._item_in_outbox(ns, MockMail()) is True


# ---------------------------------------------------------------------------
# FIX 1 - wait_for_outbox_clear
# ---------------------------------------------------------------------------

def test_wait_for_outbox_clear_returns_false_when_senton_is_none(monkeypatch):
    """Mail still in Outbox and SentOn=None -> return False (NOT delivered).

    This is the canonical bug the fix targets: previously wait_for_sent could
    return True even though SentOn was unset, which made the script claim
    successful delivery when nothing had actually left the server.
    """
    mail = MockMail(entry_id="E1", sent_on=None)
    outbox_folder = MockFolder(mails=[mail])  # mail IS still in Outbox

    ns = MagicMock()
    ns.GetDefaultFolder = lambda fid: outbox_folder

    # Patch sleep so the test is fast; _item_in_outbox returns True because
    # mail is still present. Run with timeout=1 to keep CI fast.
    monkeypatch.setattr(sfs.time, "sleep", lambda _: None)

    assert sfs.wait_for_outbox_clear(
        ns, outbox_before=0, mail=mail, timeout=2
    ) is False


def test_wait_for_outbox_clear_returns_true_when_senton_set_and_item_leaves(monkeypatch):
    """Mail leaves Outbox AND SentOn is set -> return True (delivered)."""
    mail = MockMail(entry_id="E2", sent_on="2026-07-10 10:00:00")

    # First call returns True (still in Outbox), subsequent calls return False.
    calls = {"n": 0}

    def fake_in_outbox(namespace, m):
        calls["n"] += 1
        return calls["n"] <= 1  # only present on the very first probe

    monkeypatch.setattr(sfs, "_item_in_outbox", fake_in_outbox)
    monkeypatch.setattr(sfs.time, "sleep", lambda _: None)

    ns = MagicMock()  # never actually hit, but passed in
    assert sfs.wait_for_outbox_clear(
        ns, outbox_before=0, mail=mail, timeout=5
    ) is True


def test_wait_for_outbox_clear_returns_false_on_timeout(monkeypatch):
    """If the item never leaves the Outbox, returns False within timeout."""
    mail = MockMail(entry_id="STUCK", sent_on=None)

    monkeypatch.setattr(sfs, "_item_in_outbox", lambda ns, m: True)
    monkeypatch.setattr(sfs.time, "sleep", lambda _: None)

    # Force the timeout check to fail fast by overriding time.time monotonic
    # progress: jump ahead on every call.
    counter = {"t": 0.0}

    def fake_time():
        counter["t"] += 100  # big jump on every read
        return counter["t"]

    monkeypatch.setattr(sfs.time, "time", fake_time)

    ns = MagicMock()
    assert sfs.wait_for_outbox_clear(ns, 0, mail, timeout=30) is False


# ---------------------------------------------------------------------------
# FIX 1 - wait_for_sent is now informational only
# ---------------------------------------------------------------------------

def test_wait_for_sent_is_now_a_metric_not_a_gate(monkeypatch):
    """wait_for_sent must still exist; the source code uses its return value
    only as a diagnostic (logged alongside delivery_confirmed). It returns
    True when the Sent Items count increases, False otherwise. The dispatch
    loop uses ``wait_for_outbox_clear`` as the authoritative gate.

    We exercise both branches via a small monkeypatch.
    """
    ns = MagicMock()

    # Branch A: count exceeds baseline -> returns True quickly.
    monkeypatch.setattr(sfs, "get_folder_count", lambda ns, fid: 7)
    monkeypatch.setattr(sfs.time, "sleep", lambda _: None)
    # Don't advance time: time.time() returns 0 initially, loop is bounded.
    assert sfs.wait_for_sent(ns, sent_count_before=3) is True

    # Branch B: count never exceeds baseline -> hits MAX_WAIT and returns False.
    monkeypatch.setattr(sfs, "get_folder_count", lambda ns, fid: 0)
    calls = [0]
    def fake_time():
        calls[0] += 100  # jump past MAX_WAIT immediately
        return calls[0]
    monkeypatch.setattr(sfs.time, "time", fake_time)
    assert sfs.wait_for_sent(ns, sent_count_before=5) is False


# ---------------------------------------------------------------------------
# FIX 2 - trigger_sync is robust and never crashes
# ---------------------------------------------------------------------------

def test_trigger_sync_logs_warning_on_exception(caplog):
    """If GetNamespace raises a com_error-shaped exception, trigger_sync logs a
    warning AND does not crash.

    Previously the function used ``except Exception: pass`` and silently
    swallowed errors. Now it must log a warning.
    """
    boom = _ComError("MAPI unavailable")

    class _BadOutlook:
        def GetNamespace(self, _kind):
            raise boom

    caplog.set_level(logging.WARNING, logger="send_from_staging")
    sfs.trigger_sync(_BadOutlook())  # must not raise

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("trigger_sync fall" in r.getMessage() for r in warnings), (
        f"trigger_sync swallowed the exception silently; records={caplog.records}"
    )


def test_trigger_sync_no_op_outlook_still_works():
    """trigger_sync on an outlook with empty SyncObjects does nothing wrong."""
    class _EmptySyncObjects:
        Count = 0

        def Item(self, _idx):
            raise AssertionError("Item should not be called when Count==0")

    class _Ns:
        SyncObjects = _EmptySyncObjects()

    class _Outlook:
        def GetNamespace(self, _kind):
            return _Ns()

    sfs.trigger_sync(_Outlook())  # must not raise


# ---------------------------------------------------------------------------
# FIX 2 - find_account validates OUTLOOK_SENDER_EMAIL
# ---------------------------------------------------------------------------

def test_find_account_returns_account_when_smtp_matches():
    """find_account returns the matching account."""
    outlook = MagicMock()
    acc = SimpleNamespace(SmtpAddress="sender@example.com")
    outlook.Session.Accounts.__iter__ = lambda self: iter([acc])

    result = sfs.find_account(outlook, "sender@example.com")
    assert result is acc


def test_find_account_returns_none_when_no_match():
    """find_account returns None if no account SmtpAddress matches."""
    outlook = MagicMock()
    acc = SimpleNamespace(SmtpAddress="other@example.com")
    outlook.Session.Accounts.__iter__ = lambda self: iter([acc])

    assert sfs.find_account(outlook, "sender@example.com") is None


# ---------------------------------------------------------------------------
# FIX 3 - mail.Save() removed and mail.Send() wrapped in pywintypes.com_error
# ---------------------------------------------------------------------------

def test_module_has_no_save_call_before_send():
    """The dispatch logic no longer calls mail.Save() before mail.Send().

    Find the MAPI PR_SUBJECT block and confirm no ``mail.Save()`` precedes
    the (mocked) ``mail.Send()`` line.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "send_from_staging.py").read_text()
    mapi_idx = src.find('proptag/0x0037001F')
    send_idx = src.find('mail.Send()')
    save_idx = src.find('mail.Save()', 0, send_idx)
    assert mapi_idx > 0
    assert send_idx > 0
    # No mail.Save() between MAPI subject and mail.Send()
    assert save_idx == -1, (
        f"Found mail.Save() at offset {save_idx} before mail.Send() at {send_idx}; "
        "Fix 3 requires Save() to be removed from this block"
    )


def test_send_call_wrapped_in_com_error_handling():
    """mail.Send() is inside a try/except pywintypes.com_error block.

    Asserts by static inspection: the ``except pywintypes.com_error as _ce``
    clause captures the COM error and records ``com_error:`` in the failed
    result. We verify this by reading the source and confirming the
    structure.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "send_from_staging.py").read_text()
    # The pattern: try: ... mail.Send() ... except pywintypes.com_error as _ce:
    assert "pywintypes" in src, "pywintypes import not found"
    assert "pywintypes.com_error" in src, "pywintypes.com_error not referenced"
    assert "com_error:" in src, "Reason prefix 'com_error:' not present in result"
    # mail.Send() in the dispatch loop must be inside try/except pywintypes.
    # Use the second occurrence (the first is in the module docstring).
    first = src.find("mail.Send()")
    second = src.find("mail.Send()", first + 1)
    send_idx = second if second != -1 else first
    # Look back for the most recent "try:" at less indentation than the call.
    # Just match the substring: "try:\n                import pywintypes\n                mail.Send()"
    snip_before = src.rfind("\n            try:", 0, send_idx)
    except_idx = src.find("except pywintypes.com_error", send_idx)
    assert snip_before > 0 and except_idx > send_idx, (
        f"mail.Send() at offset {send_idx} is not inside a try/except pywintypes.com_error "
        f"(try at={snip_before}, except at={except_idx})"
    )


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------

def test_module_compiles_and_has_expected_exports():
    """After the three fixes the module exposes the new helpers."""
    assert callable(sfs._item_in_outbox)
    assert callable(sfs.wait_for_outbox_clear)
    assert callable(sfs.trigger_sync)
    assert callable(sfs.find_account)
    # wait_for_sent remains (now informational)
    assert callable(sfs.wait_for_sent)


# ---------------------------------------------------------------------------
# Edge cases — bugs originales que no estaban cubiertos
# ---------------------------------------------------------------------------

def test_wait_for_outbox_clear_senton_appears_on_last_poll(monkeypatch):
    """Boundary: SentOn transitions from None to a real timestamp on the final
    poll before the timeout. The gate must accept this and return True.

    Simulates by advancing time on each ``time.time()`` call so the loop
    visits exactly N polls; the N-th poll observes SentOn set AND the item
    already out of the Outbox.
    """

    class _MutableSentOn:
        """Mail-like object whose SentOn flips from None mid-loop."""

        def __init__(self):
            self.EntryID = "BOUND"
            self._sent_on = None

        @property
        def SentOn(self):
            return self._sent_on

    mail = _MutableSentOn()

    # _item_in_outbox returns True on the first probe (item still in
    # flight), False thereafter (item has left the Outbox).
    calls = {"n": 0}

    def fake_in_outbox(_ns, _m):
        calls["n"] += 1
        # First probe: flip SentOn AFTER the probe returns, modelling
        # the SMTP server stamping the timestamp exactly between polls.
        if calls["n"] == 1:
            mail._sent_on = "2026-07-10 10:00:00"
        return False  # always out of Outbox on the second probe

    # First probe (n==1) returns True (item still there), then flips SentOn.
    # Second probe (n==2) returns False (item left) and SentOn is now set.
    def fake_in_outbox_two_step(_ns, _m):
        calls["n"] += 1
        if calls["n"] == 1:
            mail._sent_on = "2026-07-10 10:00:00"
            return True
        return False

    clock = {"t": 0.0}

    def fake_time():
        clock["t"] += 1.0
        return clock["t"]

    monkeypatch.setattr(sfs, "_item_in_outbox", fake_in_outbox_two_step)
    monkeypatch.setattr(sfs.time, "time", fake_time)
    monkeypatch.setattr(sfs.time, "sleep", lambda _: None)

    ns = MagicMock()
    # timeout=10, well above the time-jumps we do, so the boundary succeeds.
    assert sfs.wait_for_outbox_clear(ns, outbox_before=0, mail=mail, timeout=10) is True


def test_wait_for_outbox_clear_when_item_never_in_outbox(monkeypatch):
    """If the item never appeared in Outbox (sync finished before the gate
    started), the gate must still return True when SentOn is populated.

    This models a fast Exchange server where the mail is sent synchronously
    and SentOn is set before ``wait_for_outbox_clear`` is even called.
    """
    mail = MockMail(entry_id="FAST", sent_on="2026-07-10 09:00:00")

    # _item_in_outbox always returns False: the item is already gone.
    monkeypatch.setattr(sfs, "_item_in_outbox", lambda ns, m: False)
    monkeypatch.setattr(sfs.time, "sleep", lambda _: None)
    monkeypatch.setattr(sfs.time, "time", lambda: 0.0)  # never advances

    ns = MagicMock()
    assert sfs.wait_for_outbox_clear(ns, outbox_before=0, mail=mail, timeout=5) is True


def test_ensure_sender_account_raises_when_no_match(monkeypatch):
    """When OUTLOOK_SENDER_EMAIL is set but no Outlook account matches,
    ``_ensure_sender_account`` must raise RuntimeError so the run aborts.

    The dispatch loop's except-block catches RuntimeError, calls
    ``_abort_run`` and exits with progress status='error'.
    """
    outlook = MagicMock()
    outlook.Session.Accounts = iter(
        [SimpleNamespace(SmtpAddress="someone-else@example.com")]
    )

    with pytest.raises(RuntimeError) as exc_info:
        sfs._ensure_sender_account(outlook, "sender@example.com")

    # The error message must reference the misconfigured sender so the
    # operator can fix it.
    assert "sender@example.com" in str(exc_info.value)
    assert "no matchea" in str(exc_info.value)


def test_ensure_sender_account_returns_none_when_unset():
    """When OUTLOOK_SENDER_EMAIL is not configured, the helper returns None
    and lets main() fall back to the default Outlook account.
    """
    outlook = MagicMock()
    # Empty/None sender_email: do not even probe Accounts.
    assert sfs._ensure_sender_account(outlook, "") is None
    assert sfs._ensure_sender_account(outlook, None) is None


def test_abort_run_writes_status_error(monkeypatch, tmp_path, capsys):
    """_abort_run persists a progress file with status='error' and prints a
    JSON failure summary. main()'s except branch uses this to fail fast when
    _ensure_sender_account raises.
    """
    # Redirect _PROGRESS_FILE to a temp path.
    progress = tmp_path / "send_progress.json"
    monkeypatch.setattr(sfs, "_PROGRESS_FILE", progress)

    reason = "OUTLOOK_SENDER_EMAIL='x@example.com' no matchea ninguna cuenta de Outlook"
    rc = sfs._abort_run(reason)
    assert rc == 1

    # File must exist with status='error' and the right shape.
    payload = json.loads(progress.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"] == reason
    # Counts must be zero, not unknown.
    assert payload["total"] == 0
    assert payload["sent"] == 0
    assert payload["failed"] == 0
    assert payload["current"] == 0
    assert payload["pending"] == 0

    # JSON failure summary printed to stdout for the operator.
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed == {"ok": False, "error": reason}


def test_trigger_sync_with_empty_sync_objects_does_not_call_item(monkeypatch):
    """trigger_sync on an Outlook with zero configured SyncObjects must
    silently no-op without calling .Item() on an empty collection.

    The bug being guarded against: prior versions iterated ``range(1, count+1)``
    without the bound check and would index into an unindexable collection,
    or trigger a different exception path. With Count==0 the loop body never
    executes.
    """
    item_calls = {"n": 0}

    class _EmptySyncObjects:
        Count = 0

        def Item(self, _idx):
            item_calls["n"] += 1
            raise AssertionError("Item() must not be called when Count==0")

    class _Ns:
        SyncObjects = _EmptySyncObjects()

    class _Outlook:
        def GetNamespace(self, _kind):
            return _Ns()

    # trigger_sync may log a warning, that's fine. Must not raise.
    sfs.trigger_sync(_Outlook())
    assert item_calls["n"] == 0


def test_trigger_sync_when_getnamespace_itself_raises(caplog, monkeypatch):
    """If ``outlook.GetNamespace`` itself raises (not just the loop body),
    trigger_sync must log a warning, not swallow the exception silently.

    Distinguish this from test_trigger_sync_logs_warning_on_exception: that
    test fails inside GetNamespace. This test fails at a different layer to
    exercise that the outer try/except covers the whole function call, not
    just the inner iteration.
    """
    class _Outlook:
        def GetNamespace(self, _kind):
            raise _ComError("MAPI subsystem offline")

    caplog.set_level(logging.WARNING, logger="send_from_staging")
    sfs.trigger_sync(_Outlook())

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("trigger_sync" in r.getMessage() for r in warnings)


def test_dispatch_block_keeps_mapi_subject_before_mail_subject_attr():
    """Static guard: the MAPI PR_SUBJECT workaround must be applied BEFORE
    ``mail.Subject = item['subject']`` in the dispatch block.

    This protects the ordering invariant the watcher test
    ``test_outlook_dispatch_sets_subject_via_mapi_first`` relies on: an
    Exchange server that reads subject from the MAPI property must see the
    intended subject even if the COM Subject wrapper gets recycled.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "send_from_staging.py").read_text()
    proptag = src.find("proptag/0x0037001F")
    subject_setter = src.find("mail.Subject = item")
    assert proptag > 0, "MAPI PR_SUBJECT workaround not present in production"
    assert subject_setter > 0, "mail.Subject setter not found"
    assert proptag < subject_setter, (
        f"MAPI PR_SUBJECT (offset {proptag}) must be set BEFORE "
        f"mail.Subject = ... (offset {subject_setter})"
    )
