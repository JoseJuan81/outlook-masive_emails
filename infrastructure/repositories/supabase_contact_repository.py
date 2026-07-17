"""Supabase repository adapter for contacts."""

from __future__ import annotations

import os
import requests

from env import load_project_env
from domain.types import ContactRecord
from ports.contact_repository_port import ContactRepositoryPort

load_project_env()


class SupabaseContactRepository(ContactRepositoryPort):
    """Load contacts from Supabase using the PostgREST endpoint."""

    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        table: str = "contacts",
        select: str = "name,email",
        name_field: str = "name",
        email_field: str = "email",
    ) -> None:
        self.url = (url or os.getenv("SUPABASE_URL") or "").rstrip("/")
        self.key = key or os.getenv("SUPABASE_KEY")
        self.table = table
        self.select = select
        self.name_field = name_field
        self.email_field = email_field

    def get_contacts(self) -> list[ContactRecord]:
        print("Cargando contactos desde Supabase...")
        endpoint = f"{self.url}/rest/v1/{self.table}"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        params = {"select": self.select}

        response = requests.get(endpoint, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        rows = response.json()

        contacts: list[ContactRecord] = []
        for row in rows:
            contacts.append({
                "Nombre": row.get(self.name_field, ""),
                "Correo": row.get(self.email_field, ""),
            })

        print("=" * 50)
        print(f"Fueron encontrados {len(contacts)} contactos en Supabase")
        print("=" * 50)
        return contacts
