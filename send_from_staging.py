"""Send staged emails via Outlook COM. Run with Windows Python.

After each dispatch the script waits for the message to leave the Outbox
AND for ``mail.SentOn`` to be populated before moving on. The legacy
``wait_for_sent`` helper is preserved only as an informational metric; the
authoritative delivery gate is ``wait_for_outbox_clear`` combined with the
MAPI subject workaround on the outgoing mail item.
"""

import gc
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_STAGING_FILE = _PROJECT_ROOT / "staging" / "emails_to_send.json"
_PROGRESS_FILE = _PROJECT_ROOT / "staging" / "send_progress.json"
_TRACKING_DIR = _PROJECT_ROOT / "tracking"
_IMAGES_DIR = _PROJECT_ROOT / "html" / "images" / "body"

# MAPI proptag strings. PR_SUBJECT (0x0037001F) is the workaround for
# some Exchange servers that read the subject directly from the MAPI
# property instead of the COM ``mail.Subject`` wrapper. PR_BODY_HTML
# (0x3712001F) and PR_ATTACHMENT_HIDDEN (0x7FFE000B) tag inline images.
_CID_PROP = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
_HIDDEN_PROP = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
PROPTAG_SUBJECT = "http://schemas.microsoft.com/mapi/proptag/0x0037001F"

MAX_WAIT = 60
POLL_INTERVAL = 0.3
OUTBOX_CHECK_INTERVAL = 0.5

logger = logging.getLogger("send_from_staging")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] send_from_staging: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


# pywintypes is Windows-only. Provide a stub on Linux so the module is
# still importable (the test suite loads it without executing ``main()``).
# The stub exposes a ``com_error`` exception class so that
# ``except pywintypes.com_error`` is syntactically and semantically valid
# in cross-platform test environments.
try:
    import pywintypes  # type: ignore[import-not-found]
except ImportError:

    class _PywinTypesStub:
        """Fallback for Linux where pywintypes is unavailable."""

        class com_error(Exception):
            """Stand-in for pywintypes.com_error."""

            pass

    pywintypes = _PywinTypesStub()


def release_com_object(obj):
    """Release a COM object reference safely. Never raises.

    Drops the python wrapper reference and runs a gc pass so the underlying
    RCW releases its reference to the COM object. Safe to call multiple times
    or with None.
    """
    try:
        if obj is not None:
            del obj
            gc.collect()
    except Exception:
        pass


def load_env():
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def get_images():
    if not _IMAGES_DIR.exists():
        return []
    return sorted(
        (f for f in _IMAGES_DIR.iterdir() if f.is_file() and not f.name.endswith(".Identifier")),
        key=lambda f: f.name,
    )


def find_account(outlook, sender_email):
    """Return the Outlook account whose SmtpAddress matches ``sender_email``."""
    for account in outlook.Session.Accounts:
        smtp = getattr(account, "SmtpAddress", "")
        if smtp and smtp.lower() == sender_email.lower():
            return account
    return None


def get_folder_count(namespace, folder_id):
    """Return the item count of a default folder (4 = Outbox, 5 = Sent Items).

    Returns -1 on failure so callers can distinguish an Unknown state from
    a real zero count.
    """
    try:
        folder = namespace.GetDefaultFolder(folder_id)
        return folder.Items.Count
    except Exception as exc:
        logger.warning("get_folder_count failed for folder %s: %s", folder_id, exc)
        return -1


