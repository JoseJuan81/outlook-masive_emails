"""Standalone command for rendering and previewing the email HTML."""

from __future__ import annotations

import argparse
import os

from pathlib import Path

from Classes.email_class import SendEmails
from domain.entities import ContactEntity
from env import load_project_env
from infrastructure.repositories.airtable_contact_repository import AirtableContactRepository
from infrastructure.repositories.multi_contact_repository import MultiContactRepository

load_project_env()


def run_preview(
    repository=None,
    open_in_browser: bool | None = None,
    filename: str = "email_preview.html",
    contact_email: str | None = None,
    contact_name: str | None = None,
) -> Path:
    emails = SendEmails()

    active_repository = repository or MultiContactRepository([
        AirtableContactRepository(),
    ])
    emails.set_contact_repository(active_repository, test_mode=True)

    contacts = emails.contact_repository.get_contacts()
    if not contacts:
        raise RuntimeError("No se encontraron contactos para generar la vista previa.")

    normalized_contacts = [_normalize_contact(contact) for contact in contacts]
    preview_contact = _select_preview_contact(
        contacts=normalized_contacts,
        contact_email=contact_email,
        contact_name=contact_name,
    )

    first_name = preview_contact.name.split(" ")[0].title()
    html = emails.html_builder.build(first_name)

    open_preview = (
        open_in_browser
        if open_in_browser is not None
        else _resolve_preview_open_in_browser(default=True)
    )

    preview_path = emails.preview_service.generate_preview(
        html=html,
        filename=filename,
        open_in_browser=open_preview,
    )

    print("=" * 60)
    print(f"Vista previa generada en: {preview_path.resolve()}")
    print(f"Contacto de referencia: {preview_contact.name} <{preview_contact.email}>")
    print("=" * 60)
    return preview_path


def _normalize_contact(contact) -> ContactEntity:
    if isinstance(contact, ContactEntity):
        return contact

    if isinstance(contact, dict):
        name, email, *_ = contact.values()
        return ContactEntity(name=name, email=email, metadata=contact)

    if isinstance(contact, (list, tuple)):
        name, email, *_ = contact
        return ContactEntity(
            name=name,
            email=email,
            metadata={"Nombre": name, "Correo": email},
        )

    raise TypeError(f"Formato de contacto no soportado para vista previa: {type(contact)!r}")


def _select_preview_contact(
    contacts: list[ContactEntity],
    contact_email: str | None = None,
    contact_name: str | None = None,
) -> ContactEntity:
    if contact_email:
        for contact in contacts:
            if contact.email.lower() == contact_email.lower():
                return contact
        raise RuntimeError(f"No se encontró un contacto con el correo: {contact_email}")

    if contact_name:
        for contact in contacts:
            if contact.name.lower() == contact_name.lower():
                return contact
        raise RuntimeError(f"No se encontró un contacto con el nombre: {contact_name}")

    return contacts[0]


def _resolve_preview_open_in_browser(default: bool = True) -> bool:
    value = os.getenv("PREVIEW_OPEN_IN_BROWSER")
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "si", "sí"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Genera una vista previa HTML del correo.")
    parser.add_argument(
        "--contact-email",
        dest="contact_email",
        help="Usa como referencia el contacto que coincida con este correo.",
    )
    parser.add_argument(
        "--contact-name",
        dest="contact_name",
        help="Usa como referencia el contacto que coincida exactamente con este nombre.",
    )
    parser.add_argument(
        "--output",
        default="email_preview.html",
        help="Nombre del archivo HTML de salida dentro de la carpeta preview/.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Genera el archivo de vista previa sin abrirlo en el navegador.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    run_preview(
        open_in_browser=not args.no_open,
        filename=args.output,
        contact_email=args.contact_email,
        contact_name=args.contact_name,
    )


if __name__ == "__main__":
    main()
