"""Notion repository adapter for contacts."""

from __future__ import annotations

import os
import requests
import pandas as pd

from env import load_project_env
from domain.types import ContactRecord
from ports.contact_repository_port import ContactRepositoryPort
from helper.notion_helper import ContactColumns, get_contact_prop_value, filter_by_contact_prop

load_project_env()


class NotionContactRepository(ContactRepositoryPort):
    """Load contacts from a Notion database using the existing helper mapping."""

    def __init__(
        self,
        token: str | None = None,
        database_id: str | None = None,
        filter_columns: list | None = None,
    ) -> None:
        self.token = token or os.getenv("NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_CONTACT_DB_ID")
        self.filter_columns = filter_columns or []
        self.notion_url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
        }

    def get_contacts(self) -> list[ContactRecord]:
        contacts = self._get_contacts_from_notion()
        data_frame = self._extract_contact_properties(contacts)
        return self._filter_contacts(data_frame)

    def _get_contacts_from_notion(self) -> list[dict]:
        print("Cargando contactos desde Notion...")
        all_contacts = []
        has_more = True
        next_cursor = None

        while has_more:
            payload = {"start_cursor": next_cursor} if next_cursor else None
            response = requests.post(self.notion_url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            results_json = response.json()

            all_contacts.extend(results_json["results"])
            has_more = results_json["has_more"]
            next_cursor = results_json["next_cursor"]

        print("=" * 50)
        print(f"Fueron encontrados {len(all_contacts)} contactos en Notion")
        print("=" * 50)
        return all_contacts

    def _extract_contact_properties(self, contacts: list[dict]) -> pd.DataFrame:
        new_contacts: list[ContactRecord] = []

        for contact in contacts:
            props = contact["properties"]
            new_contacts.append({
                ContactColumns.NAME.value: get_contact_prop_value(ContactColumns.NAME, props),
                ContactColumns.EMAIL.value: get_contact_prop_value(ContactColumns.EMAIL, props),
                ContactColumns.AREA.value: get_contact_prop_value(ContactColumns.AREA, props),
                ContactColumns.NO_EMAIL.value: get_contact_prop_value(ContactColumns.NO_EMAIL, props),
                ContactColumns.COUNTRY.value: get_contact_prop_value(ContactColumns.COUNTRY, props),
            })

        print("=" * 50)
        print(f"{len(new_contacts)} Contactos transformados a DataFrame con propiedades de interés")
        print("=" * 50)
        return pd.DataFrame(new_contacts)

    def _filter_contacts(self, contacts: pd.DataFrame) -> list[ContactRecord]:
        filter_email_is_not_none = contacts[ContactColumns.EMAIL.value].notna()
        df_no_empty_email = contacts.loc[filter_email_is_not_none]

        filter_no_masive_email = df_no_empty_email[ContactColumns.NO_EMAIL.value] == False
        filtered = df_no_empty_email.loc[filter_no_masive_email]

        print("=" * 50)
        print(f"Resultados del primer filtrado: {len(filtered)} contactos")
        print("=" * 50)

        filtered = filter_by_contact_prop(
            filter_values=self.filter_columns,
            data_frame=filtered,
        )
        result = filtered.to_dict(orient="records")

        print("=" * 50)
        print(f"Resultado de aplicar filtros: {len(result)} contactos pasaron los filtros")
        print("=" * 50)
        return result
