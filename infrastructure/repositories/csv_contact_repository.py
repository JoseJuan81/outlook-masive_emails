"""CSV repository that wraps the existing CSV contact loading logic."""

from __future__ import annotations

import pandas as pd

from pathlib import Path

from domain.types import ContactRecord
from ports.contact_repository_port import ContactRepositoryPort


class CSVContactRepository(ContactRepositoryPort):
    """Load contacts from the existing CSV folder without changing the transformation."""

    def __init__(self, contacts_dir: Path | None = None):
        self.contacts_dir = contacts_dir or Path("./../contactos/")

    def get_contacts(self) -> list[ContactRecord]:
        all_contacts_files = self.contacts_dir.iterdir()
        all_contacts = []

        # Existing behavior: read every CSV and keep only Nombre/Correo columns.
        for file in all_contacts_files:
            if file.is_file() and file.suffix == ".csv":
                content = pd.read_csv(file)
                all_contacts.append(content)

        unified_contacts = pd.concat(all_contacts)
        contacts = unified_contacts[["Nombre", "Correo"]]

        print("====================")
        print(f"Cantidad total de contactos = {len(contacts)}")
        print("====================")
        return contacts.to_dict(orient="records")
