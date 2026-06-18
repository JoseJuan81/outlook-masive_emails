"""Airtable repository adapter for contacts."""

from __future__ import annotations

import os
import requests

from env import load_project_env
from domain.types import ContactRecord
from ports.contact_repository_port import ContactRepositoryPort

load_project_env()


class AirtableContactRepository(ContactRepositoryPort):
    """Load contacts from Airtable through its REST API."""

    def __init__(
        self,
        base_id: str | None = None,
        table_id: str | None = None,
        token: str | None = None,
        view: str | None = None,
    ) -> None:
        self.base_id = base_id or os.getenv("AIRTABLE_BASE_ID")
        self.table_id = table_id or os.getenv("AIRTABLE_CONTACT_TABLE_ID")
        self.token = token or os.getenv("AIRTABLE_TOKEN")
        self.view = view or os.getenv("AIRTABLE_VIEW")
        self.url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}"

    def get_contacts(self) -> list[ContactRecord]:
        print("Cargando contactos desde Airtable...")
        all_contacts: list[ContactRecord] = []
        offset: str | None = None
        headers = {"Authorization": f"Bearer {self.token}"}

        while True:
            params = {}
            if offset:
                params["offset"] = offset
            if self.view:
                params["view"] = self.view

            token_prefix = f"{self.token[:12]}..." if self.token else None
            print(
                "DEBUG Airtable request:",
                {
                    "base_id": self.base_id,
                    "table_id": self.table_id,
                    "view": self.view,
                    "url": self.url,
                    "token_prefix": token_prefix,
                    "has_token": bool(self.token),
                },
            )

            response = requests.get(
                self.url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()

            all_contacts.extend(self._extract_contacts(
                payload.get("records", [])))
            offset = payload.get("offset")

            if not offset:
                break

        print("=" * 50)
        print(f"Fueron encontrados {len(all_contacts)} contactos en Airtable")
        print("=" * 50)
        return all_contacts

    def _extract_contacts(self, records: list[dict]) -> list[ContactRecord]:
        contacts: list[ContactRecord] = []

        for record in records:
            fields = record.get("fields", {})
            name = fields.get("Nombre") or fields.get("Name") or ""
            email = fields.get("CORREO") or fields.get("Email") or ""

            contact: ContactRecord = {
                "Nombre": name,
                "Correo": email,
            }

            if name or email:
                contacts.append(contact)

        return contacts
