"""Send staged emails via Outlook COM. Run with Windows Python.

After each mail.Send(), triggers a Sync and waits for the email to
appear in Sent Items before dispatching the next one.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_STAGING_FILE = _PROJECT_ROOT / "staging" / "emails_to_send.json"
_PROGRESS_FILE = _PROJECT_ROOT / "staging" / "send_progress.json"
_TRACKING_DIR = _PROJECT_ROOT / "tracking"
_IMAGES_DIR = _PROJECT_ROOT / "html" / "images" / "body"
_CID_PROP = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
_HIDDEN_PROP = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"

MAX_WAIT = 60
POLL_INTERVAL = 0.3


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
    for account in outlook.Session.Accounts:
        smtp = getattr(account, "SmtpAddress", "")
        if smtp and smtp.lower() == sender_email.lower():
            return account
    return None


def get_folder_count(namespace, folder_id):
    try:
        folder = namespace.GetDefaultFolder(folder_id)
        return folder.Items.Count
    except Exception:
        return -1


def trigger_sync(outlook):
    """Force Outlook to Send/Receive all accounts."""
    try:
        sync_objects = outlook.GetNamespace("MAPI").SyncObjects
        for i in range(1, sync_objects.Count + 1):
            sync_objects.Item(i).Start()
    except Exception:
        pass


def wait_for_sent(namespace, sent_count_before):
    """Wait until Sent Items count increases (email confirmed delivered to server)."""
    start = time.time()
    while time.time() - start < MAX_WAIT:
        current = get_folder_count(namespace, 5)
        if current > sent_count_before:
            return True
        time.sleep(POLL_INTERVAL)
    return False


def write_progress(data):
    _PROGRESS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def main():
    load_env()

    if not _STAGING_FILE.exists():
        write_progress({"status": "error", "error": "No staged emails found"})
        print(json.dumps({"ok": False, "error": "No staged emails found"}))
        return

    emails = json.loads(_STAGING_FILE.read_text(encoding="utf-8"))
    images = get_images()

    import win32com.client as win32
    outlook = win32.Dispatch("outlook.application")
    namespace = outlook.GetNamespace("MAPI")
    sender_email = os.getenv("OUTLOOK_SENDER_EMAIL")
    account = find_account(outlook, sender_email) if sender_email else None

    total = len(emails)
    sent = 0
    pending = 0
    failed_list = []
    results = []

    outbox_initial = get_folder_count(namespace, 4)
    sent_initial = get_folder_count(namespace, 5)

    write_progress({
        "status": "sending",
        "total": total,
        "current": 0,
        "sent": 0,
        "pending": 0,
        "failed": 0,
        "current_to": "",
        "outbox_count": outbox_initial,
        "sent_folder_count": sent_initial,
        "outbox_initial": outbox_initial,
        "sent_folder_initial": sent_initial,
    })

    for i, item in enumerate(emails, 1):
        sent_before = get_folder_count(namespace, 5)

        write_progress({
            "status": "sending",
            "total": total,
            "current": i,
            "sent": sent,
            "pending": pending,
            "failed": len(failed_list),
            "current_to": item["to"],
            "phase": "dispatching",
            "outbox_count": get_folder_count(namespace, 4),
            "sent_folder_count": sent_before,
            "outbox_initial": outbox_initial,
            "sent_folder_initial": sent_initial,
        })

        try:
            mail = outlook.CreateItem(0)
            if account:
                mail.SendUsingAccount = account
                try:
                    sf = account.DeliveryStore.GetDefaultFolder(5)
                    mail.SaveSentMessageFolder = sf
                except Exception:
                    pass

            mail.Subject = item["subject"]
            mail.To = item["to"]
            mail.OriginatorDeliveryReportRequested = True

            for idx, img_path in enumerate(images):
                att = mail.Attachments.Add(str(img_path))
                att.PropertyAccessor.SetProperty(_CID_PROP, f"image_{idx}")
                att.PropertyAccessor.SetProperty(_HIDDEN_PROP, True)

            mail.HTMLBody = item["html"]
            mail.Send()

            # Force Outlook to sync immediately
            trigger_sync(outlook)

            # Update progress: waiting for confirmation
            write_progress({
                "status": "sending",
                "total": total,
                "current": i,
                "sent": sent,
                "pending": pending + 1,
                "failed": len(failed_list),
                "current_to": item["to"],
                "phase": "waiting_confirmation",
                "outbox_count": get_folder_count(namespace, 4),
                "sent_folder_count": get_folder_count(namespace, 5),
                "outbox_initial": outbox_initial,
                "sent_folder_initial": sent_initial,
            })

            delivered = wait_for_sent(namespace, sent_before)

            if delivered:
                results.append({"to": item["to"], "status": "sent"})
                sent += 1
            else:
                results.append({"to": item["to"], "status": "sent_pending"})
                pending += 1

        except Exception as e:
            results.append({"to": item["to"], "status": "failed", "error": str(e)})
            failed_list.append(item["to"])

        # Update after each email
        write_progress({
            "status": "sending",
            "total": total,
            "current": i,
            "sent": sent,
            "pending": pending,
            "failed": len(failed_list),
            "current_to": "",
            "phase": "next",
            "outbox_count": get_folder_count(namespace, 4),
            "sent_folder_count": get_folder_count(namespace, 5),
            "outbox_initial": outbox_initial,
            "sent_folder_initial": sent_initial,
        })

    _STAGING_FILE.unlink(missing_ok=True)

    outbox_final = get_folder_count(namespace, 4)
    sent_final = get_folder_count(namespace, 5)

    write_progress({
        "status": "complete",
        "total": total,
        "current": total,
        "sent": sent,
        "pending": pending,
        "failed": len(failed_list),
        "current_to": "",
        "outbox_count": outbox_final,
        "sent_folder_count": sent_final,
        "outbox_initial": outbox_initial,
        "sent_folder_initial": sent_initial,
        "outbox_delta": outbox_final - outbox_initial if outbox_initial >= 0 else -1,
        "sent_folder_new": sent_final - sent_initial if sent_initial >= 0 and sent_final >= 0 else -1,
    })

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


if __name__ == "__main__":
    main()
