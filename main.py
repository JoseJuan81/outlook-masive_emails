"""Genera los correos y los guarda en staging para envío vía Outlook."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from domain.entities import ContactEntity
from infrastructure.repositories.airtable_contact_repository import AirtableContactRepository
from infrastructure.repositories.multi_contact_repository import MultiContactRepository
from infrastructure.services.html_email_builder import HtmlEmailBuilder
from infrastructure.services.html_preview_service import HtmlPreviewService
from infrastructure.services.logging_config import setup_logging
from env import load_project_env

load_project_env()

_PROJECT_ROOT = Path(__file__).resolve().parent
_SUBJECT_FILE = _PROJECT_ROOT / "html/templates/subject.txt"
_STAGING_FILE = _PROJECT_ROOT / "staging/emails_to_send.json"


def _load_subject() -> str:
    if _SUBJECT_FILE.exists():
        return _SUBJECT_FILE.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "No se encontró el asunto. Ejecuta primero:\n  uv run import_email_template.py"
    )


def _to_contact_entity(raw) -> ContactEntity:
    if isinstance(raw, ContactEntity):
        return raw
    return ContactEntity(name=raw.get("Nombre", ""), email=raw.get("Correo", ""))


class _TestEmailRepository:
    def __init__(self, inner, test_email: str) -> None:
        self._inner = inner
        self._test_email = test_email

    def get_contacts(self):
        contacts = self._inner.get_contacts()
        if not contacts:
            return []
        first = _to_contact_entity(contacts[0])
        return [ContactEntity(name=first.name, email=self._test_email)]


def run(airtable_view: str | None = None, test_email: str | None = None) -> None:
    setup_logging()

    subject = _load_subject()
    builder = HtmlEmailBuilder()
    builder.build_email()

    base_repo = MultiContactRepository([AirtableContactRepository(view=airtable_view)])
    repo = _TestEmailRepository(base_repo, test_email) if test_email else base_repo

    contacts = [_to_contact_entity(c) for c in repo.get_contacts()]
    if not contacts:
        raise SystemExit("No se encontraron contactos.")

    # Vista previa opcional
    if os.getenv("PREVIEW_EMAIL_BEFORE_SEND", "").lower() in ("1", "true", "yes", "si", "sí"):
        preview_name = contacts[0].name.split()[0].title()
        preview_html = builder.build(preview_name)
        preview_service = HtmlPreviewService()
        path = preview_service.generate_preview(
            preview_html,
            open_in_browser=os.getenv("PREVIEW_OPEN_IN_BROWSER", "").lower() in ("1", "true", "yes", "si", "sí"),
        )
        print(f"Vista previa: {path}")
        ok = input("¿Apruebas el contenido? S/N: ")
        if ok.strip().lower() not in ("s", "si", "sí"):
            raise SystemExit("Envío cancelado.")

    print(f"\nAsunto : {subject}")
    print(f"Contactos: {len(contacts)}")
    confirm = input("\n¿Confirmas el envío? S/N: ")
    if confirm.strip().lower() not in ("s", "si", "sí"):
        raise SystemExit("Envío cancelado.")

    emails = []
    for contact in contacts:
        first_name = contact.name.split()[0].title() if contact.name else "Estimado"
        emails.append({"to": contact.email, "subject": subject, "html": builder.build(first_name)})

    _STAGING_FILE.parent.mkdir(exist_ok=True)
    _STAGING_FILE.write_text(json.dumps(emails, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(emails)} correo(s) preparados. Ejecutando envío...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepara correos masivos para envío vía Outlook")
    parser.add_argument("--view", default=None, help="Vista de Airtable")
    parser.add_argument("--test-email", default=None, metavar="EMAIL")
    args = parser.parse_args()
    run(airtable_view=args.view, test_email=args.test_email)
