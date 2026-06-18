"""Envía correos vía Outlook COM. Ejecutar con Windows Python.
No importa nada del proyecto — solo lee el JSON generado por main.py."""

import json
import os
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_STAGING_FILE = _PROJECT_ROOT / "staging" / "emails_to_send.json"
_IMAGES_DIR = _PROJECT_ROOT / "html" / "images" / "body"
_CID_PROP = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
_HIDDEN_PROP = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"


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
    return sorted(
        (f for f in _IMAGES_DIR.iterdir() if f.is_file() and not f.name.endswith(".Identifier")),
        key=lambda f: f.name,
    )


def find_account(outlook, sender_email: str):
    for account in outlook.Session.Accounts:
        smtp = getattr(account, "SmtpAddress", "")
        if smtp and smtp.lower() == sender_email.lower():
            return account
    return None


def main():
    load_env()

    if not _STAGING_FILE.exists():
        raise SystemExit("No hay correos preparados. Ejecuta primero:\n  uv run main.py")

    emails = json.loads(_STAGING_FILE.read_text(encoding="utf-8"))
    images = get_images()

    import win32com.client as win32
    outlook = win32.Dispatch("outlook.application")
    sender_email = os.getenv("OUTLOOK_SENDER_EMAIL")
    account = find_account(outlook, sender_email) if sender_email else None

    total = len(emails)
    failed = []

    for i, item in enumerate(emails, 1):
        print(f"Enviando {i}/{total} -> {item['to']}")
        try:
            mail = outlook.CreateItem(0)
            if account:
                mail.SendUsingAccount = account
            mail.Subject = item["subject"]
            mail.To = item["to"]

            for idx, img_path in enumerate(images):
                att = mail.Attachments.Add(str(img_path))
                att.PropertyAccessor.SetProperty(_CID_PROP, f"image_{idx}")
                att.PropertyAccessor.SetProperty(_HIDDEN_PROP, True)

            mail.HTMLBody = item["html"]
            mail.Send()
            print(f"  OK")
        except Exception as e:
            print(f"  ERROR: {e}")
            failed.append(item["to"])

        if i < total:
            time.sleep(0.2)

    print(f"\nFIN: {total - len(failed)}/{total} enviados.")
    if failed:
        print(f"Fallidos: {', '.join(failed)}")

    _STAGING_FILE.unlink()


if __name__ == "__main__":
    main()