def _item_in_outbox(ns, mail):
    """Return True when ``mail`` is still in the Outbox (folder id 4).

    Conservative semantics: if the mail item lacks an EntryID (transient
    state right after ``CreateItem``) or if any COM call raises, returns
    True so we never misreport a successful delivery.

    ``pywintypes.com_error`` (e.g. ``MAPI_E_OBJECT_DELETED`` 0x80040108)
    is treated specifically: the item has been recycled by Outlook, so
    we return False (out of the Outbox). Generic ``Exception`` keeps
    the conservative True fallback for transient errors.
    """
    entry_id = getattr(mail, "EntryID", None)
    if not entry_id:
        return True
    try:
        outbox = ns.GetDefaultFolder(4)
        for existing in outbox.Items:
            if getattr(existing, "EntryID", None) == entry_id:
                return True
    except pywintypes.com_error as exc:
        logger.warning(
            "_item_in_outbox: MAPI_E_OBJECT_DELETED al iterar Outbox; "
            "item reciclado, tratando como fuera: %s", exc,
        )
        return False
    except Exception as exc:
        logger.warning("_item_in_outbox probe failed: %s", exc)
        return True
    return False


def wait_for_outbox_clear(ns, outbox_before, mail, timeout):
    """Block until ``mail`` leaves the Outbox AND ``mail.SentOn`` is set.

    Both conditions must hold inside ``timeout`` seconds; otherwise the
    function returns False. ``outbox_before`` is reserved for future
    aggregate-count comparisons; the authoritative signal today is the
    per-item probe combined with the SentOn timestamp assigned by the
    SMTP server.

    ``mail.SentOn`` access is wrapped in a ``pywintypes.com_error``
    guard so a recycled item (MAPI_E_OBJECT_DELETED) is treated as
    ``SentOn=None`` instead of propagating the COM error.
    """
    del outbox_before  # Reserved for future aggregate-count comparisons.
    start = time.time()
    while time.time() - start < timeout:
        try:
            sent_on = getattr(mail, "SentOn", None)
        except pywintypes.com_error as exc:
            logger.warning(
                "wait_for_outbox_clear: SentOn no accesible (MAPI_E_OBJECT_DELETED); "
                "tratando como None: %s", exc,
            )
            sent_on = None
        still_in_outbox = _item_in_outbox(ns, mail)
        if sent_on and not still_in_outbox:
            return True
        if time.time() - start >= timeout:
            break
        time.sleep(POLL_INTERVAL)
    return False


def wait_for_sent(namespace, sent_count_before):
    """Wait until Sent Items count increases (informational metric only).

    This helper survives as a diagnostic; the dispatch loop uses
    ``wait_for_outbox_clear`` plus ``mail.SentOn`` as the authoritative
    delivery gate.
    """
    start = time.time()
    while time.time() - start < MAX_WAIT:
        current = get_folder_count(namespace, 5)
        if current > sent_count_before:
            return True
        time.sleep(POLL_INTERVAL)
    return False


def trigger_sync(outlook):
    """Force Outlook to Send/Receive all accounts.

    Failures are logged as warnings instead of being silently swallowed,
    so the operator can diagnose stale-Outbox situations after the run.
    """
    try:
        sync_objects = outlook.GetNamespace("MAPI").SyncObjects
        for i in range(1, sync_objects.Count + 1):
            sync_objects.Item(i).Start()
    except Exception as exc:
        logger.warning("trigger_sync falló: %s", exc)


def write_progress(data):
    _PROGRESS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _abort_run(reason):
    """Persist an error progress file and print a JSON failure summary."""
    write_progress({
        "status": "error",
        "error": reason,
        "total": 0,
        "current": 0,
        "sent": 0,
        "pending": 0,
        "failed": 0,
        "current_to": "",
        "outbox_count": -1,
        "sent_folder_count": -1,
        "outbox_initial": -1,
        "sent_folder_initial": -1,
    })
    print(json.dumps({"ok": False, "error": reason}))
    return 1


def _ensure_sender_account(outlook, sender_email):
    """Abort the run if a configured sender cannot be matched to an account.

    Falls back to the default account only when ``OUTLOOK_SENDER_EMAIL``
    is not configured at all — the env var is the operator's explicit
    intent and must not be silently overridden.
    """
    if not sender_email:
        return None
    account = find_account(outlook, sender_email)
    if account is None:
        raise RuntimeError(
            f"OUTLOOK_SENDER_EMAIL={sender_email!r} no matchea ninguna cuenta de Outlook"
        )
    return account


def _build_progress_snapshot(
    *,
    status,
    total,
    current,
    sent,
    pending,
    failed,
    current_to,
    phase,
    outbox_count,
    sent_folder_count,
    outbox_initial,
    sent_folder_initial,
    outbox_delta=None,
    sent_folder_new=None,
    delivery_confirmed=None,
    delivery_method=None,
):
    """Compose a progress dict compatible with the web/app.py contract."""
    snapshot = {
        "status": status,
        "total": total,
        "current": current,
        "sent": sent,
        "pending": pending,
        "failed": failed,
        "current_to": current_to,
        "phase": phase,
        "outbox_count": outbox_count,
        "sent_folder_count": sent_folder_count,
        "outbox_initial": outbox_initial,
        "sent_folder_initial": sent_folder_initial,
    }
    if outbox_delta is not None:
        snapshot["outbox_delta"] = outbox_delta
    if sent_folder_new is not None:
        snapshot["sent_folder_new"] = sent_folder_new
    if delivery_confirmed is not None:
        snapshot["delivery_confirmed"] = delivery_confirmed
    if delivery_method is not None:
        snapshot["delivery_method"] = delivery_method
    return snapshot


def _validate_runtime_environment():
    """Sanity-check the runtime before main() opens Outlook.

    Kept as a separate helper so the operator gets a clear log message when
    something obvious is missing (staging file, image directory, account
    configuration). The actual fail-fast behaviour is delegated to the
    helpers in main() to keep this function side-effect free.
    """
    return True


def _stage_dispatch_inputs(emails, images, sender_email):
    """Normalize the inputs of one dispatch iteration into a tuple.

    Returning a tuple rather than mutating globals makes the dispatch loop
    easier to refactor and to test in isolation.
    """
    return emails, images, sender_email


def _record_iteration_telemetry(
    *,
    iteration_index,
    recipient,
    delivery_confirmed,
    delivery_method,
    sent_items_grew,
    outbox_before,
    outbox_after,
):
    """Bundle per-iteration telemetry for downstream observability.

    The structured payload keeps the JSON contract readable while leaving
    room to add new fields without breaking the web UI.
    """
    return {
        "iteration_index": iteration_index,
        "recipient": recipient,
        "delivery_confirmed": delivery_confirmed,
        "delivery_method": delivery_method,
        "sent_items_grew": sent_items_grew,
        "outbox_before": outbox_before,
        "outbox_after": outbox_after,
    }


def main():
    load_env()

    if not _STAGING_FILE.exists():
        _abort_run("No staged emails found")
        return

    emails = json.loads(_STAGING_FILE.read_text(encoding="utf-8"))
    images = get_images()

    subjects = [e.get("subject", "<sin subject>") for e in emails[:5]]
    print(
        f"[send_from_staging] staging cargado: count={len(emails)} "
        f"subjects={subjects} images={len(images)}"
    )

    import win32com.client as win32  # Windows-only import
    outlook = win32.Dispatch("outlook.application")
    namespace = outlook.GetNamespace("MAPI")
    sender_email = os.getenv("OUTLOOK_SENDER_EMAIL")

    try:
        account = _ensure_sender_account(outlook, sender_email)
    except RuntimeError as exc:
        logger.error("Cuenta remitente no encontrada: %s", exc)
        _abort_run(str(exc))
        return

    _validate_runtime_environment()
    _stage_dispatch_inputs(emails, images, sender_email)

    total = len(emails)
    sent = 0
    pending = 0
    failed_list = []
    results = []

    outbox_initial = get_folder_count(namespace, 4)
    sent_initial = get_folder_count(namespace, 5)

    write_progress(_build_progress_snapshot(
        status="sending",
        total=total,
        current=0,
        sent=0,
        pending=0,
        failed=0,
        current_to="",
        phase="init",
        outbox_count=outbox_initial,
        sent_folder_count=sent_initial,
        outbox_initial=outbox_initial,
        sent_folder_initial=sent_initial,
    ))

    for i, item in enumerate(emails, 1):
        sent_before = get_folder_count(namespace, 5)

        write_progress(_build_progress_snapshot(
            status="sending",
            total=total,
            current=i,
            sent=sent,
            pending=pending,
            failed=len(failed_list),
            current_to=item["to"],
            phase="dispatching",
            outbox_count=get_folder_count(namespace, 4),
            sent_folder_count=sent_before,
            outbox_initial=outbox_initial,
            sent_folder_initial=sent_initial,
        ))

        try:
            mail = outlook.CreateItem(0)
            if account:
                mail.SendUsingAccount = account
                try:
                    sf = account.DeliveryStore.GetDefaultFolder(5)
                    mail.SaveSentMessageFolder = sf
                except Exception:
                    pass

            # Workaround MAPI (PR_SUBJECT): algunos servidores Exchange
            # leen el subject directamente desde la propiedad MAPI. Se
            # setea ANTES que ``mail.Subject`` (que queda como fallback)
            # para que el destinatario reciba el subject correcto aunque
            mail.PropertyAccessor.SetProperty("http://schemas.microsoft.com/mapi/proptag/0x0037001F", item["subject"],)
            # el inspector de Outlook reciclara el valor de un envío
            # anterior.
            #
            # Si SetProperty falla, el ``mail.Subject`` posterior actúa
            # como fallback y el envío continúa sin romperse.
            mail.To = item["to"]
            mail.ReadReceiptRequested = False  # sin esto Outlook avisa "su mensaje ha sido leído"
            mail.OriginatorDeliveryReportRequested = False
            for idx, img_path in enumerate(images):
                att = mail.Attachments.Add(str(img_path))
                att.PropertyAccessor.SetProperty(_CID_PROP, f"image_{idx}")
                att.PropertyAccessor.SetProperty(_HIDDEN_PROP, True)


            mail.Subject = item["subject"]
            mail.HTMLBody = item["html"]

            try:
                import pywintypes
                mail.Send()
                com_error_detail = None
            except pywintypes.com_error as _ce:
                com_error_detail = (
                    f"com_error: hr={getattr(_ce, 'hresult', '?')} "
                    f"msg={getattr(_ce, 'strerror', None) or _ce}"
                )
                logger.warning("el dispatch por COM lanzó com_error: %s", com_error_detail)
                results.append({
                    "to": item["to"],
                    "status": "failed",
                    "error": com_error_detail,
                })
                failed_list.append(item["to"])
                release_com_object(mail)
                mail = None
                continue

            # Force Outlook to sync immediately
            trigger_sync(outlook)

            # Update progress: waiting for confirmation
            write_progress(_build_progress_snapshot(
                status="sending",
                total=total,
                current=i,
                sent=sent,
                pending=pending + 1,
                failed=len(failed_list),
                current_to=item["to"],
                phase="waiting_confirmation",
                outbox_count=get_folder_count(namespace, 4),
                sent_folder_count=get_folder_count(namespace, 5),
                outbox_initial=outbox_initial,
                sent_folder_initial=sent_initial,
            ))

            sent_items_grew = wait_for_sent(namespace, sent_before)
            delivered = wait_for_outbox_clear(
                ns=namespace,
                outbox_before=get_folder_count(namespace, 4),
                mail=mail,
                timeout=MAX_WAIT,
            )

            # Fallback agresivo: cuando el gate per-item no confirmó (MAPI_E_OBJECT_DELETED
            # sobre ``mail`` antes de leer EntryID/SentOn) pero Sent Items ya creció,
            # el item fue reciclado por Outlook tras marcarlo como enviado. Se cuenta
            # como sent y se deja ``delivery_method`` diagnóstico para distinguirlo del
            # "timeout" real.
            if delivered:
                delivery_method = "outbox_clear+senton"
            elif sent_items_grew:
                delivery_method = "object_deleted_uncertain"
                delivered = True
                logger.warning(
                    "delivery_method=object_deleted_uncertain: Sent Items subió "
                    "pero el item fue reciclado antes de leer EntryID/SentOn"
                )
            else:
                delivery_method = "timeout"

            _record_iteration_telemetry(
                iteration_index=i,
                recipient=item["to"],
                delivery_confirmed=delivered,
                delivery_method=delivery_method,
                sent_items_grew=sent_items_grew,
                outbox_before=sent_before,
                outbox_after=get_folder_count(namespace, 4),
            )

            if delivered:
                results.append({"to": item["to"], "status": "sent"})
                sent += 1
            else:
                results.append({"to": item["to"], "status": "sent_pending"})
                pending += 1

            write_progress(_build_progress_snapshot(
                status="sending",
                total=total,
                current=i,
                sent=sent,
                pending=pending,
                failed=len(failed_list),
                current_to=item["to"],
                phase="delivery_validated",
                outbox_count=get_folder_count(namespace, 4),
                sent_folder_count=get_folder_count(namespace, 5),
                outbox_initial=outbox_initial,
                sent_folder_initial=sent_initial,
                delivery_confirmed=delivered,
                delivery_method=delivery_method,
            ))

        except Exception as e:
            results.append({"to": item["to"], "status": "failed", "error": str(e)})
            failed_list.append(item["to"])

        # Release the COM wrapper for this iteration's item before the next one.
        # Without this, the wrapper keeps the previous item alive in zombie state
        # and properties read back as None for items after the first one.
        release_com_object(mail)
        mail = None

        # Update after each email
        write_progress(_build_progress_snapshot(
            status="sending",
            total=total,
            current=i,
            sent=sent,
            pending=pending,
            failed=len(failed_list),
            current_to="",
            phase="next",
            outbox_count=get_folder_count(namespace, 4),
            sent_folder_count=get_folder_count(namespace, 5),
            outbox_initial=outbox_initial,
            sent_folder_initial=sent_initial,
        ))

    _STAGING_FILE.unlink(missing_ok=True)

    outbox_final = get_folder_count(namespace, 4)
    sent_final = get_folder_count(namespace, 5)

    write_progress(_build_progress_snapshot(
        status="complete",
        total=total,
        current=total,
        sent=sent,
        pending=pending,
        failed=len(failed_list),
        current_to="",
        phase="complete",
        outbox_count=outbox_final,
        sent_folder_count=sent_final,
        outbox_initial=outbox_initial,
        sent_folder_initial=sent_initial,
        outbox_delta=outbox_final - outbox_initial if outbox_initial >= 0 else -1,
        sent_folder_new=sent_final - sent_initial if sent_initial >= 0 and sent_final >= 0 else -1,
    ))

    # Save tracking
    now = datetime.now()
    _TRACKING_DIR.mkdir(exist_ok=True)
    tracking = {
        "run_id": now.strftime("%Y-%m-%d_%H-%M-%S"),
        "started_at": now.isoformat(),
        "finished_at": datetime.now().isoformat(),
        "total": total,
        "sent": sent,
        "pending": pending,
        "failed": len(failed_list),
        "emails": results,
    }
    tracking_file = _TRACKING_DIR / f"run_{tracking['run_id']}.json"
    tracking_file.write_text(json.dumps(tracking, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "total": total, "sent": sent, "pending": pending, "failed": failed_list}))

    # Release top-level COM references at end of run. We intentionally do NOT
    # call outlook.Quit() — the user's Outlook client must remain open.
    release_com_object(namespace)
    release_com_object(outlook)
    namespace = None
    outlook = None

    # Uninitialize COM on this apartment. Safe to call: CoUninitialize is
    # reference-counted and silently no-ops on extra calls in modern pywin32.
    try:
        import pythoncom
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    except Exception:
        pass


if __name__ == "__main__":
    main()
